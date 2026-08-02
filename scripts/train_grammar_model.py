#!/usr/bin/env python3
"""Fine-tune TiBERT for Tibetan Grammatical Error Correction (GEC).

Loads parallel pairs from Data/TrainingData/grammar_correction_train.jsonl,
initializes an EncoderDecoderModel using TiBERT weights, trains sequence-to-sequence
correction, and saves the final model to models/tibert-grammar-correction-final.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from teea.core.logging import get_logger

logger = get_logger(__name__)


def train_model(
    dataset_path: Path,
    output_dir: Path,
    base_model_path: Path,
    epochs: int = 3,
    batch_size: int = 16,
    learning_rate: float = 5e-5,
) -> None:
    """Fine-tune TiBERT for sequence-to-sequence GEC."""
    import torch
    from torch.utils.data import Dataset, DataLoader
    from transformers import BertTokenizer, EncoderDecoderModel, BertConfig

    print("=" * 80)
    print("STARTING TIBERT GRAMMAR CORRECTION MODEL TRAINING")
    print("=" * 80)
    print(f"[*] Training dataset : {dataset_path}")
    print(f"[*] Base model path  : {base_model_path}")
    print(f"[*] Output directory : {output_dir}")
    print(f"[*] Device           : {'cuda' if torch.cuda.is_available() else 'cpu'}")

    # 1. Load Tokenizer
    if base_model_path.exists():
        tokenizer = BertTokenizer.from_pretrained(str(base_model_path))
    else:
        tokenizer = BertTokenizer.from_pretrained("bert-base-multilingual-cased")

    # 2. Load Parallel Dataset
    if not dataset_path.exists():
        raise FileNotFoundError(f"Training dataset not found at {dataset_path}. Run generate_grammar_training_data.py first.")

    records = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    print(f"[✓] Loaded {len(records):,} training pairs.")

    class GECDataset(Dataset):
        def __init__(self, pairs, tok, max_len=128):
            self.pairs = pairs
            self.tok = tok
            self.max_len = max_len

        def __len__(self):
            return len(self.pairs)

        def __getitem__(self, idx):
            item = self.pairs[idx]
            inp = self.tok(item["incorrect"], truncation=True, max_length=self.max_len, padding="max_length", return_tensors="pt")
            tgt = self.tok(item["correct"], truncation=True, max_length=self.max_len, padding="max_length", return_tensors="pt")
            
            labels = tgt["input_ids"].squeeze(0)
            labels[labels == self.tok.pad_token_id] = -100
            
            return {
                "input_ids": inp["input_ids"].squeeze(0),
                "attention_mask": inp["attention_mask"].squeeze(0),
                "labels": labels,
            }

    train_data = GECDataset(records, tokenizer)
    dataloader = DataLoader(train_data, batch_size=batch_size, shuffle=True)

    # 3. Construct EncoderDecoderModel
    if base_model_path.exists():
        model = EncoderDecoderModel.from_encoder_decoder_pretrained(str(base_model_path), str(base_model_path))
    else:
        model = EncoderDecoderModel.from_encoder_decoder_pretrained("bert-base-multilingual-cased", "bert-base-multilingual-cased")

    model.config.decoder_start_token_id = tokenizer.cls_token_id
    model.config.eos_token_id = tokenizer.sep_token_id
    model.config.pad_token_id = tokenizer.pad_token_id

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)

    # 4. Training Loop
    model.train()
    print(f"[*] Training for {epochs} epochs over {len(dataloader):,} batches per epoch...")
    
    for epoch in range(1, epochs + 1):
        total_loss = 0.0
        for step, batch in enumerate(dataloader, 1):
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)

            optimizer.zero_grad()
            outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
            loss = outputs.loss
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            if step % 50 == 0 or step == len(dataloader):
                avg_loss = total_loss / step
                print(f"  Epoch [{epoch}/{epochs}] Step [{step}/{len(dataloader)}] - Loss: {avg_loss:.4f}")

    # 5. Save Final Model Artifacts
    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    print("=" * 80)
    print(f"[SUCCESS] Training Complete! Saved TiBERT GEC Model to: {output_dir}")
    print("=" * 80)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Train TiBERT Grammar Correction Model")
    parser.add_argument("--dataset", type=str, default="Data/TrainingData/grammar_correction_train.jsonl")
    parser.add_argument("--output-dir", type=str, default="models/tibert-grammar-correction-final")
    parser.add_argument("--base-model", type=str, default="TiBERT")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=5e-5)
    args = parser.parse_args()

    train_model(
        dataset_path=PROJECT_ROOT / args.dataset,
        output_dir=PROJECT_ROOT / args.output_dir,
        base_model_path=PROJECT_ROOT / args.base_model,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
    )


if __name__ == "__main__":
    main()
