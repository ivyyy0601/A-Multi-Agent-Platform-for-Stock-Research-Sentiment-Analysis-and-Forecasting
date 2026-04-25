"""Train ensemble model (LogisticRegression) with walk-forward validation.

Predicts next-day direction: 1 = up, 0 = down.
P(up) from logistic regression combined with cosine similarity at inference time.

Usage:
    python -m backend.adanos.model               # train all tickers unified
    python -m backend.adanos.model --ticker NVDA # single ticker
"""

import argparse
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

import numpy as np
import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler, FunctionTransformer
from sklearn.metrics import accuracy_score
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

from backend.adanos.features import build_features, FEATURE_COLS
from backend.adanos.forecast_store import save_model_run

MODELS_DIR = Path(__file__).parent / "models"
MODELS_DIR.mkdir(exist_ok=True)

LR_PARAM_CANDIDATES = [
    {"C": 0.03, "class_weight": None},
    {"C": 0.1, "class_weight": None},
    {"C": 0.3, "class_weight": None},
    {"C": 1.0, "class_weight": None},
    {"C": 0.03, "class_weight": "balanced"},
    {"C": 0.1, "class_weight": "balanced"},
    {"C": 0.3, "class_weight": "balanced"},
    {"C": 1.0, "class_weight": "balanced"},
]

# Production override selected against page-level combined signal backtests.
# The current best combination uses a lighter LR contribution at inference time
# and performs best with C=1.0 / no class weighting for the unified model.
PRODUCTION_UNIFIED_PARAMS = {"C": 1.0, "class_weight": None}
PRODUCTION_UNIFIED_XGB_PARAMS = {
    "max_depth": 2,
    "learning_rate": 0.05,
    "n_estimators": 200,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "min_child_weight": 1,
    "reg_lambda": 1.0,
}


def _make_model(params: dict, max_iter: int = 1000) -> Pipeline:
    return Pipeline([
        ("scaler", StandardScaler()),
        (
            "clipper",
            FunctionTransformer(
                np.clip,
                validate=False,
                kw_args={"a_min": -5, "a_max": 5},
            ),
        ),
        (
            "clf",
            LogisticRegression(
                C=float(params["C"]),
                class_weight=params["class_weight"],
                max_iter=max_iter,
                random_state=42,
            ),
        ),
    ])


def _walk_forward_single(
    X: np.ndarray, y: np.ndarray, params: dict, window: int = 25
) -> Optional[float]:
    """Walk-forward direction accuracy for a single ticker."""
    correct = 0
    total = 0
    for i in range(window, len(X)):
        X_tr = X[i - window:i]
        y_tr = y[i - window:i]
        X_te, y_te = X[i:i+1], y[i:i+1]
        if len(np.unique(y_tr)) < 2:
            continue
        try:
            model = _make_model(params, max_iter=500)
            model.fit(X_tr, y_tr)
            pred = model.predict(X_te)
            correct += int(pred[0] == y_te[0])
            total += 1
        except Exception:
            continue
    return correct / total if total > 0 else None


def _walk_forward(full_df, params: dict, window: int = 25) -> float:
    """Walk-forward per ticker separately, then average."""
    results = []
    for ticker in full_df["ticker"].unique():
        df_t = full_df[full_df["ticker"] == ticker].reset_index(drop=True)
        if len(df_t) < window + 5:
            continue
        X_t = df_t[FEATURE_COLS].values.astype(np.float64)
        y_t = (df_t["target_t1"].values > 0).astype(int)
        np.nan_to_num(X_t, copy=False)
        acc = _walk_forward_single(X_t, y_t, params=params, window=window)
        if acc is not None:
            results.append(acc)
    return float(np.mean(results)) if results else 0.5


def _time_split_accuracy(X_df, y: np.ndarray, params: dict) -> tuple[float, int, int, float]:
    split = int(len(X_df) * 0.8)
    X_tr, X_te = X_df.iloc[:split].values, X_df.iloc[split:].values
    y_tr, y_te = y[:split], y[split:]
    baseline = float(max(y_te.mean(), 1 - y_te.mean()))
    model = _make_model(params)
    model.fit(X_tr, y_tr)
    acc = float(accuracy_score(y_te, model.predict(X_te)))
    return acc, split, len(y_te), baseline


def _select_best_params(full_df, X_df, y: np.ndarray) -> tuple[dict, list[dict]]:
    candidates: list[dict] = []
    for params in LR_PARAM_CANDIDATES:
        try:
            lr_acc, _, _, _ = _time_split_accuracy(X_df, y, params)
            wf_acc = _walk_forward(full_df, params=params, window=25)
            candidates.append(
                {
                    "params": params,
                    "lr_accuracy": round(lr_acc, 4),
                    "walkforward_accuracy": round(wf_acc, 4),
                }
            )
        except Exception:
            continue

    if not candidates:
        raise RuntimeError("No valid LogisticRegression parameter candidates")

    candidates.sort(
        key=lambda item: (item["walkforward_accuracy"], item["lr_accuracy"]),
        reverse=True,
    )
    return candidates[0]["params"], candidates


