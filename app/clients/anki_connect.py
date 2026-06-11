from __future__ import annotations

from typing import Any

import requests


class AnkiConnectError(Exception):
    pass


class AnkiConnectClient:
    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/")

    def invoke(self, action: str, params: dict[str, Any] | None = None) -> Any:
        payload: dict[str, Any] = {"action": action, "version": 6}
        if params is not None:
            payload["params"] = params
        try:
            response = requests.post(self.url, json=payload, timeout=10)
            response.raise_for_status()
            body = response.json()
        except requests.RequestException as exc:
            raise AnkiConnectError(
                "AnkiConnect is unavailable. Open Anki and ensure AnkiConnect is installed."
            ) from exc

        if body.get("error"):
            raise AnkiConnectError(str(body["error"]))
        return body.get("result")

    def check_available(self) -> None:
        self.invoke("version")

    def deck_names(self) -> list[str]:
        result = self.invoke("deckNames")
        return sorted(result or [])

    def model_names(self) -> list[str]:
        """Returns list of note type names (Basic, Cloze, etc.)."""
        result = self.invoke("modelNames")
        names = [m for m in (result or []) if m and not str(m).startswith("-")]
        return sorted(names)

    def model_field_names(self, model: str) -> list[str]:
        """Returns list of field names for a given note type."""
        result = self.invoke("modelFieldNames", {"modelName": model})
        return list(result or [])

    def create_deck(self, deck: str) -> None:
        """Creates a new deck in Anki."""
        self.invoke("createDeck", {"deck": deck})

    def create_model(
        self,
        model_name: str,
        field_names: list[str],
        *,
        front_fields: list[str],
        back_fields: list[str],
    ) -> None:
        """Create a note type with one card template.

        Args:
            model_name: The name of the note type to create.
            field_names: The names of the fields (defines order in the note type).
            front_fields: Fields to show on the card front (question side).
            back_fields: Fields to show on the card back (answer side).
        """
        if not field_names:
            raise AnkiConnectError("At least one field is required.")
        if not front_fields:
            raise AnkiConnectError("At least one field must be on the front of the card.")

        known = set(field_names)
        for name in front_fields + back_fields:
            if name not in known:
                raise AnkiConnectError(f'Unknown field "{name}" for this note type.')
        if set(front_fields) | set(back_fields) != known:
            raise AnkiConnectError("Each field must be assigned to the front or back of the card.")
        if len(front_fields) != len(set(front_fields)) or len(back_fields) != len(set(back_fields)):
            raise AnkiConnectError("Duplicate field assignment.")

        def _block(names: list[str]) -> str:
            return "<br>".join(f"{{{{{name}}}}}" for name in names)

        front_template = _block(front_fields)
        if back_fields:
            back_template = f"{_block(front_fields)}<hr id=answer>{_block(back_fields)}"
        else:
            back_template = front_template

        params = {
            "modelName": model_name,
            "inOrderFields": field_names,
            "cardTemplates": [
                {
                    "Name": "Card 1",
                    "Front": front_template,
                    "Back": back_template,
                }
            ],
        }
        self.invoke("createModel", params)

    def add_note(
        self,
        deck: str,
        model: str,
        fields: dict[str, str],
        tags: list[str],
    ) -> int:
        """Adds a new note to Anki."""
        note = {
            "deckName": deck,
            "modelName": model,
            "fields": fields,
            "tags": tags,
        }
        result = self.invoke("addNote", {"note": note})
        if result is None:
            raise AnkiConnectError("Failed to add note: AnkiConnect returned no note id.")
        return int(result)
