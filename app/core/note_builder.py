from __future__ import annotations

from app.core.models import AppConfig, PreparedAnkiNote

DEFAULT_TAGS = ["ai", "quick_add"]


class NoteBuildError(Exception):
    pass


def build_prepared_note(
    config: AppConfig,
    note_type: str,
    field_names: list[str],
    generated_fields: dict[str, str],
) -> PreparedAnkiNote:
    deck = (config.selected_deck or "").strip()
    note_type = note_type.strip()
    if not deck:
        raise NoteBuildError("Choose a deck in Settings.")
    if not note_type:
        raise NoteBuildError("Choose a note type in Settings.")
    if not field_names:
        raise NoteBuildError(f'Note type "{note_type}" has no fields.')

    missing = [name for name in field_names if name not in generated_fields]
    if missing:
        raise NoteBuildError(f"LLM did not fill field(s): {', '.join(missing)}")

    return PreparedAnkiNote(
        deck=deck,
        model=note_type,
        fields={name: generated_fields[name] for name in field_names},
        tags=list(DEFAULT_TAGS),
    )
