"""Fine-tune Qwen3.5 on the rewrite dataset with a bf16 LoRA (run inside the WSL training env).

Usage: python -m training.rewrite.train --output training/rewrite/runs/qwen3.5-2b
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def render_prompt(tokenizer, messages: list[dict]) -> str:
    # Training and inference share this exact prompt; the model answers directly without thinking.
    return tokenizer.apply_chat_template(messages[:2], tokenize=False, add_generation_prompt=True,
                                         enable_thinking=False)


def tokenize_example(tokenizer, row: dict, max_length: int) -> dict | None:
    prompt_ids = tokenizer(render_prompt(tokenizer, row["messages"]), add_special_tokens=False)["input_ids"]
    answer = row["messages"][2]["content"] + tokenizer.eos_token
    answer_ids = tokenizer(answer, add_special_tokens=False)["input_ids"]
    input_ids = prompt_ids + answer_ids
    if len(input_ids) > max_length:
        return None
    return {
        "input_ids": input_ids,
        "attention_mask": [1] * len(input_ids),
        "labels": [-100] * len(prompt_ids) + answer_ids,
    }


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="LoRA fine-tune for the VoxFlow rewrite model")
    parser.add_argument("--model", default="Qwen/Qwen3.5-2B")
    parser.add_argument("--data", type=Path, default=ROOT / "build")
    parser.add_argument("--output", type=Path, default=ROOT / "runs" / "qwen3.5-2b")
    parser.add_argument("--epochs", type=float, default=2)
    parser.add_argument("--max-steps", type=int, default=-1)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--max-length", type=int, default=1024)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--seed", type=int, default=3407)
    args = parser.parse_args()

    from unsloth import FastLanguageModel  # must be imported before transformers
    from datasets import Dataset
    from transformers import DataCollatorForSeq2Seq, Trainer, TrainingArguments

    model, processor = FastLanguageModel.from_pretrained(
        model_name=args.model, max_seq_length=args.max_length, load_in_4bit=False, load_in_16bit=True)
    tokenizer = getattr(processor, "tokenizer", processor)
    model = FastLanguageModel.get_peft_model(
        model, r=args.rank, lora_alpha=args.rank, lora_dropout=0, bias="none",
        target_modules=LORA_TARGETS, use_gradient_checkpointing="unsloth", random_state=args.seed)
    model.print_trainable_parameters()

    datasets, skipped = {}, {}
    for split in ("train", "valid"):
        encoded = [tokenize_example(tokenizer, row, args.max_length) for row in read_rows(args.data / f"{split}.jsonl")]
        skipped[split] = sum(example is None for example in encoded)
        datasets[split] = Dataset.from_list([example for example in encoded if example is not None])
    print(f"train {len(datasets['train'])} | valid {len(datasets['valid'])} | skipped {skipped}")

    args.output.mkdir(parents=True, exist_ok=True)
    trainer = Trainer(
        model=model,
        args=TrainingArguments(
            output_dir=str(args.output / "checkpoints"),
            per_device_train_batch_size=args.batch_size,
            per_device_eval_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            num_train_epochs=args.epochs,
            max_steps=args.max_steps,
            learning_rate=args.learning_rate,
            lr_scheduler_type="cosine",
            warmup_ratio=0.03,
            logging_steps=10,
            eval_strategy="epoch",
            save_strategy="epoch",
            save_total_limit=1,
            bf16=True,
            optim="adamw_8bit",
            seed=args.seed,
            report_to="none",
            remove_unused_columns=False,
        ),
        train_dataset=datasets["train"],
        eval_dataset=datasets["valid"],
        data_collator=DataCollatorForSeq2Seq(tokenizer, padding=True, label_pad_token_id=-100),
    )
    result = trainer.train()
    evaluation = trainer.evaluate()
    model.save_pretrained(str(args.output / "adapter"))
    processor.save_pretrained(str(args.output / "adapter"))
    summary = {"args": {key: str(value) for key, value in vars(args).items()}, "skipped": skipped,
               "train": result.metrics, "eval": evaluation}
    (args.output / "train_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
