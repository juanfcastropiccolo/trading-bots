from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # LLM
    anthropic_api_key: str = ""
    llm_model: str = "anthropic/claude-3-haiku-20240307"

    # Database
    database_url: str = "sqlite:///data/trading.db"

    # Trading
    default_symbol: str = "BTC/USDT"
    default_timeframe: str = "1m"
    trading_loop_interval_seconds: int = 60
    initial_budget_usd: float = 100.0

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {
        "env_file": str(Path(__file__).resolve().parent.parent / ".env"),
        "env_file_encoding": "utf-8",
    }


settings = Settings()
