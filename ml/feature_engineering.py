"""Backward-compatible alias to the single shared live/offline feature engine."""
from services.feature_engine import build_features, FEATURE_COLUMNS, get_feature_list

__all__ = ["build_features", "FEATURE_COLUMNS", "get_feature_list"]
