from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    def generate(
        self,
        selected_text: str,
        note_type: str,
        field_names: list[str],
    ) -> dict[str, str]:
        """Fill Anki note fields for the given note type."""
