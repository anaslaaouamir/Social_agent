"""DatasetLoader - lecture, nettoyage, feature engineering pour ML."""
from __future__ import annotations

import logging
import re
import zipfile
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DATASET_DIR = Path("./data/datasets")


def clean_text(text: str) -> str:
    """Nettoie un texte brut : URLs, mentions, emojis parasites, espaces."""
    text = re.sub(r"http\S+|www\.\S+", " ", str(text))
    text = re.sub(r"@\w+", " ", text)
    text = re.sub(r"#(\w+)", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_text_features(df: pd.DataFrame, text_col: str = "text") -> pd.DataFrame:
    """Feature engineering sur texte : longueur, emojis, hashtags, mentions."""
    df = df.copy()
    if text_col not in df.columns:
        df[text_col] = ""
    df[text_col] = df[text_col].fillna("").astype(str)
    df["caption_length"] = df[text_col].str.len().clip(0, 2200)
    df["word_count"] = df[text_col].str.split().str.len().fillna(0).astype(int)
    df["hashtag_count"] = df[text_col].str.count(r"#\w+").clip(0, 30)
    df["mention_count"] = df[text_col].str.count(r"@\w+")
    df["has_emoji"] = df[text_col].str.contains(r"[\U0001F300-\U0001FAFF]", regex=True, na=False).astype(int)
    df["has_mention"] = (df["mention_count"] > 0).astype(int)
    df["has_question"] = df[text_col].str.contains(r"\?", na=False).astype(int)
    df["url_count"] = df[text_col].str.count(r"http[s]?://")
    df["exclamation"] = df[text_col].str.count(r"!")
    if "hour" in df.columns:
        df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
        df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    if "day_of_week" in df.columns:
        df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
        df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)
        df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    return df


def load_sentiment140(max_rows: int = 200_000) -> pd.DataFrame:
    """Charge Sentiment140 et remappe les labels en negatif/neutre/positif."""
    try:
        from datasets import load_dataset

        ds = load_dataset("stanfordnlp/sentiment140", split="train")
        df = ds.to_pandas().sample(min(max_rows, len(ds)), random_state=42)
        df = df.rename(columns={"sentiment": "raw_sentiment"})
    except Exception:
        zip_path = DATASET_DIR / "sentiment140.zip"
        if not zip_path.exists():
            raise FileNotFoundError("Dataset sentiment140 introuvable. Ajoutez sentiment140.zip dans data/datasets/")

        with zipfile.ZipFile(zip_path) as archive:
            csv_name = next(
                (name for name in archive.namelist() if name.lower().endswith(".csv")),
                None,
            )
            if not csv_name:
                raise FileNotFoundError("Aucun CSV trouve dans sentiment140.zip")
            with archive.open(csv_name) as handle:
                df = pd.read_csv(
                    handle,
                    header=None,
                    encoding="latin-1",
                    names=["raw_sentiment", "id", "date", "query", "user", "text"],
                )

        if len(df) > max_rows:
            df = df.sample(n=max_rows, random_state=42)

    df["text"] = df["text"].astype(str).apply(clean_text)
    df = df[df["text"].str.len() > 5].copy()
    df["sentiment_label"] = df["raw_sentiment"].map({0: "negative", 2: "neutral", 4: "positive"})
    df = df.dropna(subset=["sentiment_label"])
    logger.info("Sentiment140: %s lignes | %s", len(df), df["sentiment_label"].value_counts().to_dict())
    return df[["text", "sentiment_label"]].reset_index(drop=True)


def load_toxic_comments(max_rows: int = 100_000) -> pd.DataFrame:
    """Charge Jigsaw Toxic Comments avec fallback CSV local."""
    from datasets import load_dataset

    try:
        ds = load_dataset("thesofakillers/jigsaw-toxic-comment-classification-challenge", split="train")
        df = ds.to_pandas().sample(min(max_rows, len(ds)), random_state=42)
    except Exception:
        csv_path = DATASET_DIR / "toxic" / "train.csv"
        if not csv_path.exists():
            raise FileNotFoundError("Dataset toxic introuvable. Lancez download_hf_datasets.py")
        df = pd.read_csv(csv_path, nrows=max_rows)

    df["text"] = df["comment_text"].astype(str).apply(clean_text)
    df["is_toxic"] = (
        df[["toxic", "severe_toxic", "obscene", "threat", "insult", "identity_hate"]].max(axis=1) > 0
    ).astype(int)
    df = df[df["text"].str.len() > 5].copy()
    logger.info("Toxic: %s lignes | %s", len(df), df["is_toxic"].value_counts().to_dict())
    return df[["text", "is_toxic"]].reset_index(drop=True)


