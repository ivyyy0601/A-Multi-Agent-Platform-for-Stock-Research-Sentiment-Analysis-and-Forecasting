"""Model training and prediction for detail forecasts.

Detail models are trained per ticker. We select across a small set of
model families and parameters:

1. build daily features for the ticker
2. compare LR / RF / XGBoost candidates
3. score candidates with time-series cross validation
4. evaluate the selected candidate on the latest holdout window
5. save the best candidate trained on all available history
"""

import json
from pathlib import Path
from datetime import datetime

import numpy as np
import joblib
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier

from backend.ml.features import build_features, build_features_multi, FEATURE_COLS
from backend.ml.features_v2 import (
    build_features_v2,
    FEATURE_COLS_V2_MARKET,
    FEATURE_COLS_V2_CANDLE,
)

MODELS_DIR = Path(__file__).parent / "models"
MODELS_DIR.mkdir(exist_ok=True)

DETAIL_MODEL_CANDIDATES = [
    {
        "family": "lr",
        "params": {
            "C": 0.3,
            "class_weight": None,
            "max_iter": 1000,
        },
    },
    {
        "family": "lr",
        "params": {
            "C": 1.0,
            "class_weight": None,
            "max_iter": 1000,
        },
    },
    {
        "family": "lr",
        "params": {
            "C": 0.3,
            "class_weight": "balanced",
            "max_iter": 1000,
        },
    },
    {
        "family": "lr",
        "params": {
            "C": 1.0,
            "class_weight": "balanced",
            "max_iter": 1000,
        },
    },
    {
        "family": "rf",
        "params": {
            "n_estimators": 250,
            "max_depth": 4,
            "min_samples_leaf": 3,
            "class_weight": None,
            "random_state": 42,
        },
    },
    {
        "family": "rf",
        "params": {
            "n_estimators": 350,
            "max_depth": 6,
            "min_samples_leaf": 2,
            "class_weight": None,
            "random_state": 42,
        },
    },
    {
        "family": "rf",
        "params": {
            "n_estimators": 250,
            "max_depth": 4,
            "min_samples_leaf": 3,
            "class_weight": "balanced",
            "random_state": 42,
        },
    },
    {
        "family": "rf",
        "params": {
            "n_estimators": 350,
            "max_depth": 6,
            "min_samples_leaf": 2,
            "class_weight": "balanced",
            "random_state": 42,
        },
    },
    {
        "family": "xgb",
        "params": {
            "max_depth": 3,
            "n_estimators": 150,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
        },
    },
    {
        "family": "xgb",
        "params": {
            "max_depth": 4,
            "n_estimators": 200,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
        },
    },
    {
        "family": "xgb",
        "params": {
            "max_depth": 4,
            "n_estimators": 300,
            "learning_rate": 0.03,
            "subsample": 0.9,
            "colsample_bytree": 0.9,
        },
    },
]

DETAIL_HORIZON_CONFIG = {
    "t1": {
        "builder": build_features_v2,
        "builder_kwargs": {"use_text": False},
    },
    "t7": {
        "builder": build_features_v2,
        "builder_kwargs": {"use_text": False},
    },
    "t14": {
        "builder": build_features_v2,
        "builder_kwargs": {"use_text": False},
    },
}

DETAIL_FEATURE_SETS = {
    "v1_base": FEATURE_COLS,
    "v2_market": FEATURE_COLS_V2_MARKET,
    "v2_candle": FEATURE_COLS_V2_CANDLE,
}

DETAIL_MODEL_COMBOS = [
    {
        "feature_set": "v1_base",
        "family": "xgb",
        "params": {
            "max_depth": 4,
            "n_estimators": 200,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
        },
    },
    {
        "feature_set": "v2_market",
        "family": "xgb",
        "params": {
            "max_depth": 4,
            "n_estimators": 200,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
        },
    },
    {
        "feature_set": "v2_candle",
        "family": "xgb",
        "params": {
            "max_depth": 4,
            "n_estimators": 200,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
        },
    },
    {
        "feature_set": "v1_base",
        "family": "lr",
        "params": {
            "C": 1.0,
            "class_weight": "balanced",
            "max_iter": 1000,
        },
    },
    {
        "feature_set": "v2_market",
        "family": "lr",
        "params": {
            "C": 1.0,
            "class_weight": "balanced",
            "max_iter": 1000,
        },
    },
    {
        "feature_set": "v2_candle",
        "family": "lr",
        "params": {
            "C": 1.0,
            "class_weight": "balanced",
            "max_iter": 1000,
        },
    },
    {
        "feature_set": "v1_base",
        "family": "rf",
        "params": {
            "n_estimators": 250,
            "max_depth": 6,
            "class_weight": "balanced",
            "random_state": 42,
        },
    },
    {
        "feature_set": "v2_market",
        "family": "rf",
        "params": {
            "n_estimators": 250,
            "max_depth": 6,
            "class_weight": "balanced",
            "random_state": 42,
        },
    },
    {
        "feature_set": "v2_candle",
        "family": "rf",
        "params": {
            "n_estimators": 250,
            "max_depth": 6,
            "class_weight": "balanced",
            "random_state": 42,
        },
    },
]


