from __future__ import annotations

from typing import Callable


# Stub content by normalized field name (future real LLM will ignore this map).
_FIELD_STUBS: dict[str, Callable[[str, str], str]] = {
    "front": lambda word, _note: word,
    "word": lambda word, _note: word,
    "question": lambda word, _note: word,
    "back": lambda word, _note: f"Definition of {word}",
    "definition": lambda word, _note: f"Definition of {word}",
    "answer": lambda word, _note: f"Answer for {word}",
    "translation": lambda word, _note: f"Translation of {word}",
    "example": lambda word, _note: f"Example sentence with {word}.",
    "example translation": lambda word, _note: f"Пример со словом {word}.",
    "example_translation": lambda word, _note: f"Пример со словом {word}.",
}


class FakeLLMClient:
    """Placeholder LLM: fills each Anki field with deterministic fake content."""

    def generate(
        self,
        selected_text: str,
        note_type: str,
        field_names: list[str],
    ) -> dict[str, str]:
        if not field_names:
            raise ValueError("Note type has no fields.")

        word = selected_text.strip()
        fields: dict[str, str] = {}
        for index, field_name in enumerate(field_names):
            stub = _FIELD_STUBS.get(field_name.strip().lower())
            if stub is not None:
                fields[field_name] = stub(word, note_type)
            elif index == 0:
                fields[field_name] = word
            else:
                fields[field_name] = f"({note_type}) {field_name}: {word}"
        return fields
