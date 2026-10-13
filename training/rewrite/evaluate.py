"""Generate predictions for a dataset split and score them.

Usage:
  python -m training.rewrite.evaluate --output training/rewrite/runs/base-2b            # untuned baseline (WSL env)
  python -m training.rewrite.evaluate --adapter training/rewrite/runs/qwen3.5-2b/adapter --output ...   # LoRA (WSL env)
  python -m training.rewrite.evaluate --endpoint http://127.0.0.1:8765/v1 --output ...   # any OpenAI-compatible server
"""

import argparse
import json
import re
import statistics
import time
import urllib.request
from pathlib import Path

from .metrics import clean_metrics, suggest_metrics
from .train import ROOT, read_rows, render_prompt

_REASONING = re.compile(r"<think>.*?</think>", re.S)


def endpoint_generator(base_url: str, model: str, opener=urllib.request.urlopen):
    url = base_url.rstrip("/") + "/chat/completions"

    def generate(messages: list[dict], max_tokens: int) -> str:
        body = json.dumps({"model": model, "messages": messages[:2], "max_tokens": max_tokens,
                           "temperature": 0}).encode("utf-8")
        request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with opener(request, timeout=120) as response:
            content = json.loads(response.read())["choices"][0]["message"]["content"]
        return _REASONING.sub("", content).strip()

    return generate


def model_generator(model_name: str, adapter: Path | None):
    from unsloth import FastLanguageModel  # must be imported before transformers
    import torch

    model, processor = FastLanguageModel.from_pretrained(
        model_name=str(adapter or model_name), max_seq_length=2048, load_in_4bit=False, load_in_16bit=True)
    tokenizer = getattr(processor, "tokenizer", processor)
    FastLanguageModel.for_inference(model)

    def generate(messages: list[dict], max_tokens: int) -> str:
        inputs = tokenizer(render_prompt(tokenizer, messages), return_tensors="pt",
                           add_special_tokens=False).to(model.device)
        output = model.generate(**inputs, max_new_tokens=max_tokens, do_sample=False)
        torch.cuda.synchronize()
        text = tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        return text.replace("<think>", "").replace("</think>", "").strip()

    return generate


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the VoxFlow rewrite model")
    parser.add_argument("--model", default="Qwen/Qwen3.5-2B")
    parser.add_argument("--adapter", type=Path, help="LoRA adapter directory; omit to evaluate the base model")
    parser.add_argument("--endpoint", help="OpenAI-compatible base URL; evaluates that server instead")
    parser.add_argument("--endpoint-model", default="voxflow-rewrite")
    parser.add_argument("--data", type=Path, default=ROOT / "build")
    parser.add_argument("--split", default="test")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-new-tokens", type=int, default=384)
    args = parser.parse_args()

    generate = (endpoint_generator(args.endpoint, args.endpoint_model) if args.endpoint
                else model_generator(args.model, args.adapter))
    rows = read_rows(args.data / f"{args.split}.jsonl")[:args.limit]
    args.output.mkdir(parents=True, exist_ok=True)
    latencies = []
    with (args.output / f"predictions-{args.split}.jsonl").open("w", encoding="utf-8") as handle:
        for index, row in enumerate(rows, 1):
            started = time.perf_counter()
            row["prediction"] = generate(row["messages"], args.max_new_tokens)
            row["latency"] = time.perf_counter() - started
            if row["meta"]["task"] == "clean" and len(row["messages"][1]["content"]) <= 50:
                latencies.append(row["latency"])
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            if index % 20 == 0:
                print(f"{index}/{len(rows)}", flush=True)

    clean = [row for row in rows if row["meta"]["task"] == "clean"]
    translate = [row for row in clean if "instr_translate" in row["meta"]["categories"]]
    try:
        import sacrebleu
        chrf = (sacrebleu.corpus_chrf([row["prediction"] for row in translate],
                                      [[row["messages"][2]["content"] for row in translate]]).score
                if translate else None)
    except ImportError:
        chrf = None
    report = {
        "model": args.endpoint or args.model,
        "adapter": str(args.adapter) if args.adapter else None,
        "split": args.split,
        "clean": clean_metrics(clean),
        "suggest": suggest_metrics([row for row in rows if row["meta"]["task"] == "suggest"]),
        "translate_chrf": chrf,
        "latency_median_s": statistics.median(latencies) if latencies else None,
    }
    (args.output / f"report-{args.split}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                           encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
