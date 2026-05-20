"""
ML Engagement Predictor trained on Instagram analytics.
Predicts engagement rate.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import joblib
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MODEL_PATH = "./data/models/engagement_model.pkl"
MODEL_TARGET = "engagement_timing"
HISTORICAL_ER_BLEND_WEIGHT = 0.8


@dataclass
class EngagementPrediction:
    predicted_engagement_rate: float
    feature_importance: dict


class EngagementPredictor:
    PLATFORMS = ["instagram", "tiktok", "facebook", "twitter", "linkedin", "threads", "youtube", "pinterest"]
    CONTENT_TYPES = ["image", "video", "carousel", "reel", "story"]
    DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    def __init__(self):
        self._model = None
        self._classifier = None
        self._is_fitted = False
        self._feature_names: list[str] = []
        self._r2 = 0.0
        self._try_load_model()

    def _try_load_model(self):
        if not os.path.exists(MODEL_PATH):
            return
        try:
            data = joblib.load(MODEL_PATH)
            if data.get("target") != MODEL_TARGET:
                logger.warning("Ancien modele engagement ignore. Relancez l'entrainement Instagram.")
                return
            self._model = data.get("regressor")
            self._classifier = data.get("classifier")
            self._feature_names = data.get("feature_names", self.current_feature_names)
            self._r2 = data.get("r2", 0.0)
            self._is_fitted = self._model is not None
            logger.info("Engagement model charge depuis le disque")
        except Exception as exc:
            logger.warning("Impossible de charger le modele engagement: %s", exc)

    @property
    def current_feature_names(self) -> list[str]:
        return [
            "hour", "dow", "is_weekend", "hour_sin", "hour_cos", "dow_sin", "dow_cos",
            *[f"platform_{p}" for p in self.PLATFORMS],
            *[f"ct_{c}" for c in self.CONTENT_TYPES],
            "caption_len", "caption_sqrt", "hashtag_count",
            "has_emoji", "has_mention", "has_question",
            "followers_log", "historical_er",
        ]

    def _extract_feature_values(
        self,
        platform: str,
        content_type: str,
        hour: int,
        day_of_week: int,
        caption_length: int,
        hashtag_count: int,
        has_emoji: bool,
        has_mention: bool,
        has_question: bool,
        followers: int,
        historical_avg_er: float = 0.03,
    ) -> dict[str, float]:
        platform = platform.lower()
        content_type = content_type.lower()
        values = {
            "hour": float(hour),
            "dow": float(day_of_week),
            "is_weekend": float(day_of_week >= 5),
            "hour_sin": float(np.sin(2 * np.pi * hour / 24)),
            "hour_cos": float(np.cos(2 * np.pi * hour / 24)),
            "dow_sin": float(np.sin(2 * np.pi * day_of_week / 7)),
            "dow_cos": float(np.cos(2 * np.pi * day_of_week / 7)),
            "caption_len": float(min(caption_length, 2200)),
            "caption_sqrt": float(max(caption_length, 0) ** 0.5),
            "hashtag_count": float(min(hashtag_count, 30)),
            "has_emoji": float(bool(has_emoji)),
            "has_mention": float(bool(has_mention)),
            "has_question": float(bool(has_question)),
            "followers_log": float(np.log1p(max(followers, 1))),
            "historical_er": float(historical_avg_er),
        }
        values.update({f"platform_{p}": float(platform == p) for p in self.PLATFORMS})
        values.update({f"ct_{ct}": float(content_type == ct) for ct in self.CONTENT_TYPES})
        return values

    def _extract_features(
        self,
        platform: str,
        content_type: str,
        hour: int,
        day_of_week: int,
        caption_length: int,
        hashtag_count: int,
        has_emoji: bool,
        has_mention: bool,
        has_question: bool,
        followers: int,
        historical_avg_er: float = 0.03,
        feature_names: list[str] | None = None,
    ) -> np.ndarray:
        values = self._extract_feature_values(
            platform,
            content_type,
            hour,
            day_of_week,
            caption_length,
            hashtag_count,
            has_emoji,
            has_mention,
            has_question,
            followers,
            historical_avg_er,
        )
        names = feature_names or self.current_feature_names
        return np.array([values.get(name, 0.0) for name in names], dtype=float).reshape(1, -1)

    def _build_training_matrix(self, df: pd.DataFrame) -> np.ndarray:
        return np.vstack([
            self._extract_features(
                str(row["platform"]),
                str(row["content_type"]),
                int(row["hour"]),
                int(row["day_of_week"]),
                int(row.get("caption_length", 150)),
                int(row.get("hashtag_count", 10)),
                bool(row.get("has_emoji", False)),
                bool(row.get("has_mention", False)),
                bool(row.get("has_question", False)),
                int(row.get("followers", 10000)),
                float(row.get("historical_avg_er", 0.03)),
            ).flatten()
            for _, row in df.iterrows()
        ])

    def train_on_dataset(self, df: pd.DataFrame) -> dict:
        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
        from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, r2_score
        from sklearn.model_selection import cross_val_score, train_test_split

        df = df.copy()
        logger.info("Training engagement sur %s exemples...", len(df))
        df = df.dropna(subset=["engagement_rate"]).copy()

        X = self._build_training_matrix(df)
        y = df["engagement_rate"].astype(float).values

        model_cv = RandomForestRegressor(
            n_estimators=240,
            max_depth=18,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1,
        )
        cv_scores = cross_val_score(model_cv, X, y, cv=5, scoring="r2", n_jobs=1)

        labels = df["performance_bucket"].fillna("unknown").astype(str) if "performance_bucket" in df.columns else None
        stratify = labels if labels is not None and labels.nunique() > 1 else None
        X_train, X_test, y_train, y_test, train_idx, test_idx = train_test_split(
            X,
            y,
            df.index.values,
            test_size=0.2,
            random_state=42,
            stratify=stratify,
        )

        self._model = RandomForestRegressor(
            n_estimators=360,
            max_depth=20,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1,
        )
        self._model.fit(X_train, y_train)
        raw_preds = self._model.predict(X_test)
        hist_idx = self.current_feature_names.index("historical_er")
        preds = np.clip(
            HISTORICAL_ER_BLEND_WEIGHT * X_test[:, hist_idx]
            + (1 - HISTORICAL_ER_BLEND_WEIGHT) * raw_preds,
            0.001,
            0.5,
        )

        engagement_mae = float(mean_absolute_error(y_test, preds))
        engagement_r2 = float(r2_score(y_test, preds))
        raw_engagement_mae = float(mean_absolute_error(y_test, raw_preds))
        raw_engagement_r2 = float(r2_score(y_test, raw_preds))

        accuracy = None
        f1_weighted = None
        self._classifier = None
        if labels is not None:
            self._classifier = RandomForestClassifier(
                n_estimators=240,
                max_depth=18,
                min_samples_leaf=2,
                random_state=42,
                n_jobs=-1,
            )
            self._classifier.fit(X_train, labels.loc[train_idx])
            cls_preds = self._classifier.predict(X_test)
            accuracy = float(accuracy_score(labels.loc[test_idx], cls_preds))
            f1_weighted = float(f1_score(labels.loc[test_idx], cls_preds, average="weighted"))

        self._r2 = engagement_r2
        self._is_fitted = True
        self._feature_names = self.current_feature_names

        os.makedirs("./data/models", exist_ok=True)
        joblib.dump(
            {
                "target": MODEL_TARGET,
                "regressor": self._model,
                "classifier": self._classifier,
                "feature_names": self._feature_names,
                "r2": engagement_r2,
                "engagement_mae": engagement_mae,
                "engagement_r2": engagement_r2,
                "raw_model_engagement_mae": raw_engagement_mae,
                "raw_model_engagement_r2": raw_engagement_r2,
                "accuracy": accuracy,
                "f1_weighted": f1_weighted,
            },
            MODEL_PATH,
        )

        metrics = {
            "engagement_mae": engagement_mae,
            "engagement_r2": engagement_r2,
            "r2": engagement_r2,
            "raw_model_engagement_mae": raw_engagement_mae,
            "raw_model_engagement_r2": raw_engagement_r2,
            "cv_r2_mean": float(cv_scores.mean()),
            "cv_r2_std": float(cv_scores.std()),
            "n_train": len(X_train),
            "n_test": len(X_test),
            "real_data_rows": int((df.get("source", "real_instagram") == "real_instagram").sum()) if "source" in df.columns else len(df),
        }
        if accuracy is not None:
            metrics["accuracy"] = accuracy
            metrics["f1_weighted"] = f1_weighted
        logger.info("Training termine: %s", metrics)
        return metrics

    def predict(
        self,
        platform: str,
        content_type: str,
        hour: int,
        day_of_week: int,
        caption_length: int = 150,
        hashtag_count: int = 10,
        has_emoji: bool = True,
        has_mention: bool = False,
        has_question: bool = False,
        followers: int = 10000,
        historical_avg_er: float = 0.03,
    ) -> EngagementPrediction:
        if not self._is_fitted:
            raise RuntimeError("Engagement model is not trained. Train it with Instagram_Analytics.csv first.")

        model_feature_names = self._feature_names or self.current_feature_names
        er = self.predict_rate(
            platform=platform,
            content_type=content_type,
            hour=hour,
            day_of_week=day_of_week,
            caption_length=caption_length,
            hashtag_count=hashtag_count,
            has_emoji=has_emoji,
            has_mention=has_mention,
            has_question=has_question,
            followers=followers,
            historical_avg_er=historical_avg_er,
            feature_names=model_feature_names,
        )

        fi = {}
        if hasattr(self._model, "feature_importances_"):
            for label, imp in zip(self._feature_names, self._model.feature_importances_):
                fi[label] = round(float(imp), 4)

        return EngagementPrediction(
            predicted_engagement_rate=round(er, 4),
            feature_importance=fi,
        )

    def predict_rate(
        self,
        platform: str,
        content_type: str,
        hour: int,
        day_of_week: int,
        caption_length: int = 150,
        hashtag_count: int = 10,
        has_emoji: bool = True,
        has_mention: bool = False,
        has_question: bool = False,
        followers: int = 10000,
        historical_avg_er: float = 0.03,
        feature_names: list[str] | None = None,
    ) -> float:
        if not self._is_fitted:
            raise RuntimeError("Engagement model is not trained. Train it with Instagram_Analytics.csv first.")

        X = self._extract_features(
            platform,
            content_type,
            hour,
            day_of_week,
            caption_length,
            hashtag_count,
            has_emoji,
            has_mention,
            has_question,
            followers,
            historical_avg_er,
            feature_names=feature_names or self._feature_names or self.current_feature_names,
        )

        try:
            er = float(self._model.predict(X)[0])
        except Exception as exc:
            raise RuntimeError("Engagement model prediction failed") from exc

        historical_avg_er = max(0.001, min(float(historical_avg_er), 0.5))
        blended_er = (
            HISTORICAL_ER_BLEND_WEIGHT * historical_avg_er
            + (1 - HISTORICAL_ER_BLEND_WEIGHT) * er
        )
        return max(0.001, min(blended_er, 0.5))


engagement_predictor = EngagementPredictor()
