"""Runtime settings read from the repository-root .env file (template: .env.example)."""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env", encoding="utf-8-sig")  # Notepad may add a BOM

# [AMENDMENT 2026-10-01, docs/design_mock_data.md 0 and 8] Two datasets. "desanitized" is the original
# layout in place at the repository root (the owner's private regression data, never pitched);
# "mock" lives under datasets/mock/ with the same inner layout (kb/, eval/, data/, emails/).
# without DATASET the original layout is used when its tables are present, and the mock set otherwise (the public demo repository has no original data)
DATASET = os.getenv("DATASET") or ("desanitized" if (REPO_ROOT / "kb" / "vessels.csv").exists() else "mock")
if DATASET not in ("desanitized", "mock"):
    raise ValueError(f"DATASET must be desanitized or mock, not {DATASET!r}")
DATASET_ROOT = REPO_ROOT if DATASET == "desanitized" else REPO_ROOT / "datasets" / DATASET


class Settings(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    llm_mode: Literal["recorded", "live"]
    chat_llm_mode: Literal["recorded", "live"] = "recorded"  # CHAT_LLM_MODE, defaults to LLM_MODE
    llm_model: str
    llm_base_url: str  # OpenAI-compatible endpoint; DeepSeek since 2026-09-26
    llm_thinking: Literal["enabled", "disabled"]  # DeepSeek reasoning; off for extraction
    database_path: Path
    has_api_key: bool
    default_utc_offset: timezone  # for sent times without an offset (E1)
    demo_now: datetime | None = (
        None  # DEMO_NOW: the clock of the demo (sample data ends 30 Jul 2026)
    )


def _parse_offset(value: str) -> timezone:
    """'+08:00' or '-05:30' to a fixed timezone."""
    sign = -1 if value.startswith("-") else 1
    hours, minutes = value.lstrip("+-").split(":")
    return timezone(sign * timedelta(hours=int(hours), minutes=int(minutes)))


def load_settings() -> Settings:
    """Read settings once at startup. The API key itself is never stored here or logged."""
    database_path = Path(os.getenv("DATABASE_PATH", "./data/app.sqlite"))
    if not database_path.is_absolute():
        database_path = DATASET_ROOT / database_path
    return Settings(
        llm_mode=os.getenv("LLM_MODE", "recorded"),
        chat_llm_mode=os.getenv("CHAT_LLM_MODE") or os.getenv("LLM_MODE", "recorded"),
        llm_model=os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL", ""),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
        llm_thinking=os.getenv("LLM_THINKING", "disabled"),
        database_path=database_path,
        has_api_key=bool(os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")),
        default_utc_offset=_parse_offset(os.getenv("DEFAULT_UTC_OFFSET", "+08:00")),
        demo_now=datetime.fromisoformat(os.environ["DEMO_NOW"]) if os.getenv("DEMO_NOW") else None,
    )
