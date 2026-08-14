from dataclasses import dataclass
from os import getenv
from pathlib import Path
from typing import Literal

RuntimeMode = Literal["demo", "llm"]


@dataclass(frozen=True, slots=True)
class Settings:
    mode: RuntimeMode = "demo"
    database_path: Path = Path("meetings.db")
    llm_model: str = "gpt-4.1-mini"
    llm_base_url: str | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"demo", "llm"}:
            raise ValueError("MEETING_ASSISTANT_MODE must be either 'demo' or 'llm'")


def load_settings() -> Settings:
    return Settings(
        mode=getenv("MEETING_ASSISTANT_MODE", "demo"),
        database_path=Path(getenv("MEETING_ASSISTANT_DATABASE_PATH", "meetings.db")),
        llm_model=getenv("MEETING_ASSISTANT_LLM_MODEL", "gpt-4.1-mini"),
        llm_base_url=getenv("MEETING_ASSISTANT_LLM_BASE_URL") or None,
    )
