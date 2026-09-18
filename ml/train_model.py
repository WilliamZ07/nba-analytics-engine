"""Model training pipeline for NBA win probability and point spread forecasting."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from psycopg2.extras import RealDictCursor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    mean_absolute_error,
    root_mean_squared_error,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# Ensure project root is on sys.path for internal imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.database import get_db_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
LOGGER = logging.getLogger(__name__)

ARTIFACTS_DIR = PROJECT_ROOT / "ml" / "artifacts"

FEATURE_COLUMNS = [
    "rest_differential",
    "is_home_back_to_back",
    "is_away_back_to_back",
    "home_l10_off_rating",
    "home_l10_def_rating",
    "home_l10_net_rating",
    "home_l10_pace",
    "home_l10_win_pct",
    "away_l10_off_rating",
    "away_l10_def_rating",
    "away_l10_net_rating",
    "away_l10_pace",
    "away_l10_win_pct",
    "net_rating_differential_l10",
    "home_off_vs_away_def_edge",
    "away_off_vs_home_def_edge",
    "projected_matchup_pace",
    "win_pct_differential_l10",
]


def load_feature_data() -> pd.DataFrame:
    """Fetch clean, mature pre-game matchup records sorted chronologically."""
    LOGGER.info("Querying feature store mart analytics.fct_game_features...")
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM analytics.fct_game_features
                    WHERE is_mature_sample = 1
                    ORDER BY game_date ASC, game_id ASC;
                    """
                )
                rows = cursor.fetchall()
                df = pd.DataFrame(rows)
    finally:
        conn.close()

    LOGGER.info("Loaded %d mature matchup rows for model training.", len(df))
    return df


def train_and_evaluate() -> None:
    """Train classification and regression models using chronological holdout validation."""
    df = load_feature_data()
    if df.empty:
        raise ValueError("No mature feature records available to train.")

    # Cast feature types
    for col in FEATURE_COLUMNS + ["target_home_win", "target_point_margin"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=FEATURE_COLUMNS + ["target_home_win", "target_point_margin"]).reset_index(drop=True)

    # Chronological 80/20 train/test split (no lookahead leakage)
    split_idx = int(len(df) * 0.80)
    train_df = df.iloc[:split_idx]
    test_df = df.iloc[split_idx:]

    X_train = train_df[FEATURE_COLUMNS]
    y_win_train = train_df["target_home_win"]
    y_margin_train = train_df["target_point_margin"]

    X_test = test_df[FEATURE_COLUMNS]
    y_win_test = test_df["target_home_win"]
    y_margin_test = test_df["target_point_margin"]

    LOGGER.info("Training Split: %d games | Holdout Test Split: %d games", len(train_df), len(test_df))

    # 1. Win Probability Classifier (StandardScaler + LogisticRegression)
    clf_pipeline = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("classifier", LogisticRegression(C=0.1, solver="lbfgs", max_iter=1000, random_state=42)),
        ]
    )
    clf_pipeline.fit(X_train, y_win_train)

    win_probs = clf_pipeline.predict_proba(X_test)[:, 1]
    win_preds = (win_probs >= 0.5).astype(int)

    acc = accuracy_score(y_win_test, win_preds)
    brier = brier_score_loss(y_win_test, win_probs)
    roc_auc = roc_auc_score(y_win_test, win_probs)

    LOGGER.info("=== Win Probability Model Evaluation ===")
    LOGGER.info("Accuracy:     %.2f%%", acc * 100)
    LOGGER.info("Brier Score:  %.4f (lower is better; baseline is 0.25)", brier)
    LOGGER.info("ROC-AUC:      %.4f", roc_auc)

    # 2. Point Spread Regressor (StandardScaler + Ridge)
    reg_pipeline = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("regressor", Ridge(alpha=10.0, random_state=42)),
        ]
    )
    reg_pipeline.fit(X_train, y_margin_train)

    margin_preds = reg_pipeline.predict(X_test)
    mae = mean_absolute_error(y_margin_test, margin_preds)
    rmse = root_mean_squared_error(y_margin_test, margin_preds)

    LOGGER.info("=== Point Margin Model Evaluation ===")
    LOGGER.info("MAE:          %.2f pts", mae)
    LOGGER.info("RMSE:         %.2f pts", rmse)

    # 3. Serialize Artifacts
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    bundle = {
        "win_classifier": clf_pipeline,
        "spread_regressor": reg_pipeline,
        "feature_columns": FEATURE_COLUMNS,
        "metrics": {
            "test_accuracy": acc,
            "brier_score": brier,
            "roc_auc": roc_auc,
            "mae": mae,
            "rmse": rmse,
        },
        "train_sample_size": len(train_df),
        "test_sample_size": len(test_df),
    }

    output_path = ARTIFACTS_DIR / "nba_model_bundle.joblib"
    joblib.dump(bundle, output_path)
    LOGGER.info("Successfully serialized model bundle to %s", output_path)


if __name__ == "__main__":
    train_and_evaluate()