def _make_model(family: str, params: dict):
    if family == "xgb":
        return XGBClassifier(
            eval_metric="logloss",
            random_state=42,
            **params,
        )
    if family == "rf":
        return Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="constant", fill_value=0.0)),
                ("clf", RandomForestClassifier(**params)),
            ]
        )
    if family == "lr":
        return Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="constant", fill_value=0.0)),
                ("scaler", StandardScaler()),
                ("clf", LogisticRegression(random_state=42, **params)),
            ]
        )
    raise ValueError(f"Unsupported family: {family}")


def _feature_importances(model, n_features: int) -> np.ndarray:
    if isinstance(model, Pipeline):
        clf = model.named_steps["clf"]
        if hasattr(clf, "coef_"):
            coefs = np.asarray(clf.coef_)
            if coefs.ndim == 2:
                coefs = coefs[0]
            return np.abs(coefs)
        if hasattr(clf, "feature_importances_"):
            return np.asarray(clf.feature_importances_, dtype=float)
        return np.zeros(n_features, dtype=float)

    if hasattr(model, "feature_importances_"):
        return np.asarray(model.feature_importances_, dtype=float)

    return np.zeros(n_features, dtype=float)


def _time_series_candidate_results(X: np.ndarray, y: np.ndarray, candidate: dict) -> dict:
    """Evaluate a candidate with expanding-window splits.

    We keep this intentionally small and stable so it can run in daily automation.
    """
    n_rows = len(y)
    n_splits = 4 if n_rows >= 220 else 3 if n_rows >= 140 else 2
    splitter = TimeSeriesSplit(n_splits=n_splits)

    fold_metrics: list[dict] = []
    for fold_idx, (train_idx, test_idx) in enumerate(splitter.split(X), 1):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        if len(np.unique(y_train)) < 2 or len(np.unique(y_test)) < 2:
            continue

        model = _make_model(candidate["family"], candidate["params"])
        if candidate["family"] == "xgb":
            model.fit(X_train, y_train, verbose=False)
        else:
            model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        baseline = max(y_test.mean(), 1 - y_test.mean())
        fold_metrics.append(
            {
                "fold": fold_idx,
                "accuracy": float(acc),
                "baseline": float(baseline),
                "edge": float(acc - baseline),
                "train_size": int(len(train_idx)),
                "test_size": int(len(test_idx)),
            }
        )

    if not fold_metrics:
        return {
            "family": candidate["family"],
            "params": candidate["params"],
            "cv_accuracy": 0.0,
            "cv_baseline": 0.0,
            "cv_edge": -1.0,
            "cv_std": 1.0,
            "folds": [],
        }

    accs = [m["accuracy"] for m in fold_metrics]
    baselines = [m["baseline"] for m in fold_metrics]
    edges = [m["edge"] for m in fold_metrics]
    return {
        "family": candidate["family"],
        "params": candidate["params"],
        "cv_accuracy": float(np.mean(accs)),
        "cv_baseline": float(np.mean(baselines)),
        "cv_edge": float(np.mean(edges)),
        "cv_std": float(np.std(accs)),
        "folds": fold_metrics,
    }


def _select_best_candidate(results: list[dict]) -> dict:
    """Pick the most robust candidate.

    Priority:
    1. highest edge over baseline
    2. highest CV accuracy
    3. lower CV volatility
    """
    return sorted(
        results,
        key=lambda r: (
            round(r["cv_edge"], 6),
            round(r["cv_accuracy"], 6),
            -round(r["cv_std"], 6),
        ),
        reverse=True,
    )[0]


