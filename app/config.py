from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    database_path: Path
    check_interval_seconds: int = 120
    olx_timeout_seconds: float = 20.0
    max_profiles: int = 1

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN não foi configurado")

        database_path = Path(os.getenv("DATABASE_PATH", "data/olx_bot.sqlite3"))
        return cls(
            telegram_token=token,
            database_path=database_path,
            check_interval_seconds=max(30, int(os.getenv("CHECK_INTERVAL_SECONDS", "120"))),
            olx_timeout_seconds=max(5.0, float(os.getenv("OLX_REQUEST_TIMEOUT_SECONDS", "20"))),
            max_profiles=max(1, int(os.getenv("MAX_PROFILES", "1"))),
        )
