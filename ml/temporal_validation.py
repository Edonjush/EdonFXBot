"""Leakage-aware chronological splitting and candidate-only ML training."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
import json

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, balanced_accuracy_score, classification_report, confusion_matrix
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier


@dataclass(frozen=True)
class TemporalSplit:
    X_train: pd.DataFrame
    y_train: pd.Series
    X_validation: pd.DataFrame
    y_validation: pd.Series
    X_test: pd.DataFrame
    y_test: pd.Series
    boundaries: dict


def chronological_purged_split(X: pd.DataFrame, y: pd.Series, *, lookahead: int = 12,
                               train_fraction: float = 0.70,
                               validation_fraction: float = 0.15) -> TemporalSplit:
    """Split in existing time order; purge `lookahead` samples before each boundary.

    The caller must sort chronologically before calling. Rows in the purge gaps
    are deliberately unused so training labels cannot reach into the next fold.
    """
    if not isinstance(X, pd.DataFrame) or not isinstance(y, pd.Series):
        raise TypeError("X must be a DataFrame and y must be a Series")
    if len(X) != len(y) or len(X) < max(100, lookahead * 10):
        raise ValueError("Insufficient or mismatched samples for temporal split")
    if lookahead < 1 or not 0 < train_fraction < 1 or not 0 < validation_fraction < 1:
        raise ValueError("Invalid split parameters")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("Train and validation fractions must sum to less than 1")

    n = len(X)
    train_end = int(n * train_fraction)
    validation_end = int(n * (train_fraction + validation_fraction))
    # Exclude the final `lookahead` labelled observations from each earlier fold.
    train_stop = train_end - lookahead
    validation_stop = validation_end - lookahead
    if train_stop <= 0 or validation_stop <= train_end or validation_end >= n:
        raise ValueError("Dataset too small after applying purge windows")

    positions = {
        "train": (0, train_stop),
        "purge_after_train": (train_stop, train_end),
        "validation": (train_end, validation_stop),
        "purge_after_validation": (validation_stop, validation_end),
        "test": (validation_end, n),
    }
    def take(start, stop):
        fold_x = X.iloc[start:stop].copy()
        fold_y = y.iloc[start:stop].copy()
        labelled = fold_y.notna()
        return fold_x.loc[labelled].copy(), fold_y.loc[labelled].astype(int).copy()
    xt, yt = take(*positions["train"])
    xv, yv = take(*positions["validation"])
    xs, ys = take(*positions["test"])
    if yt.nunique() < 2 or yv.nunique() < 2 or ys.nunique() < 2:
        raise ValueError("Each chronological fold must contain both target classes")
    return TemporalSplit(xt, yt, xv, yv, xs, ys, positions)


def _metrics(model, X, y):
    pred = model.predict(X)
    probabilities = model.predict_proba(X)
    return {
        "samples": int(len(y)),
        "accuracy": float(accuracy_score(y, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
        "classification_report": classification_report(y, pred, output_dict=True, zero_division=0),
        "confusion_matrix": confusion_matrix(y, pred).tolist(),
        "mean_max_probability": float(probabilities.max(axis=1).mean()),
    }


def train_candidate(dataset_path: Path | str, *, output_root: Path | str,
                    lookahead: int = 12, random_state: int = 42) -> dict:
    """Train/evaluate a candidate and save only under a separate candidates folder.

    This function never writes to models/model.pkl, scaler.pkl, or features.pkl.
    The test fold is evaluated once after fitting on the training fold; validation
    is reported separately and is not used for hyperparameter selection here.
    """
    from services.feature_engine import build_features, FEATURE_COLUMNS
    from ml.label_generator import generate_labels
    from ml.dataset_builder import prepare_dataset

    dataset_path = Path(dataset_path)
    output_root = Path(output_root)
    df = pd.read_csv(dataset_path)
    if "datetime" not in df.columns:
        raise ValueError("Historical data must contain a datetime column")
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce", utc=True)
    df = df.dropna(subset=["datetime"]).sort_values("datetime")
    if df["datetime"].duplicated().any():
        raise ValueError("Duplicate timestamps found; resolve duplicates before training")
    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing OHLC columns: {missing}")
    if not np.isfinite(df[required].to_numpy(dtype=float)).all():
        raise ValueError("OHLC data contains non-finite values")
    if (df["high"] < df[["open", "close", "low"]].max(axis=1)).any() or (df["low"] > df[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("Invalid OHLC candle ranges detected")

    featured = build_features(df)
    labelled = generate_labels(featured, lookahead=lookahead, drop_unlabeled=False)
    columns = list(FEATURE_COLUMNS)
    missing_features = [c for c in columns if c not in labelled.columns]
    if missing_features:
        raise ValueError(f"Feature pipeline missing columns: {missing_features}")
    labelled = labelled.replace([np.inf, -np.inf], np.nan)
    X, y = prepare_dataset(labelled, drop_unlabeled=False)
    split = chronological_purged_split(X, y, lookahead=lookahead)

    # Fit preprocessing on training observations only.
    scaler = StandardScaler()
    x_train = scaler.fit_transform(split.X_train)
    x_validation = scaler.transform(split.X_validation)
    x_test = scaler.transform(split.X_test)

    negatives = int((split.y_train == 0).sum())
    positives = int((split.y_train == 1).sum())
    if positives == 0 or negatives == 0:
        raise ValueError("Training fold does not contain both classes")
    model = XGBClassifier(
        n_estimators=300, max_depth=4, learning_rate=0.03,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=negatives / positives,
        eval_metric="logloss", random_state=random_state,
        n_jobs=1,
    )
    model.fit(x_train, split.y_train)
    validation_metrics = _metrics(model, x_validation, split.y_validation)
    test_metrics = _metrics(model, x_test, split.y_test)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate_dir = output_root / "candidates" / f"candidate_{stamp}"
    candidate_dir.mkdir(parents=True, exist_ok=False)
    joblib.dump(model, candidate_dir / "model.pkl")
    joblib.dump(scaler, candidate_dir / "scaler.pkl")
    joblib.dump(columns, candidate_dir / "features.pkl")
    metadata = {
        "status": "candidate_not_promoted",
        "created_utc": stamp,
        "dataset": str(dataset_path),
        "lookahead_bars": lookahead,
        "feature_columns": columns,
        "split_positions": split.boundaries,
        "rows_after_features_before_neutral_filter": int(len(labelled)),
        "labelled_rows": int(y.notna().sum()),
        "validation": validation_metrics,
        "out_of_sample_test": test_metrics,
        "deployment_approved": False,
        "note": "Classification metrics only; transaction-cost-aware strategy evaluation is still required.",
    }
    (candidate_dir / "metrics.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {"success": True, "candidate_dir": str(candidate_dir), "metadata": metadata}
