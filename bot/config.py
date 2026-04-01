from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(slots=True)
class Settings:
    token: str
    prefix: str
    mongodb_uri: str
    mongodb_database: str
    openai_api_key: str | None
    openai_model: str
    log_level: str


def load_settings() -> Settings:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("DISCORD_TOKEN is missing. Add it to your environment or .env file.")

    return Settings(
        token=token,
        prefix=os.getenv("BOT_PREFIX", "-").strip() or "-",
        mongodb_uri=os.getenv("MONGODB_URI", "mongodb://localhost:27017/").strip() or "mongodb://localhost:27017/",
        mongodb_database=os.getenv("MONGODB_DATABASE", "study_os").strip() or "study_os",
        openai_api_key=_get_optional("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
    )


def _get_optional(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None
