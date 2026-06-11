from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox, QWidget

from app.clients.anki_connect import AnkiConnectClient, AnkiConnectError
from app.core.card_worker import CardWorker, CardWorkerResult
from app.llm.base import LLMClient
from app.llm.fake import FakeLLMClient
from app.storage.history import HistoryStore
from app.core.models import AppConfig, PreparedAnkiNote
from app.ui.preview_window import PreviewWindow


class CardCreationService:
    def __init__(
        self,
        config: AppConfig,
        anki_client: AnkiConnectClient,
        history_store: HistoryStore,
        llm_client: LLMClient | None = None,
        notify: Callable[[str, str], None] | None = None,
        parent_widget: QWidget | None = None,
    ) -> None:
        self.config = config
        self.anki_client = anki_client
        self.history_store = history_store
        self.llm_client = llm_client or FakeLLMClient()
        self.notify = notify or (lambda _title, _message: None)
        self.parent_widget = parent_widget
        self._worker: CardWorker | None = None

    def run_preview(self) -> None:
        self._start_worker("preview")

    def run_quick_add(self) -> None:
        if not self.config.behavior.quick_add_enabled:
            self._show_error("Quick add disabled", "Enable quick_add in config.yaml.")
            return
        self._start_worker("quick_add")

    def _start_worker(self, mode: str) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._show_error("Busy", "Already processing a selection. Wait a moment.")
            return

        self._worker = CardWorker(
            mode=mode,
            config=self.config,
            anki_client=self.anki_client,
            history_store=self.history_store,
            llm_client=self.llm_client,
        )
        self._worker.succeeded.connect(self._on_worker_succeeded)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_worker_finished(self) -> None:
        self._worker = None

    def _on_worker_failed(self, message: str) -> None:
        title = "Clipboard" if "selection" in message.lower() or "clipboard" in message.lower() else "Error"
        self._show_error(title, message)

    def _on_worker_succeeded(self, result: CardWorkerResult) -> None:
        if result.mode == "preview":
            self._show_preview(result)
        else:
            self._quick_add(result)

    def _show_preview(self, result: CardWorkerResult) -> None:
        field_names = list(result.prepared.fields.keys())
        try:
            field_names = self.anki_client.model_field_names(result.prepared.model)
        except AnkiConnectError:
            pass
        window = PreviewWindow(
            selected_text=result.selected_text,
            prepared=result.prepared,
            field_names=field_names,
            parent=self.parent_widget,
        )
        window.setWindowModality(Qt.ApplicationModal)
        window.raise_()
        window.activateWindow()
        if window.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            note_id = self._add_to_anki(window.edited_prepared())
            if result.history_id is not None:
                self.history_store.mark_added(result.history_id, note_id)
            self.notify("Success", f"Added to Anki: {result.selected_text}")
        except AnkiConnectError as exc:
            self._handle_error(result.history_id, str(exc))
            self._show_error("AnkiConnect", str(exc))

    def _quick_add(self, result: CardWorkerResult) -> None:
        try:
            note_id = self._add_to_anki(result.prepared)
            if result.history_id is not None:
                self.history_store.mark_added(result.history_id, note_id)
            self.notify("Added to Anki", f"Added to Anki: {result.selected_text}")
        except AnkiConnectError as exc:
            short_error = str(exc).split(".")[0]
            self._handle_error(result.history_id, str(exc))
            self._show_error("Failed to add card", f"Failed to add card: {short_error}")

    def _add_to_anki(self, prepared: PreparedAnkiNote) -> int:
        self.anki_client.check_available()
        return self.anki_client.add_note(
            deck=prepared.deck,
            model=prepared.model,
            fields=prepared.fields,
            tags=prepared.tags,
        )

    def _show_error(self, title: str, message: str) -> None:
        self.notify(title, message)
        QMessageBox.warning(self.parent_widget, title, message)

    def shutdown(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.wait(2000)
        self._worker = None

    def _handle_error(self, history_id: int | None, error: str) -> None:
        if history_id is not None:
            self.history_store.mark_error(history_id, error)