def train(symbol: str, horizon: str = "t1") -> dict:
    """Train the best candidate model for a single symbol/horizon."""
    target_col = f"target_{horizon}"
    cfg = DETAIL_HORIZON_CONFIG.get(horizon)
    if cfg is None:
        return {"error": f"Unsupported horizon: {horizon}"}

    builder = cfg["builder"]
    df = builder(symbol, **cfg.get("builder_kwargs", {}))
    if df.empty or len(df) < 60:
        return {"error": f"Not enough data for {symbol} ({len(df)} rows)"}

    # Drop rows where target is NaN (last few days)
    df = df.dropna(subset=[target_col]).reset_index(drop=True)
    y = df[target_col].values
    dates = df["trade_date"].dt.strftime("%Y-%m-%d").tolist()

    # Time-series split: last 20% for holdout evaluation
    split_idx = int(len(df) * 0.8)
    y_train, y_test = y[:split_idx], y[split_idx:]
    candidate_results = []
    matrices = {}

    for combo in DETAIL_MODEL_COMBOS:
        feature_cols = [c for c in DETAIL_FEATURE_SETS[combo["feature_set"]] if c in df.columns]
        X = df[feature_cols].values
        X_train = X[:split_idx]
        result = _time_series_candidate_results(
            X_train,
            y_train,
            {"family": combo["family"], "params": combo["params"]},
        )
        result["feature_set"] = combo["feature_set"]
        result["feature_cols"] = feature_cols
        candidate_results.append(result)
        matrices[(combo["feature_set"], combo["family"])] = X

    best_candidate = _select_best_candidate(candidate_results)
    selected_family = str(best_candidate["family"])
    selected_params = dict(best_candidate["params"])
    feature_cols = list(best_candidate["feature_cols"])
    selected_feature_set = str(best_candidate["feature_set"])
    X = matrices[(selected_feature_set, selected_family)]
    X_train, X_test = X[:split_idx], X[split_idx:]

    model = _make_model(selected_family, selected_params)
    if selected_family == "xgb":
        model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
    else:
        model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    baseline = max(y_test.mean(), 1 - y_test.mean())

    # Feature importance
    importances = _feature_importances(model, len(feature_cols))
    top_features = sorted(
        zip(feature_cols, importances.tolist()),
        key=lambda x: x[1],
        reverse=True,
    )[:10]

    meta = {
        "symbol": symbol,
        "horizon": horizon,
        "accuracy": round(accuracy, 4),
        "baseline": round(baseline, 4),
        "precision": round(precision_score(y_test, y_pred, zero_division=0), 4),
        "recall": round(recall_score(y_test, y_pred, zero_division=0), 4),
        "f1": round(f1_score(y_test, y_pred, zero_division=0), 4),
        "cv_accuracy": round(best_candidate["cv_accuracy"], 4),
        "cv_baseline": round(best_candidate["cv_baseline"], 4),
        "cv_edge": round(best_candidate["cv_edge"], 4),
        "cv_std": round(best_candidate["cv_std"], 4),
        "feature_set": selected_feature_set,
        "train_size": split_idx,
        "test_size": len(y_test),
        "train_start": dates[0],
        "train_end": dates[split_idx - 1],
        "test_start": dates[split_idx],
        "test_end": dates[-1],
        "selected_family": selected_family,
        "selected_params": selected_params,
        "candidate_results": [
            {
                "family": r["family"],
                "feature_set": r.get("feature_set"),
                "params": r["params"],
                "cv_accuracy": round(r["cv_accuracy"], 4),
                "cv_baseline": round(r["cv_baseline"], 4),
                "cv_edge": round(r["cv_edge"], 4),
                "cv_std": round(r["cv_std"], 4),
            }
            for r in candidate_results
        ],
        "top_features": [{"name": n, "importance": round(v, 4)} for n, v in top_features],
        "trained_at": datetime.now().isoformat(),
    }

    # Refit the selected configuration on all available rows before saving.
    final_model = _make_model(selected_family, selected_params)
    if selected_family == "xgb":
        final_model.fit(X, y, verbose=False)
    else:
        final_model.fit(X, y)

    model_path = MODELS_DIR / f"{symbol}_{horizon}.joblib"
    meta_path = MODELS_DIR / f"{symbol}_{horizon}_meta.json"
    joblib.dump(final_model, model_path)
    meta_path.write_text(json.dumps(meta, indent=2))

    return meta


