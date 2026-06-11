from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.core.models import CardHistoryRecord


class HistoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS card_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mode TEXT NOT NULL,
                    selected_text TEXT NOT NULL,
                    template_name TEXT NOT NULL,
                    generated_fields_json TEXT NOT NULL,
                    added_to_anki INTEGER NOT NULL,
                    anki_note_id INTEGER,
                    error TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

    def save_generation(
        self,
        mode: str,
        selected_text: str,
        note_type: str,
        generated_fields: dict[str, str],
        error: str | None = None,
    ) -> int:
        record = CardHistoryRecord(
            mode=mode,
            selected_text=selected_text,
            template_name=note_type,
            generated_fields_json=json.dumps(
                {"note_type": note_type, "fields": generated_fields},
                ensure_ascii=False,
            ),
            added_to_anki=0,
            error=error,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO card_history (
                    mode, selected_text, template_name, generated_fields_json,
                    added_to_anki, anki_note_id, error, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.mode,
                    record.selected_text,
                    record.template_name,
                    record.generated_fields_json,
                    record.added_to_anki,
                    record.anki_note_id,
                    record.error,
                    record.created_at,
                ),
            )
            return int(cursor.lastrowid)

    def mark_added(self, history_id: int, anki_note_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE card_history
                SET added_to_anki = 1, anki_note_id = ?, error = NULL
                WHERE id = ?
                """,
                (anki_note_id, history_id),
            )

    def mark_error(self, history_id: int, error: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE card_history SET error = ? WHERE id = ?",
                (error, history_id),
            )

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM card_history").fetchone()
        return int(row["n"]) if row else 0

    def list_recent(self, limit: int = 200) -> list[CardHistoryRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, mode, selected_text, template_name, generated_fields_json,
                       added_to_anki, anki_note_id, error, created_at
                FROM card_history
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def clear_all(self) -> int:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM card_history")
            return cursor.rowcount

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> CardHistoryRecord:
        return CardHistoryRecord(
            id=int(row["id"]),
            mode=str(row["mode"]),
            selected_text=str(row["selected_text"]),
            template_name=str(row["template_name"]),
            generated_fields_json=str(row["generated_fields_json"]),
            added_to_anki=int(row["added_to_anki"]),
            anki_note_id=row["anki_note_id"],
            error=row["error"],
            created_at=str(row["created_at"]),
        )