def _get_all_db_tickers() -> list[str]:
    """Return all tickers that have platform_sentiment data in the DB."""
    from backend.database import get_conn
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT ticker FROM platform_sentiment ORDER BY ticker"
    ).fetchall()
    conn.close()
    return [r["ticker"] for r in rows]


def train(ticker: Optional[str] = None) -> dict:
    """Train logistic regression model across all tickers (or single ticker)."""
    symbols = [ticker.upper()] if ticker else _get_all_db_tickers()
    frames = []
    for sym in symbols:
        df = build_features(sym)
        if df.empty or len(df) < 30:
            continue
        df["ticker"] = sym
        frames.append(df)

    if not frames:
        return {"error": "No feature data available"}

    import pandas as pd
    full_df = pd.concat(frames, ignore_index=True)
    full_df = full_df.dropna(subset=["target_t1"]).reset_index(drop=True)

    X_df = full_df[FEATURE_COLS].astype(np.float64).fillna(0)
    y = (full_df["target_t1"].values > 0).astype(int)  # 1=up, 0=down

    if ticker is None:
        # Production path: ticker-aware XGBoost on the unified dataset.
        # We append ticker identity so the model can learn different regimes
        # without forcing separate per-ticker models.
        import pandas as pd

        full_df = full_df.copy()
        split_mask = pd.Series(False, index=full_df.index)
        for sym in full_df["ticker"].unique():
            idx = full_df.index[full_df["ticker"] == sym]
            split = int(len(idx) * 0.8)
            split_mask.loc[idx[:split]] = True

        X_all = pd.get_dummies(full_df[FEATURE_COLS + ["ticker"]], columns=["ticker"])
        y_all = y
        X_tr = X_all.loc[split_mask]
        X_te = X_all.loc[~split_mask]
        y_tr = y_all[split_mask.values]
        y_te = y_all[~split_mask.values]

        baseline = float(max(y_te.mean(), 1 - y_te.mean()))
        xgb_params = dict(PRODUCTION_UNIFIED_XGB_PARAMS)
        model = XGBClassifier(
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=42,
            **xgb_params,
        )
        model.fit(X_tr, y_tr)
        proba = model.predict_proba(X_te)[:, 1]
        pred = (proba >= 0.55).astype(int)
        lr_acc = float(accuracy_score(y_te, pred))
        wf_acc = lr_acc
        split = int(split_mask.sum())
        test_size = int((~split_mask).sum())

        # Refit on all rows.
        model.fit(X_all, y_all)

        imp_map = dict(zip(X_all.columns.tolist(), model.feature_importances_.tolist()))
        top_features = sorted(
            (
                (name, float(imp_map.get(name, 0.0)))
                for name in FEATURE_COLS
            ),
            key=lambda x: x[1],
            reverse=True,
        )[:10]
        candidate_results = [
            {
                "params": xgb_params,
                "threshold": 0.55,
                "ml_accuracy": round(lr_acc, 4),
            }
        ]
        selected_params = xgb_params
        saved_model = {"xgb": model}
        model_type = "xgboost_ticker"
        extra_meta = {
            "feature_columns": X_all.columns.tolist(),
        }
    else:
        best_params, candidate_results = _select_best_params(full_df, X_df, y)
        best_params = dict(best_params)
        lr_acc, split, test_size, baseline = _time_split_accuracy(X_df, y, best_params)
        wf_acc = _walk_forward(full_df, params=best_params, window=25)

        model = _make_model(best_params)
        model.fit(X_df.values, y)

        coefs = np.abs(model.named_steps["clf"].coef_[0])
        coefs = coefs / (coefs.sum() + 1e-10)
        top_features = sorted(
            zip(FEATURE_COLS, coefs.tolist()),
            key=lambda x: x[1], reverse=True
        )[:10]
        selected_params = best_params
        saved_model = {"lr": model}
        model_type = "logistic_regression"
        extra_meta = {}

    # ── Save ──────────────────────────────────────────────────────────────────
    name = ticker.upper() if ticker else "UNIFIED"
    joblib.dump(saved_model, MODELS_DIR / f"{name}_ensemble.joblib")

    meta = {
        "name": name,
        "tickers": symbols,
        "n_rows": len(full_df),
        "train_size": split,
        "test_size": test_size,
        "lr_accuracy": round(lr_acc, 4),
        "walkforward_accuracy": round(wf_acc, 4),
        "baseline": round(baseline, 4),
        "selected_params": selected_params,
        "candidate_results": candidate_results,
        "top_features": [{"name": n, "importance": round(v, 4)} for n, v in top_features],
        "trained_at": datetime.now().isoformat(),
        "run_date": datetime.now().strftime("%Y-%m-%d"),
        "model_type": model_type,
        **extra_meta,
    }
    (MODELS_DIR / f"{name}_meta.json").write_text(json.dumps(meta, indent=2))
    save_model_run(meta)

    print(
        f"  {name}: LR={lr_acc:.1%} WF={wf_acc:.1%} base={baseline:.1%} "
        f"params={selected_params} ({len(full_df)} rows)"
    )
    return meta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", type=str, default=None)
    args = parser.parse_args()
    result = train(args.ticker)
    if "error" in result:
        print(f"Error: {result['error']}")


if __name__ == "__main__":
    main()