def load_instagram_dataset() -> Optional[pd.DataFrame]:
    """Charge le dataset Instagram HF pour les features d'engagement."""
    try:
        try:
            from datasets import load_dataset

            ds = load_dataset("vargr/main_instagram", split="train")
            df = ds.to_pandas()
        except Exception:
            parquet_files = sorted((DATASET_DIR / "instagram").glob("**/*.parquet"))
            if not parquet_files:
                raise
            frames = [pd.read_parquet(path) for path in parquet_files]
            df = pd.concat(frames, ignore_index=True)

        rename_map = {
            "likesCount": "likes",
            "commentsCount": "comments_count",
            "followersCount": "followers",
            "caption": "text",
            "type": "content_type",
            "timestamp": "posted_at",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
        if "likes" in df.columns and "followers" in df.columns:
            df["engagement_rate"] = (
                (df.get("likes", 0) + df.get("comments_count", 0))
                / df["followers"].clip(1)
            ).clip(0, 0.5)
        if "text" in df.columns:
            df["text"] = df["text"].fillna("").astype(str).apply(clean_text)
            df = extract_text_features(df)
        df["platform"] = "instagram"
        logger.info("Instagram dataset: %s lignes", len(df))
        return df
    except Exception as exc:
        logger.warning("Instagram dataset non disponible: %s", exc)
        return None


def build_engagement_training_df(
    instagram_df: Optional[pd.DataFrame] = None,
    synthetic_size: int = 20_000,
) -> pd.DataFrame:
    """Construit le DataFrame d'entrainement de l'EngagementPredictor."""
    platforms = ["instagram", "tiktok", "facebook", "twitter", "linkedin", "threads", "youtube", "pinterest"]
    content_types = ["image", "video", "carousel", "reel", "story"]
    base_er = {"instagram": 0.038, "tiktok": 0.058, "facebook": 0.012, "twitter": 0.009, "linkedin": 0.022, "threads": 0.026, "youtube": 0.018, "pinterest": 0.021}
    ct_mult = {"reel": 1.8, "video": 1.5, "carousel": 1.3, "image": 1.0, "story": 0.7}

    rng = np.random.default_rng(42)
    plat = rng.choice(platforms, synthetic_size)
    ct = rng.choice(content_types, synthetic_size)
    hour = rng.integers(0, 24, synthetic_size)
    dow = rng.integers(0, 7, synthetic_size)
    followers = rng.integers(1000, 1_000_000, synthetic_size)
    caption_length = rng.integers(10, 2200, synthetic_size)
    hashtag_count = rng.integers(0, 30, synthetic_size)
    has_emoji = rng.integers(0, 2, synthetic_size)
    has_mention = rng.integers(0, 2, synthetic_size)
    has_question = rng.integers(0, 2, synthetic_size)

    time_bonus = np.where((hour >= 18) & (hour <= 21), 1.2, np.where((hour < 8) | (hour > 23), 0.85, 1.0))
    er_base = np.array([base_er[p] for p in plat])
    er_ct = np.array([ct_mult[c] for c in ct])
    er_syn = (er_base * er_ct * time_bonus + rng.normal(0, 0.005, synthetic_size)).clip(0.001, 0.5)

    synth = pd.DataFrame({
        "platform": plat,
        "content_type": ct,
        "hour": hour,
        "day_of_week": dow,
        "caption_length": caption_length,
        "hashtag_count": hashtag_count,
        "has_emoji": has_emoji,
        "has_mention": has_mention,
        "has_question": has_question,
        "followers": followers,
        "historical_avg_er": er_syn * rng.uniform(0.8, 1.1, synthetic_size),
        "engagement_rate": er_syn,
        "source": "synthetic",
    })

    frames = [synth]
    if instagram_df is not None and "engagement_rate" in instagram_df.columns:
        ig = instagram_df.copy()
        ig["source"] = "real_instagram"
        for col in synth.columns:
            if col not in ig.columns:
                if synth[col].dtype == object:
                    ig[col] = synth[col].mode().iloc[0]
                else:
                    ig[col] = float(synth[col].median())
        frames.append(ig[[c for c in synth.columns if c in ig.columns]])
        logger.info("Donnees reelles Instagram ajoutees : %s lignes", len(ig))

    df = pd.concat(frames, ignore_index=True)
    if "text" in df.columns:
        df = extract_text_features(df, text_col="text")
    logger.info("Training DF final : %s lignes (%s)", len(df), df["source"].value_counts().to_dict())
    return df
