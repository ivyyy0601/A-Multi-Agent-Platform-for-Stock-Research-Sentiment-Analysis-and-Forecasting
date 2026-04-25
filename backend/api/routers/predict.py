"""Prediction API endpoints."""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "ml" / "models"


@router.get("/{symbol}")
def get_prediction(symbol: str, horizon: str = Query("t1", pattern="^t(1|7|14)$")):
    """Get direction prediction for a symbol."""
    from backend.ml.model import predict

    result = predict(symbol.upper(), horizon)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/{symbol}/backtest")
def get_backtest(symbol: str, horizon: str = Query("t1", pattern="^t(1|7|14)$")):
    """Get backtest results for a symbol."""
    sym = symbol.upper()
    path = MODELS_DIR / f"{sym}_{horizon}_backtest.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No backtest for {sym}/{horizon}. Run training with --backtest.")
    return json.loads(path.read_text())


@router.get("/{symbol}/forecast")
def get_forecast(symbol: str, window: int = Query(7, ge=1, le=14), date: str | None = Query(None)):
    """Generate forecast based on 1D / 7D / 14D look-back windows."""
    from backend.ml.inference import generate_forecast
    from backend.ml.forecast_store import load_latest_forecast, load_forecast_on_or_before

    symbol = symbol.upper()
    try:
        cached = load_forecast_on_or_before(symbol, window, date) if date else load_latest_forecast(symbol, window)
        if cached:
            if not date:
                return cached
            # Historical detail view must use the clicked day itself, not an older
            # cached snapshot on or before that day. If there is no exact cache hit,
            # fall back to live generation for the requested date.
            if str(cached.get("forecast_date")) == str(date):
                return cached

        result = generate_forecast(symbol, window, ref_date=date)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"forecast_failed:{type(e).__name__}:{e}")


@router.get("/{symbol}/similar-days")
def get_similar_days(symbol: str, date: str = Query(...), top_k: int = Query(10, ge=1, le=30)):
    """Find historically similar trading days based on ML features."""
    from backend.ml.similar import find_similar_days

    result = find_similar_days(symbol.upper(), date, top_k)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
