from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal

from app.clients.anki_connect import AnkiConnectClient, AnkiConnectError
from app.clients.clipboard import ClipboardError, capture_selected_text
from app.llm.fake import FakeLLMClient
from app.llm.base import LLMClient
from app.storage.history import HistoryStore
from app.core.models import AppConfig, PreparedAnkiNote
from app.core.note_builder import NoteBuildError, build_prepared_note


@dataclass
class CardWorkerResult:
    mode: str
    selected_text: str
    note_type: str
    generated_fields: dict[str, str]
    prepared: PreparedAnkiNote
    history_id: int | None


class CardWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        mode: str,
        config: AppConfig,
        anki_client: AnkiConnectClient,
        history_store: HistoryStore,
        llm_client: LLMClient,
    ) -> None:
        super().__init__()
        self.mode = mode
        self.config = config
        self.anki_client = anki_client
        self.history_store = history_store
        self.llm_client = llm_client

    def run(self) -> None:
        history_id: int | None = None
        try:
            selected_text = capture_selected_text(
                restore_clipboard=self.config.restore_clipboard
            )
            note_type = (self.config.note_type or "").strip()
            if not note_type:
                raise NoteBuildError("Choose a note type in Settings.")

            field_names = self.anki_client.model_field_names(note_type)
            if not field_names:
                raise NoteBuildError(f'Note type "{note_type}" has no fields.')

            generated_fields = self.llm_client.generate(
                selected_text, note_type, field_names
            )
            prepared = build_prepared_note(
                self.config,
                note_type,
                field_names,
                generated_fields,
            )

            if self.config.behavior.save_history:
                history_id = self.history_store.save_generation(
                    mode=self.mode,
                    selected_text=selected_text,
                    note_type=note_type,
                    generated_fields=generated_fields,
                )

            self.succeeded.emit(
                CardWorkerResult(
                    mode=self.mode,
                    selected_text=selected_text,
                    note_type=note_type,
                    generated_fields=generated_fields,
                    prepared=prepared,
                    history_id=history_id,
                )
            )
        except (ClipboardError, NoteBuildError, AnkiConnectError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"Unexpected error: {exc}")
