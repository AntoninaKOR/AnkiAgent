from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class HotkeysConfig(BaseModel):
    preview: str
    quick_add: str


class AnkiConfig(BaseModel):
    url: str = "http://127.0.0.1:8765"


class BehaviorConfig(BaseModel):
    preview_before_add: bool = True
    quick_add_enabled: bool = True
    save_history: bool = True


class AppConfig(BaseModel):
    hotkeys: HotkeysConfig
    note_type: str = "Basic"
    selected_deck: str = "Default"
    restore_clipboard: bool = True
    anki: AnkiConfig = Field(default_factory=AnkiConfig)
    behavior: BehaviorConfig = Field(default_factory=BehaviorConfig)

    @classmethod
    def load(cls, path: Path) -> AppConfig:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)


class CardHistoryRecord(BaseModel):
    id: int | None = None
    mode: str
    selected_text: str
    template_name: str
    generated_fields_json: str
    added_to_anki: int
    anki_note_id: int | None = None
    error: str | None = None
    created_at: str


class PreparedAnkiNote(BaseModel):
    deck: str
    model: str
    fields: dict[str, str]
    tags: list[str]
