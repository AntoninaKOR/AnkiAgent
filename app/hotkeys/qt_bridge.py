from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, Signal, Slot

if TYPE_CHECKING:
    from app.ui.card_service import CardCreationService


class HotkeyBridge(QObject):
    """Routes global hotkey callbacks onto the Qt main thread via signals."""

    preview_requested = Signal()
    quick_add_requested = Signal()

    def __init__(self, card_service: CardCreationService) -> None:
        super().__init__()
        self._card_service = card_service
        self.preview_requested.connect(
            self._on_preview, Qt.ConnectionType.QueuedConnection
        )
        self.quick_add_requested.connect(
            self._on_quick_add, Qt.ConnectionType.QueuedConnection
        )

    def request_preview(self) -> None:
        self.preview_requested.emit()

    def request_quick_add(self) -> None:
        self.quick_add_requested.emit()

    @Slot()
    def _on_preview(self) -> None:
        self._card_service.run_preview()

    @Slot()
    def _on_quick_add(self) -> None:
        self._card_service.run_quick_add()
