#!/usr/bin/env python3
"""Fine-tune Tibetan-Llama2-7B using QLoRA for Tibetan Grammatical Error Correction (GEC).

Loads parallel Tibetan sentence pairs from Data/TrainingData/grammar_correction_train.jsonl,
applies 4-bit QLoRA adapters to target projection layers (q_proj, k_proj, v_proj, o_proj),
and saves the trained LoRA adapter to models/llama2_gec_lora.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from teea.core.logging import get_logger

logger = get_logger(__name__)


def train_llama_gec(
    dataset_path: Path,
    output_dir: Path,
    base_model_path: Path,
    epochs: int = 1,
    batch_size: int = 1,
    gradient_accumulation_steps: int = 8,
    learning_rate: float = 2e-4,
    max_samples: int | None = None,
) -> None:
    """Fine-tune Tibetan-Llama2-7B with QLoRA."""
    import torch
    try:
        from datasets import Dataset
    except ImportError:
        Dataset = None

    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        DataCollatorForLanguageModeling,
        Trainer,
        TrainingArguments,
    )

    sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 80)
    print("STARTING TIBETAN LLAMA2 GEC QLORA FINE-TUNING")
    print("=" * 80)
    print(f"[*] Training dataset : {dataset_path}")
    print(f"[*] Base model path  : {base_model_path}")
    print(f"[*] Output directory : {output_dir}")
    print(f"[*] Device           : {'cuda' if torch.cuda.is_available() else 'cpu'}")

    # 1. Load Tokenizer
    tokenizer = AutoTokenizer.from_pretrained(str(base_model_path), trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # 2. Prepare Parallel Dataset
    if not dataset_path.exists():
        raise FileNotFoundError(f"Training dataset not found at {dataset_path}.")

    records = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if max_samples and max_samples < len(records):
        records = records[:max_samples]

    print(f"[✓] Loaded {len(records):,} training pairs for GEC QLoRA.")

    formatted_texts = []
    prompt_template = "ཞུ་དག: {incorrect}\nདག་ཆ: {correct}"
    for rec in records:
        inc = rec.get("incorrect", "").strip()
        cor = rec.get("correct", "").strip()
        if inc and cor:
            text = prompt_template.format(incorrect=inc, correct=cor) + tokenizer.eos_token
            formatted_texts.append(text)

    if Dataset is not None:
        raw_dataset = Dataset.from_list([{"text": t} for t in formatted_texts])
        def tokenize_function(examples):
            return tokenizer(
                examples["text"],
                truncation=True,
                max_length=128,
                padding=False,
            )
        tokenized_dataset = raw_dataset.map(tokenize_function, batched=True, remove_columns=["text"])
    else:
        class PyTorchDataset(torch.utils.data.Dataset):
            def __init__(self, texts, tok):
                self.encodings = [tok(t, truncation=True, max_length=128, padding=False) for t in texts]
            def __len__(self):
                return len(self.encodings)
            def __getitem__(self, idx):
                return self.encodings[idx]

        tokenized_dataset = PyTorchDataset(formatted_texts, tokenizer)

    # 3. Configure 4-Bit QLoRA & Load Base Model
    print("[*] Loading base model in 4-bit precision (BitsAndBytesConfig)...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    model = AutoModelForCausalLM.from_pretrained(
        str(base_model_path),
        quantization_config=bnb_config if torch.cuda.is_available() else None,
        device_map="auto" if torch.cuda.is_available() else None,
        trust_remote_code=True,
    )

    model.config.use_cache = False
    if torch.cuda.is_available():
        model = prepare_model_for_kbit_training(model)
        model.gradient_checkpointing_enable()

    # 4. LoRA Adapter Configuration
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # 5. Training Arguments
    training_args = TrainingArguments(
        output_dir=str(output_dir / "checkpoints"),
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=gradient_accumulation_steps,
        learning_rate=learning_rate,
        num_train_epochs=epochs,
        logging_steps=10,
        save_strategy="epoch",
        optim="paged_adamw_8bit" if torch.cuda.is_available() else "adamw_torch",
        fp16=torch.cuda.is_available(),
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
    )

    # 6. Run Training & Save Adapter
    print(f"[*] Fine-tuning QLoRA adapter for {epochs} epoch(s)...")
    trainer.train()

    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    print("=" * 80)
    print(f"[SUCCESS] QLoRA Fine-Tuning Complete! Saved LoRA adapter to: {output_dir}")
    print("=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune Tibetan-Llama2-7B using QLoRA for GEC")
    parser.add_argument("--dataset", type=str, default="Data/TrainingData/grammar_correction_train.jsonl")
    parser.add_argument("--output-dir", type=str, default="models/llama2_gec_lora")
    parser.add_argument("--base-model", type=str, default="models/Tibetan-Llama2-7B")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--max-samples", type=int, default=None)
    args = parser.parse_args()

    train_llama_gec(
        dataset_path=PROJECT_ROOT / args.dataset,
        output_dir=PROJECT_ROOT / args.output_dir,
        base_model_path=PROJECT_ROOT / args.base_model,
        epochs=args.epochs,
        batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.learning_rate,
        max_samples=args.max_samples,
    )


if __name__ == "__main__":
    main()
