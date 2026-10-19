"""Fine-tune the rewrite model with LoRA (run inside the WSL training env).

Usage:
  python -m training.rewrite.train --output training/rewrite/runs/qwen3.5-2b
  python -m training.rewrite.train --model unsloth/gemma-4-E2B-it --load-in-4bit \
      --output training/rewrite/runs/gemma-4-e2b
Qwen3.5 trains as a bf16 LoRA (Unsloth advises against 4-bit for it). Gemma 4 E2B has about 5B parameters
including its per-layer embeddings, too many for bf16 on a 6 GB GPU, so it trains as a text-only QLoRA.
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# Qwen3.5 mixes full attention (q/k/v/o) with linear-attention layers (in_proj_qkv/in_proj_z/out_proj).
LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "in_proj_qkv", "in_proj_z", "out_proj",
                "gate_proj", "up_proj", "down_proj"]


def is_gemma(model_name: str) -> bool:
    return "gemma" in model_name.lower()


# Gemma 4 E2B's per-layer embedding table (4.4 GB in bf16) is never quantized and does not fit a 6 GB GPU
# next to everything else. It only serves lookups, so it stays in system memory; the rest goes to the GPU.
GEMMA_DEVICE_MAP = {"model.embed_tokens_per_layer": "cpu", "model.embed_tokens": 0, "model.layers": 0,
                    "model.norm": 0, "model.per_layer_model_projection": 0, "model.per_layer_projection_norm": 0,
                    "model.rotary_emb": 0, "lm_head": 0}


def keep_lookup_on_cpu(embedding, device: str = "cuda:0") -> None:
    """Run an embedding lookup on the CPU and hand the result to the GPU.

    accelerate's CPU offload would copy the whole table to the GPU on every forward pass instead.
    """
    import torch
    from accelerate.hooks import remove_hook_from_module

    hook = getattr(embedding, "_hf_hook", None)
    weight = embedding.weight if embedding.weight.device.type != "meta" else hook.weights_map["weight"]
    remove_hook_from_module(embedding)
    embedding.weight = torch.nn.Parameter(weight.to("cpu"), requires_grad=False)
    embedding.register_forward_pre_hook(lambda module, args: tuple(arg.to("cpu") for arg in args))
    embedding.register_forward_hook(lambda module, args, output: output.to(device))


def load_model(model_name: str, max_length: int, load_in_4bit: bool, rank: int = 0, seed: int = 3407,
               gemma: bool | None = None):
    """Load the base model (or a saved adapter); with rank > 0 also attach a fresh LoRA."""
    precision = {"load_in_4bit": load_in_4bit, "load_in_16bit": not load_in_4bit}
    if is_gemma(model_name) if gemma is None else gemma:
        from unsloth import FastModel  # must be imported before transformers

        placement = {"device_map": "cpu"}
        if load_in_4bit:
            import torch
            from transformers import BitsAndBytesConfig

            # Quantize the original weights here: a pre-quantized checkpoint brings its own config, which
            # forbids placing any module on the CPU.
            placement = {"device_map": GEMMA_DEVICE_MAP, "quantization_config": BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=torch.bfloat16, llm_int8_enable_fp32_cpu_offload=True)}
        model, processor = FastModel.from_pretrained(model_name=model_name, max_seq_length=max_length,
                                                     text_only=True, use_exact_model_name=True,
                                                     **precision, **placement)
        if load_in_4bit:
            keep_lookup_on_cpu(model.model.embed_tokens_per_layer)
        if rank:
            # Language layers only: the vision and audio towers are not loaded.
            model = FastModel.get_peft_model(
                model, r=rank, lora_alpha=rank, lora_dropout=0, bias="none", finetune_vision_layers=False,
                finetune_language_layers=True, finetune_attention_modules=True, finetune_mlp_modules=True,
                use_gradient_checkpointing="unsloth", random_state=seed)
        return model, processor
    from unsloth import FastLanguageModel  # must be imported before transformers

    model, processor = FastLanguageModel.from_pretrained(model_name=model_name, max_seq_length=max_length,
                                                         **precision)
    if rank:
        model = FastLanguageModel.get_peft_model(
            model, r=rank, lora_alpha=rank, lora_dropout=0, bias="none",
            target_modules=LORA_TARGETS, use_gradient_checkpointing="unsloth", random_state=seed)
    return model, processor


def render_prompt(tokenizer, messages: list[dict]) -> str:
    # Training and inference share this exact prompt; the model answers directly without thinking.
    return tokenizer.apply_chat_template(messages[:2], tokenize=False, add_generation_prompt=True,
                                         enable_thinking=False)


def answer_end(tokenizer, gemma: bool) -> str:
    # Gemma's chat template closes the model's turn with <turn|>, not with <eos>.
    return "<turn|>" if gemma else tokenizer.eos_token


def tokenize_example(tokenizer, row: dict, max_length: int, end: str | None = None) -> dict | None:
    prompt_ids = tokenizer(render_prompt(tokenizer, row["messages"]), add_special_tokens=False)["input_ids"]
    answer = row["messages"][2]["content"] + (end or tokenizer.eos_token)
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
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--load-in-4bit", action="store_true", help="QLoRA: load the base model in 4-bit")
    parser.add_argument("--resume", action="store_true", help="continue from the latest checkpoint in --output")
    args = parser.parse_args()

    import os

    # The 6 GB laptop GPU is shared with the desktop; avoid fragmentation-driven OOMs.
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    model, processor = load_model(args.model, args.max_length, args.load_in_4bit, args.rank, args.seed)
    from datasets import Dataset
    from transformers import DataCollatorForSeq2Seq, Trainer, TrainingArguments

    tokenizer = getattr(processor, "tokenizer", processor)
    model.print_trainable_parameters()

    datasets, skipped = {}, {}
    for split in ("train", "valid"):
        end = answer_end(tokenizer, is_gemma(args.model))
        encoded = [tokenize_example(tokenizer, row, args.max_length, end)
                   for row in read_rows(args.data / f"{split}.jsonl")]
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
            warmup_steps=20,
            logging_steps=10,
            eval_strategy="epoch",
            save_strategy="steps",
            save_steps=100,
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
    result = trainer.train(resume_from_checkpoint=args.resume or None)
    evaluation = trainer.evaluate()
    model.save_pretrained(str(args.output / "adapter"))
    processor.save_pretrained(str(args.output / "adapter"))
    import torch
    summary = {"args": {key: str(value) for key, value in vars(args).items()}, "skipped": skipped,
               "train": result.metrics, "eval": evaluation,
               "max_memory_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2)}
    (args.output / "train_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