def train_unified(horizon: str = "t1", symbols: list[str] | None = None) -> dict:
    """Train a single XGBoost on ALL tickers combined. Returns metrics dict."""
    target_col = f"target_{horizon}"

    df = build_features_multi(symbols)
    if df.empty or len(df) < 100:
        return {"error": f"Not enough combined data ({len(df)} rows)"}

    df = df.dropna(subset=[target_col]).reset_index(drop=True)

    X = df[FEATURE_COLS].values
    y = df[target_col].values
    dates = df["trade_date"].dt.strftime("%Y-%m-%d").tolist()
    syms = df["symbol"].tolist()

    # Time-series split: sort by date, last 20% for test
    split_idx = int(len(df) * 0.8)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    model = XGBClassifier(
        max_depth=4,
        n_estimators=300,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        random_state=42,
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    baseline = max(y_test.mean(), 1 - y_test.mean())

    importances = _feature_importances(model, len(FEATURE_COLS))
    top_features = sorted(
        zip(FEATURE_COLS, importances.tolist()),
        key=lambda x: x[1],
        reverse=True,
    )[:10]

    meta = {
        "symbol": "UNIFIED",
        "horizon": horizon,
        "accuracy": round(accuracy, 4),
        "baseline": round(baseline, 4),
        "precision": round(precision_score(y_test, y_pred, zero_division=0), 4),
        "recall": round(recall_score(y_test, y_pred, zero_division=0), 4),
        "f1": round(f1_score(y_test, y_pred, zero_division=0), 4),
        "train_size": split_idx,
        "test_size": len(y_test),
        "train_start": dates[0],
        "train_end": dates[split_idx - 1],
        "test_start": dates[split_idx],
        "test_end": dates[-1],
        "tickers": sorted(set(syms)),
        "top_features": [{"name": n, "importance": round(v, 4)} for n, v in top_features],
        "trained_at": datetime.now().isoformat(),
    }

    model_path = MODELS_DIR / f"UNIFIED_{horizon}.joblib"
    meta_path = MODELS_DIR / f"UNIFIED_{horizon}_meta.json"
    joblib.dump(model, model_path)
    meta_path.write_text(json.dumps(meta, indent=2))

    return meta


def predict(symbol: str, horizon: str = "t1") -> dict:
    """Load model and predict direction for the latest trading day."""
    model_path = MODELS_DIR / f"{symbol}_{horizon}.joblib"
    meta_path = MODELS_DIR / f"{symbol}_{horizon}_meta.json"

    # Fall back to unified model if per-ticker model missing
    if not model_path.exists():
        model_path = MODELS_DIR / f"UNIFIED_{horizon}.joblib"
        meta_path = MODELS_DIR / f"UNIFIED_{horizon}_meta.json"
    if not model_path.exists():
        return {"error": f"No model for {symbol}/{horizon}. Run training first."}

    model = joblib.load(model_path)
    meta = json.loads(meta_path.read_text())

    cfg = DETAIL_HORIZON_CONFIG.get(horizon)
    if cfg is None:
        return {"error": f"Unsupported horizon: {horizon}"}

    df = cfg["builder"](symbol, **cfg.get("builder_kwargs", {}))
    if df.empty:
        return {"error": f"No feature data for {symbol}"}

    # Use the last row (most recent trading day with complete features)
    last_row = df.iloc[-1]
    feature_cols = [c for c in cfg["feature_cols"] if c in df.columns]
    X = last_row[feature_cols].values.reshape(1, -1).astype(np.float64)

    proba = model.predict_proba(X)[0]
    pred_class = int(np.argmax(proba))
    confidence = float(proba[pred_class])

    # Top feature contributions for this prediction
    if hasattr(model, "feature_importances_"):
        importances = np.asarray(model.feature_importances_, dtype=float)
    elif hasattr(model, "named_steps"):
        clf = model.named_steps["clf"]
        if hasattr(clf, "feature_importances_"):
            importances = np.asarray(clf.feature_importances_, dtype=float)
        elif hasattr(clf, "coef_"):
            coef = np.asarray(clf.coef_)
            if coef.ndim == 2:
                coef = coef[0]
            importances = np.abs(coef)
        else:
            importances = np.zeros(len(feature_cols), dtype=float)
    else:
        importances = np.zeros(len(feature_cols), dtype=float)
    feature_values = {col: float(last_row[col]) for col in feature_cols}
    top = sorted(
        zip(feature_cols, importances.tolist()),
        key=lambda x: x[1],
        reverse=True,
    )[:5]

    return {
        "symbol": symbol,
        "horizon": horizon,
        "direction": "up" if pred_class == 1 else "down",
        "confidence": round(confidence, 4),
        "date": str(last_row["trade_date"].date()),
        "top_features": [
            {"name": n, "value": round(feature_values[n], 4), "importance": round(imp, 4)}
            for n, imp in top
        ],
        "model_accuracy": meta["accuracy"],
        "baseline_accuracy": meta["baseline"],
    }
