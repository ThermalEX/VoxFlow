"""Merge the LoRA adapter into its base model and convert it to GGUF for llama.cpp (run inside the WSL training env).

Usage:
  python -m training.rewrite.export_gguf --adapter training/rewrite/runs/qwen3.5-2b/adapter \
      --output training/rewrite/runs/qwen3.5-2b/gguf --llama-cpp ~/llama.cpp
Further quantization (for example Q4_K_M) uses llama.cpp's llama-quantize on the bf16 file.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .train import ROOT, is_gemma, load_model

GGUF_PREFIX = "voxflow-rewrite"


def gguf_name(kind: str) -> str:
    return f"{GGUF_PREFIX}-{kind}.gguf"


def conversion_commands(llama_cpp: Path, merged: Path, output: Path, kinds: list[str]) -> list[list[str]]:
    return [["python", f"{llama_cpp.as_posix()}/convert_hf_to_gguf.py", merged.as_posix(), "--outtype", kind,
             "--outfile", f"{output.as_posix()}/{gguf_name(kind)}"] for kind in kinds]


def merge_lora_by_tensor(base: Path, adapter: Path, merged: Path, shard_bytes: int = 2 << 30) -> int:
    """Add a LoRA adapter to a safetensors checkpoint one tensor at a time.

    Loading Gemma 4 E2B in bf16 to merge it needs more system memory than the WSL environment has; this keeps
    at most one output shard in memory. Returns how many weights were changed.
    """
    import shutil

    import torch
    from safetensors import safe_open
    from safetensors.torch import load_file, save_file

    config = json.loads((adapter / "adapter_config.json").read_text(encoding="utf-8"))
    scale = config["lora_alpha"] / config["r"]
    lora = load_file(str(adapter / "adapter_model.safetensors"))
    # base_model.model.model.layers.N.<module>.lora_A.weight -> model.language_model.layers.N.<module>.weight
    deltas = {}
    for key in lora:
        if ".lora_A." in key:
            target = key.replace("base_model.model.model.", "model.language_model.").replace(".lora_A.weight", ".weight")
            deltas[target] = (lora[key], lora[key.replace(".lora_A.", ".lora_B.")])
    merged.mkdir(parents=True, exist_ok=True)
    for name in ("config.json", "generation_config.json", "tokenizer.json", "tokenizer_config.json",
                 "chat_template.jinja", "processor_config.json"):
        if (base / name).is_file():
            shutil.copy2(base / name, merged / name)
    weight_map, shard, size, changed = {}, {}, 0, 0

    def flush():
        nonlocal shard, size
        name = f"model-{len(set(weight_map.values())) + 1:05d}.safetensors"
        save_file(shard, str(merged / name), metadata={"format": "pt"})
        weight_map.update({key: name for key in shard})
        shard, size = {}, 0

    for path in sorted(base.glob("*.safetensors")):
        with safe_open(str(path), "pt") as reader:
            for key in reader.keys():
                tensor = reader.get_tensor(key)
                if key in deltas:
                    down, up = deltas.pop(key)
                    tensor = (tensor.float() + (up.float() @ down.float()) * scale).to(tensor.dtype)
                    changed += 1
                shard[key] = tensor
                size += tensor.numel() * tensor.element_size()
                if size >= shard_bytes:
                    flush()
    if shard:
        flush()
    if deltas:
        raise ValueError(f"{len(deltas)} adapter weights have no match in the checkpoint, e.g. {next(iter(deltas))}")
    index = {"metadata": {}, "weight_map": weight_map}
    (merged / "model.safetensors.index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the VoxFlow rewrite model to GGUF")
    parser.add_argument("--adapter", type=Path, default=ROOT / "runs" / "qwen3.5-2b" / "adapter")
    parser.add_argument("--output", type=Path, default=ROOT / "runs" / "qwen3.5-2b" / "gguf")
    parser.add_argument("--llama-cpp", type=Path, default=Path.home() / "llama.cpp")
    parser.add_argument("--types", nargs="+", default=["q8_0", "bf16"])
    parser.add_argument("--load-in-4bit", action="store_true", help="the adapter was trained as a QLoRA")
    args = parser.parse_args()

    merged = args.output / "merged"
    if not (merged / "config.json").is_file():
        base = json.loads((args.adapter / "adapter_config.json").read_text(encoding="utf-8"))["base_model_name_or_path"]
        if is_gemma(base):
            from huggingface_hub import snapshot_download

            changed = merge_lora_by_tensor(Path(snapshot_download(base)), args.adapter, merged)
            print(f"merged LoRA into {changed} weights", flush=True)
        else:
            model, processor = load_model(str(args.adapter), 2048, args.load_in_4bit)
            model.save_pretrained_merged(str(merged), processor, save_method="merged_16bit")
    for command in conversion_commands(args.llama_cpp, merged, args.output, args.types):
        command[0] = sys.executable
        print(" ".join(command), flush=True)
        subprocess.run(command, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
