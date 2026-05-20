"""
Fine-tune multilingual BERT models on local project datasets.

Usage examples:
  python scripts/train_mbert.py --task sentiment
  python scripts/train_mbert.py --task toxic
  python scripts/train_mbert.py --task all
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import traceback

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import numpy as np
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    Trainer,
    TrainingArguments,
)

from services.dataset_loader import load_quadrilingual_sentiment, load_toxic_comments

MODEL_NAME = "bert-base-multilingual-uncased"
MODEL_DIR = Path("./data/models")
SENTIMENT_OUT = MODEL_DIR / "mbert_sentiment_finetuned"
TOXIC_OUT = MODEL_DIR / "mbert_toxic_finetuned"
LOG_DIR = MODEL_DIR / "training_logs"

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def _compute_metrics(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    return {
        "accuracy": accuracy_score(labels, preds),
        "f1_weighted": f1_score(labels, preds, average="weighted"),
    }


def _build_dataset(texts, labels, tokenizer):
    class SimpleDataset:
        def __init__(self, encodings, labels_):
            self.encodings = encodings
            self.labels = labels_

        def __len__(self):
            return len(self.labels)

        def __getitem__(self, idx):
            item = {key: value[idx] for key, value in self.encodings.items()}
            item["labels"] = self.labels[idx]
            return item

    encodings = tokenizer(
        list(texts),
        truncation=True,
        max_length=256,
    )
    return SimpleDataset(encodings, list(labels))


def _build_training_args(
    output_dir: Path,
    epochs: float,
    train_batch_size: int,
    eval_batch_size: int,
    logging_steps: int,
    save_steps: int,
    use_cpu: bool,
):
    return TrainingArguments(
        output_dir=str(output_dir),
        overwrite_output_dir=False,
        eval_strategy="steps",
        save_strategy="steps",
        eval_steps=save_steps,
        save_steps=save_steps,
        logging_steps=logging_steps,
        per_device_train_batch_size=train_batch_size,
        per_device_eval_batch_size=eval_batch_size,
        num_train_epochs=epochs,
        learning_rate=2e-5,
        weight_decay=0.01,
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="f1_weighted",
        report_to="none",
        dataloader_num_workers=0,
        dataloader_pin_memory=False,
        use_cpu=use_cpu,
    )


def _latest_checkpoint(output_dir: Path) -> str | None:
    checkpoints = sorted(output_dir.glob("checkpoint-*"), key=lambda p: p.stat().st_mtime)
    return str(checkpoints[-1]) if checkpoints else None


def train_sentiment(
    max_rows: int = 60000,
    epochs: float = 1.0,
    train_batch_size: int = 8,
    eval_batch_size: int = 8,
    logging_steps: int = 50,
    save_steps: int = 500,
    resume: bool = False,
    use_cpu: bool = True,
):
    df = load_quadrilingual_sentiment(max_rows=max_rows)
    label_map = {"negative": 0, "neutral": 1, "positive": 2}
    df["label_id"] = df["sentiment_label"].map(label_map)

    train_df, eval_df = train_test_split(
        df[["text", "label_id"]],
        test_size=0.1,
        random_state=42,
        stratify=df["label_id"],
    )

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME,
        num_labels=3,
        id2label={0: "negative", 1: "neutral", 2: "positive"},
        label2id=label_map,
    )

    train_dataset = _build_dataset(train_df["text"], train_df["label_id"], tokenizer)
    eval_dataset = _build_dataset(eval_df["text"], eval_df["label_id"], tokenizer)
    args = _build_training_args(
        output_dir=SENTIMENT_OUT,
        epochs=epochs,
        train_batch_size=train_batch_size,
        eval_batch_size=eval_batch_size,
        logging_steps=logging_steps,
        save_steps=save_steps,
        use_cpu=use_cpu,
    )
    trainer = Trainer(
        model=model,
        args=args,
        tokenizer=tokenizer,
        data_collator=DataCollatorWithPadding(tokenizer=tokenizer),
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        compute_metrics=_compute_metrics,
    )
    resume_checkpoint = _latest_checkpoint(SENTIMENT_OUT) if resume else None
    print(f"[sentiment] train={len(train_dataset)} eval={len(eval_dataset)} rows={len(df)}")
    if resume_checkpoint:
        print(f"[sentiment] resume from {resume_checkpoint}")
    trainer.train(resume_from_checkpoint=resume_checkpoint)
    trainer.save_model(str(SENTIMENT_OUT))
    tokenizer.save_pretrained(str(SENTIMENT_OUT))
    print(f"[sentiment] model saved to {SENTIMENT_OUT}")


def train_toxic(
    max_rows: int = 80000,
    epochs: float = 1.0,
    train_batch_size: int = 8,
    eval_batch_size: int = 8,
    logging_steps: int = 50,
    save_steps: int = 500,
    resume: bool = False,
    use_cpu: bool = True,
):
    df = load_toxic_comments(max_rows=max_rows)
    train_df, eval_df = train_test_split(
        df[["text", "is_toxic"]],
        test_size=0.1,
        random_state=42,
        stratify=df["is_toxic"],
    )

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME,
        num_labels=2,
        id2label={0: "clean", 1: "toxic"},
        label2id={"clean": 0, "toxic": 1},
    )

    train_dataset = _build_dataset(train_df["text"], train_df["is_toxic"], tokenizer)
    eval_dataset = _build_dataset(eval_df["text"], eval_df["is_toxic"], tokenizer)
    args = _build_training_args(
        output_dir=TOXIC_OUT,
        epochs=epochs,
        train_batch_size=train_batch_size,
        eval_batch_size=eval_batch_size,
        logging_steps=logging_steps,
        save_steps=save_steps,
        use_cpu=use_cpu,
    )
    trainer = Trainer(
        model=model,
        args=args,
        tokenizer=tokenizer,
        data_collator=DataCollatorWithPadding(tokenizer=tokenizer),
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        compute_metrics=_compute_metrics,
    )
    resume_checkpoint = _latest_checkpoint(TOXIC_OUT) if resume else None
    print(f"[toxic] train={len(train_dataset)} eval={len(eval_dataset)} rows={len(df)}")
    if resume_checkpoint:
        print(f"[toxic] resume from {resume_checkpoint}")
    trainer.train(resume_from_checkpoint=resume_checkpoint)
    trainer.save_model(str(TOXIC_OUT))
    tokenizer.save_pretrained(str(TOXIC_OUT))
    print(f"[toxic] model saved to {TOXIC_OUT}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=["sentiment", "toxic", "all"], default="all")
    parser.add_argument("--sentiment-rows", type=int, default=60000)
    parser.add_argument("--toxic-rows", type=int, default=80000)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--train-batch-size", type=int, default=8)
    parser.add_argument("--eval-batch-size", type=int, default=8)
    parser.add_argument("--logging-steps", type=int, default=50)
    parser.add_argument("--save-steps", type=int, default=500)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--use-cpu", action="store_true", default=True)
    args = parser.parse_args()

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if args.task in {"sentiment", "all"}:
        train_sentiment(
            max_rows=args.sentiment_rows,
            epochs=args.epochs,
            train_batch_size=args.train_batch_size,
            eval_batch_size=args.eval_batch_size,
            logging_steps=args.logging_steps,
            save_steps=args.save_steps,
            resume=args.resume,
            use_cpu=args.use_cpu,
        )
    if args.task in {"toxic", "all"}:
        train_toxic(
            max_rows=args.toxic_rows,
            epochs=args.epochs,
            train_batch_size=args.train_batch_size,
            eval_batch_size=args.eval_batch_size,
            logging_steps=args.logging_steps,
            save_steps=args.save_steps,
            resume=args.resume,
            use_cpu=args.use_cpu,
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOG_DIR / "last_error.log"
        error_text = traceback.format_exc()
        log_path.write_text(error_text, encoding="utf-8")
        print(error_text)
        print(f"[training] error log saved to {log_path}")
        raise
