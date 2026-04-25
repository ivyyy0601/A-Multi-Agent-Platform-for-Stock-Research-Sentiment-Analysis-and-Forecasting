import os
from pathlib import Path

# Load .env before anything else
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith('#') and '=' in _line:
            _k, _v = _line.split('=', 1)
            os.environ.setdefault(_k.strip(), _v.strip())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.api.routers import stocks, news, analysis, predict, adanos, automation, market, ai, library

app = FastAPI(title="PokieTicker", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:7777", "http://127.0.0.1:7777", "http://localhost:7778", "http://127.0.0.1:7778"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(stocks.router, prefix="/api/stocks", tags=["stocks"])
app.include_router(news.router, prefix="/api/news", tags=["news"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(predict.router, prefix="/api/predict", tags=["predict"])
app.include_router(adanos.router, prefix="/api/adanos", tags=["adanos"])
app.include_router(automation.router, prefix="/api/automation", tags=["automation"])
app.include_router(market.router, prefix="/api/market", tags=["market"])
app.include_router(ai.router,      prefix="/api/ai",      tags=["ai"])
app.include_router(library.router, prefix="/api/library", tags=["library"])
@app.on_event("startup")
def startup():
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}
