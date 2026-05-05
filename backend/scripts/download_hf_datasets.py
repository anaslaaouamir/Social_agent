"""Download project datasets from Hugging Face instead of Kaggle.

Usage examples:
    python scripts/download_hf_datasets.py
    python scripts/download_hf_datasets.py sentiment140 toxic
    python scripts/download_hf_datasets.py instagram --output-dir ./data/datasets
"""
from __future__ import annotations

import argparse
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
DEFAULT_OUTPUT_DIR = BACKEND_DIR / "data" / "datasets"


DATASETS = {
    "sentiment140": {
        "repo_id": "stanfordnlp/sentiment140",
        "description": "1.6M tweets labellises sentiment",
    },
    "toxic": {
        "repo_id": "thesofakillers/jigsaw-toxic-comment-classification-challenge",
        "description": "Jigsaw toxic comments (224k lignes)",
    },
    "instagram": {
        "repo_id": "vargr/main_instagram",
        "description": "Posts Instagram avec likes/comments/followers",
    },
    "spam_comments": {
        "repo_id": "merve/spam-classification-dataset",
        "description": "YouTube spam comments dataset",
    },
    "social_engagement": {
        "repo_id": "shawhin/social-media-data",
        "description": "Metriques d'engagement multi-plateforme",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download project datasets from Hugging Face Hub."
    )
    parser.add_argument(
        "datasets",
        nargs="*",
        choices=sorted(DATASETS.keys()),
        help="Datasets to download. Defaults to all known datasets.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Base directory where datasets are stored.",
    )
    return parser.parse_args()


def download_dataset(name: str, output_dir: Path) -> Path:
    from huggingface_hub import snapshot_download

    meta = DATASETS[name]
    target_dir = output_dir / name
    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"[download] {name}: {meta['repo_id']}")
    snapshot_download(
        repo_id=meta["repo_id"],
        repo_type="dataset",
        local_dir=target_dir,
    )
    return target_dir


def main() -> None:
    args = parse_args()
    selected_datasets = args.datasets or sorted(DATASETS.keys())
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import huggingface_hub  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: huggingface_hub. "
            "Install backend requirements inside mon_projet311 first."
        ) from exc

    print(f"[target] {output_dir}")
    for name in selected_datasets:
        path = download_dataset(name, output_dir)
        print(f"[ok] {name} -> {path}")

    print("")
    print("Installed datasets:")
    for name in selected_datasets:
        meta = DATASETS[name]
        print(f"- {name}: {meta['repo_id']} ({meta['description']})")


if __name__ == "__main__":
    main()
