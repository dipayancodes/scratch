from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()

DEPRECATED_GROQ_MODELS = {
    "llama3-8b-8192": "llama-3.1-8b-instant",
    "llama3-70b-8192": "llama-3.3-70b-versatile",
}


@dataclass(slots=True)
class Settings:
    token: str
    prefix: str
    mongodb_uri: str
    mongodb_database: str
    groq_api_key: str | None
    groq_model: str
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
        groq_api_key=_get_optional("GROQ_API_KEY"),
        groq_model=_normalize_groq_model(os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip() or "llama-3.1-8b-instant"),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
    )


def _get_optional(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def _normalize_groq_model(model: str) -> str:
    return DEPRECATED_GROQ_MODELS.get(model, model)
