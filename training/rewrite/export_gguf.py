"""Merge the LoRA adapter into Qwen3.5 and convert it to GGUF for llama.cpp (run inside the WSL training env).

Usage:
  python -m training.rewrite.export_gguf --adapter training/rewrite/runs/qwen3.5-2b/adapter \
      --output training/rewrite/runs/qwen3.5-2b/gguf --llama-cpp ~/llama.cpp
Further quantization (for example Q4_K_M) uses llama.cpp's llama-quantize on the bf16 file.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from .train import ROOT

GGUF_PREFIX = "voxflow-rewrite"


def gguf_name(kind: str) -> str:
    return f"{GGUF_PREFIX}-{kind}.gguf"


def conversion_commands(llama_cpp: Path, merged: Path, output: Path, kinds: list[str]) -> list[list[str]]:
    return [["python", f"{llama_cpp.as_posix()}/convert_hf_to_gguf.py", merged.as_posix(), "--outtype", kind,
             "--outfile", f"{output.as_posix()}/{gguf_name(kind)}"] for kind in kinds]


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the VoxFlow rewrite model to GGUF")
    parser.add_argument("--adapter", type=Path, default=ROOT / "runs" / "qwen3.5-2b" / "adapter")
    parser.add_argument("--output", type=Path, default=ROOT / "runs" / "qwen3.5-2b" / "gguf")
    parser.add_argument("--llama-cpp", type=Path, default=Path.home() / "llama.cpp")
    parser.add_argument("--types", nargs="+", default=["q8_0", "bf16"])
    args = parser.parse_args()

    merged = args.output / "merged"
    if not (merged / "config.json").is_file():
        from unsloth import FastLanguageModel  # must be imported before transformers

        model, processor = FastLanguageModel.from_pretrained(
            model_name=str(args.adapter), max_seq_length=2048, load_in_4bit=False, load_in_16bit=True)
        model.save_pretrained_merged(str(merged), processor, save_method="merged_16bit")
    for command in conversion_commands(args.llama_cpp, merged, args.output, args.types):
        command[0] = sys.executable
        print(" ".join(command), flush=True)
        subprocess.run(command, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
