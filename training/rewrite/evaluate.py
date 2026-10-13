"""Generate predictions for a dataset split and score them (run inside the WSL training env).

Usage:
  python -m training.rewrite.evaluate --output training/rewrite/runs/base-2b            # untuned baseline
  python -m training.rewrite.evaluate --adapter training/rewrite/runs/qwen3.5-2b/adapter --output training/rewrite/runs/qwen3.5-2b
"""

import argparse
import json
import statistics
import time
from pathlib import Path

from .metrics import clean_metrics, suggest_metrics
from .train import ROOT, read_rows, render_prompt


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the VoxFlow rewrite model")
    parser.add_argument("--model", default="Qwen/Qwen3.5-2B")
    parser.add_argument("--adapter", type=Path, help="LoRA adapter directory; omit to evaluate the base model")
    parser.add_argument("--data", type=Path, default=ROOT / "build")
    parser.add_argument("--split", default="test")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-new-tokens", type=int, default=384)
    args = parser.parse_args()

    from unsloth import FastLanguageModel  # must be imported before transformers
    import sacrebleu
    import torch

    model, processor = FastLanguageModel.from_pretrained(
        model_name=str(args.adapter or args.model), max_seq_length=2048, load_in_4bit=False, load_in_16bit=True)
    tokenizer = getattr(processor, "tokenizer", processor)
    FastLanguageModel.for_inference(model)

    rows = read_rows(args.data / f"{args.split}.jsonl")[:args.limit]
    args.output.mkdir(parents=True, exist_ok=True)
    latencies = []
    with (args.output / f"predictions-{args.split}.jsonl").open("w", encoding="utf-8") as handle:
        for index, row in enumerate(rows, 1):
            inputs = tokenizer(render_prompt(tokenizer, row["messages"]), return_tensors="pt",
                               add_special_tokens=False).to(model.device)
            torch.cuda.synchronize()
            started = time.perf_counter()
            output = model.generate(**inputs, max_new_tokens=args.max_new_tokens, do_sample=False)
            torch.cuda.synchronize()
            elapsed = time.perf_counter() - started
            text = tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
            row["prediction"] = text.replace("<think>", "").replace("</think>", "").strip()
            row["latency"] = elapsed
            if row["meta"]["task"] == "clean" and len(row["messages"][1]["content"]) <= 50:
                latencies.append(elapsed)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            if index % 20 == 0:
                print(f"{index}/{len(rows)}", flush=True)

    clean = [row for row in rows if row["meta"]["task"] == "clean"]
    translate = [row for row in clean if "instr_translate" in row["meta"]["categories"]]
    report = {
        "model": args.model,
        "adapter": str(args.adapter) if args.adapter else None,
        "split": args.split,
        "clean": clean_metrics(clean),
        "suggest": suggest_metrics([row for row in rows if row["meta"]["task"] == "suggest"]),
        "translate_chrf": sacrebleu.corpus_chrf([row["prediction"] for row in translate],
                                                [[row["messages"][2]["content"] for row in translate]]).score
        if translate else None,
        "latency_median_s": statistics.median(latencies) if latencies else None,
    }
    (args.output / f"report-{args.split}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                           encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
