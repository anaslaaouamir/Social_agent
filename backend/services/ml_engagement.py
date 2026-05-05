"""
ML Engagement Predictor - entraine sur jeux de donnees reels et synthetiques.
Predit : engagement_rate, reach, best_timing
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


@dataclass
class EngagementPrediction:
    predicted_engagement_rate: float
    predicted_reach: int
    confidence: float
    best_hour: int
    best_day: str
    recommended_content_type: str
    feature_importance: dict


class EngagementPredictor:
    PLATFORMS = ["instagram", "tiktok", "facebook", "twitter", "linkedin", "threads", "youtube", "pinterest"]
    CONTENT_TYPES = ["image", "video", "carousel", "reel", "story"]
    DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    def __init__(self):
        self._model = None
        self._is_fitted = False
        self._feature_names: list[str] = []
        self._r2 = 0.0
        self._try_load_model()

    def _try_load_model(self):
        if os.path.exists(MODEL_PATH):
            try:
                data = joblib.load(MODEL_PATH)
                self._model = data["model"]
                self._feature_names = data["feature_names"]
                self._r2 = data.get("r2", 0.75)
                self._is_fitted = True
                logger.info("Engagement model charge depuis le disque")
            except Exception as exc:
                logger.warning("Impossible de charger le modele: %s", exc)

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
    ) -> np.ndarray:
        features = [
            hour,
            day_of_week,
            1 if day_of_week >= 5 else 0,
            np.sin(2 * np.pi * hour / 24),
            np.cos(2 * np.pi * hour / 24),
            np.sin(2 * np.pi * day_of_week / 7),
            np.cos(2 * np.pi * day_of_week / 7),
        ]

        for p in self.PLATFORMS:
            features.append(1 if platform.lower() == p else 0)
        for ct in self.CONTENT_TYPES:
            features.append(1 if content_type.lower() == ct else 0)

        features.extend([
            min(caption_length, 2200),
            caption_length ** 0.5,
            min(hashtag_count, 30),
            1 if has_emoji else 0,
            1 if has_mention else 0,
            1 if has_question else 0,
            np.log1p(followers),
            historical_avg_er,
        ])
        return np.array(features).reshape(1, -1)

    def train_on_dataset(self, df: pd.DataFrame) -> dict:
        from sklearn.metrics import mean_absolute_error, r2_score
        from sklearn.model_selection import cross_val_score, train_test_split
        from xgboost import XGBRegressor

        logger.info("Training sur %s exemples...", len(df))

        X = np.vstack([
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
        y = df["engagement_rate"].values

        model_cv = XGBRegressor(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1,
        )
        cv_scores = cross_val_score(model_cv, X, y, cv=5, scoring="r2", n_jobs=1)
        logger.info("CV R² scores: %s | mean=%.4f", np.round(cv_scores, 4), cv_scores.mean())

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        self._model = XGBRegressor(
            n_estimators=500,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1,
        )
        try:
            self._model.fit(
                X_train,
                y_train,
                eval_set=[(X_test, y_test)],
                verbose=False,
                early_stopping_rounds=30,
            )
        except TypeError:
            self._model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

        preds = self._model.predict(X_test)
        mae = float(mean_absolute_error(y_test, preds))
        r2 = float(r2_score(y_test, preds))
        self._r2 = r2
        self._is_fitted = True
        self._feature_names = [
            "hour", "dow", "is_weekend", "hour_sin", "hour_cos", "dow_sin", "dow_cos",
            *[f"platform_{p}" for p in self.PLATFORMS],
            *[f"ct_{c}" for c in self.CONTENT_TYPES],
            "caption_len", "caption_sqrt", "hashtag_count",
            "has_emoji", "has_mention", "has_question",
            "followers_log", "historical_er",
        ]

        os.makedirs("./data/models", exist_ok=True)
        joblib.dump(
            {"model": self._model, "feature_names": self._feature_names, "r2": r2, "mae": mae},
            MODEL_PATH,
        )

        real_rows = int((df.get("source", "synthetic") == "real_instagram").sum()) if "source" in df.columns else 0
        logger.info("Model saved - MAE: %.4f, R²: %.4f", mae, r2)
        return {
            "mae": mae,
            "r2": r2,
            "cv_r2_mean": float(cv_scores.mean()),
            "cv_r2_std": float(cv_scores.std()),
            "n_train": len(X_train),
            "n_test": len(X_test),
            "real_data_rows": real_rows,
        }

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
            return self._heuristic_predict(platform, content_type, hour, day_of_week, followers)

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
        )
        expected_features = len(self._feature_names) if self._feature_names else None
        if expected_features and X.shape[1] != expected_features:
            logger.warning(
                "Engagement model feature mismatch: expected %s, got %s. Falling back to heuristic.",
                expected_features,
                X.shape[1],
            )
            return self._heuristic_predict(platform, content_type, hour, day_of_week, followers)

        try:
            er = float(self._model.predict(X)[0])
        except Exception as exc:
            logger.warning("Engagement model prediction failed: %s. Falling back to heuristic.", exc)
            return self._heuristic_predict(platform, content_type, hour, day_of_week, followers)

        er = max(0.001, min(er, 0.5))
        reach = int(followers * er * 10)

        best_er = -1.0
        best_hour = hour
        best_day_idx = day_of_week
        for h in range(6, 23):
            for d in range(7):
                X_test = self._extract_features(
                    platform,
                    content_type,
                    h,
                    d,
                    caption_length,
                    hashtag_count,
                    has_emoji,
                    has_mention,
                    has_question,
                    followers,
                    historical_avg_er,
                )
                try:
                    pred = float(self._model.predict(X_test)[0])
                except Exception:
                    continue
                if pred > best_er:
                    best_er = pred
                    best_hour = h
                    best_day_idx = d

        fi = {}
        if hasattr(self._model, "feature_importances_"):
            for label, imp in zip(self._feature_names, self._model.feature_importances_):
                fi[label] = round(float(imp), 4)

        return EngagementPrediction(
            predicted_engagement_rate=round(er, 4),
            predicted_reach=reach,
            confidence=min(0.95, 0.6 + self._r2 if self._r2 else 0.75),
            best_hour=best_hour,
            best_day=self.DAYS[best_day_idx],
            recommended_content_type=content_type,
            feature_importance=fi,
        )

    def _heuristic_predict(self, platform, content_type, hour, day_of_week, followers) -> EngagementPrediction:
        base_er = {
            "instagram": 0.038,
            "tiktok": 0.058,
            "facebook": 0.012,
            "twitter": 0.009,
            "linkedin": 0.022,
            "threads": 0.026,
            "youtube": 0.018,
            "pinterest": 0.021,
        }.get(platform.lower(), 0.025)
        ct_multiplier = {
            "reel": 1.8,
            "video": 1.5,
            "carousel": 1.3,
            "image": 1.0,
            "story": 0.7,
        }.get(content_type.lower(), 1.0)
        time_bonus = 1.2 if 18 <= hour <= 21 else (0.85 if hour < 8 or hour > 23 else 1.0)
        er = base_er * ct_multiplier * time_bonus
        return EngagementPrediction(
            predicted_engagement_rate=round(er, 4),
            predicted_reach=int(followers * er * 8),
            confidence=0.45,
            best_hour=19,
            best_day="Wednesday",
            recommended_content_type="reel" if platform in ["instagram", "tiktok"] else "video",
            feature_importance={},
        )


engagement_predictor = EngagementPredictor()
