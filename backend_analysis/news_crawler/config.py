import os
from dotenv import load_dotenv

load_dotenv()

WATCHLIST = [t.strip().upper() for t in os.getenv("WATCHLIST", "").split(",") if t.strip()]
CRAWL_INTERVAL = int(os.getenv("CRAWL_INTERVAL", "15"))
NEWS_RETENTION_DAYS = int(os.getenv("NEWS_RETENTION_DAYS", "3"))
_DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "news.db")
DATABASE_PATH = os.getenv("DATABASE_PATH", _DEFAULT_DB)
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8001"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
