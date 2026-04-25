import os
from dotenv import load_dotenv

load_dotenv()

WATCHLIST = [t.strip().upper() for t in os.getenv("WATCHLIST", "").split(",") if t.strip()]
CRAWL_INTERVAL = int(os.getenv("CRAWL_INTERVAL", "15"))
POST_RETENTION_DAYS = int(os.getenv("POST_RETENTION_DAYS", "3"))
_DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "reddit.db")
DATABASE_PATH = os.getenv("DATABASE_PATH", _DEFAULT_DB)
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8002"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
MAIN_SUBREDDITS = [s.strip() for s in os.getenv("MAIN_SUBREDDITS", "stocks,investing,wallstreetbets").split(",") if s.strip()]
