"""DatasetLoader - lecture, nettoyage, feature engineering pour ML."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DATASET_DIR = Path("./data/datasets")
QUADRILINGUAL_SENTIMENT_CSV = DATASET_DIR / "sentiment_quadrilingual_3333.csv"
INSTAGRAM_ANALYTICS_CSV = DATASET_DIR / "Instagram_Analytics.csv"


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


def _add_historical_engagement_feature(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute une moyenne d'engagement historique sans fuite de la ligne cible."""
    df = df.copy()
    er = pd.to_numeric(df["engagement_rate"], errors="coerce").fillna(0.03).clip(0.001, 0.5)
    df["engagement_rate"] = er

    fallback = float(er.median()) if len(er) else 0.03
    if "account_id" not in df.columns:
        df["historical_avg_er"] = fallback
        return df

    sort_cols = []
    if "post_datetime" in df.columns:
        df["_post_dt_sort"] = pd.to_datetime(df["post_datetime"], errors="coerce")
        sort_cols.append("_post_dt_sort")
    elif "post_date" in df.columns:
        df["_post_dt_sort"] = pd.to_datetime(df["post_date"], errors="coerce")
        sort_cols.append("_post_dt_sort")
    sort_cols.extend(["account_id"])

    ordered = df.sort_values(sort_cols, kind="mergesort") if sort_cols else df.copy()
    ordered["_prior_account_er"] = (
        ordered.groupby("account_id", sort=False)["engagement_rate"]
        .transform(lambda values: values.expanding().mean().shift(1))
    )
    ordered["_prior_global_er"] = ordered["engagement_rate"].expanding().mean().shift(1)
    ordered["historical_avg_er"] = (
        ordered["_prior_account_er"]
        .fillna(ordered["_prior_global_er"])
        .fillna(fallback)
        .clip(0.001, 0.5)
    )

    restored = ordered.sort_index()
    drop_cols = [col for col in ["_post_dt_sort", "_prior_account_er", "_prior_global_er"] if col in restored.columns]
    return restored.drop(columns=drop_cols)


def load_quadrilingual_sentiment(max_rows: int = 200_000) -> pd.DataFrame:
    """Charge le CSV local quadrilingue avec les colonnes text/sentiment_label."""
    if not QUADRILINGUAL_SENTIMENT_CSV.exists():
        raise FileNotFoundError(
            f"Dataset quadrilingue introuvable. Ajoutez {QUADRILINGUAL_SENTIMENT_CSV}"
        )

    df = pd.read_csv(QUADRILINGUAL_SENTIMENT_CSV, nrows=max_rows)
    required = {"text", "sentiment_label"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            "Dataset quadrilingue invalide. Colonnes manquantes: "
            + ", ".join(sorted(missing))
        )

    df["text"] = df["text"].astype(str).apply(clean_text)
    df["sentiment_label"] = df["sentiment_label"].astype(str).str.strip().str.lower()
    df = df[df["sentiment_label"].isin({"negative", "neutral", "positive"})]
    df = df[df["text"].str.len() > 5].copy()

    if len(df) > max_rows:
        df = df.sample(n=max_rows, random_state=42)

    logger.info(
        "Sentiment quadrilingue: %s lignes | %s",
        len(df),
        df["sentiment_label"].value_counts().to_dict(),
    )
    return df[["text", "sentiment_label"]].reset_index(drop=True)


def load_sentiment140(max_rows: int = 200_000) -> pd.DataFrame:
    """Compatibilite: charge uniquement le CSV quadrilingue local."""
    return load_quadrilingual_sentiment(max_rows=max_rows)


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
    """Charge le dataset Instagram local pour les features d'engagement."""
    try:
        if not INSTAGRAM_ANALYTICS_CSV.exists():
            raise FileNotFoundError(f"Dataset Instagram introuvable: {INSTAGRAM_ANALYTICS_CSV}")

        df = pd.read_csv(INSTAGRAM_ANALYTICS_CSV)
        rename_map = {
            "follower_count": "followers",
            "media_type": "content_type",
            "post_hour": "hour",
            "hashtags_count": "hashtag_count",
            "caption_length": "caption_length",
            "performance_bucket_label": "performance_bucket",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
        if "day_of_week" in df.columns:
            day_map = {
                "monday": 0,
                "tuesday": 1,
                "wednesday": 2,
                "thursday": 3,
                "friday": 4,
                "saturday": 5,
                "sunday": 6,
            }
            df["day_of_week"] = (
                df["day_of_week"].astype(str).str.strip().str.lower().map(day_map)
            )

        if "engagement_rate" not in df.columns and {"likes", "comments", "shares", "saves", "followers"}.issubset(df.columns):
            interactions = df[["likes", "comments", "shares", "saves"]].sum(axis=1)
            df["engagement_rate"] = (interactions / df["followers"].clip(1)).clip(0, 0.5)

        df["platform"] = "instagram"
        df["content_type"] = (df["content_type"] if "content_type" in df.columns else "image")
        if not isinstance(df["content_type"], pd.Series):
            df["content_type"] = "image"
        df["content_type"] = df["content_type"].fillna("image").astype(str).str.lower()

        for col, default, min_value, max_value in [
            ("hour", 12, 0, 23),
            ("day_of_week", 0, 0, 6),
            ("followers", 10000, 1, None),
            ("caption_length", 150, 0, 2200),
            ("hashtag_count", 0, 0, 30),
        ]:
            if col not in df.columns:
                df[col] = default
            values = pd.to_numeric(df[col], errors="coerce").fillna(default).astype(int)
            df[col] = values.clip(lower=min_value, upper=max_value)
        df["has_emoji"] = 0
        df["has_mention"] = 0
        df["has_question"] = 0
        if "reach" in df.columns:
            df["reach"] = pd.to_numeric(df["reach"], errors="coerce").fillna(0).astype(int).clip(0)
        df = _add_historical_engagement_feature(df)
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
    expected_er = (er_base * er_ct * time_bonus).clip(0.001, 0.5)
    er_syn = (expected_er + rng.normal(0, 0.005, synthetic_size)).clip(0.001, 0.5)

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
        "historical_avg_er": (expected_er * rng.uniform(0.9, 1.1, synthetic_size)).clip(0.001, 0.5),
        "engagement_rate": er_syn,
        "source": "synthetic",
    })

    frames = [synth]
    if instagram_df is not None and "engagement_rate" in instagram_df.columns:
        ig = instagram_df.copy()
        ig["source"] = "real_instagram"
        for col in [*synth.columns, "reach", "performance_bucket"]:
            if col not in ig.columns:
                if col in synth.columns and synth[col].dtype == object:
                    ig[col] = synth[col].mode().iloc[0]
                else:
                    ig[col] = float(synth[col].median()) if col in synth.columns else None
        frames.append(ig[[c for c in [*synth.columns, "reach", "performance_bucket"] if c in ig.columns]])
        logger.info("Donnees reelles Instagram ajoutees : %s lignes", len(ig))

    df = pd.concat(frames, ignore_index=True)
    if "text" in df.columns:
        df = extract_text_features(df, text_col="text")
    logger.info("Training DF final : %s lignes (%s)", len(df), df["source"].value_counts().to_dict())
    return df
