from pydantic_settings import BaseSettings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    polygon_api_key: str = ""
    alpaca_api_key_id: str = ""
    alpaca_api_secret_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    database_path: str = str(PROJECT_ROOT / "pokieticker.db")
    email_user: str = ""
    email_password: str = ""
    email_from_name: str = "IvyTrader Research"

    model_config = {
        "env_file": str(PROJECT_ROOT / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
