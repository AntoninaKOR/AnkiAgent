from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.storage.history import HistoryStore
from app.core.models import CardHistoryRecord


def _format_when(iso_timestamp: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso_timestamp


def _status_label(record: CardHistoryRecord) -> str:
    if record.error:
        return "Error"
    if record.added_to_anki:
        if record.anki_note_id is not None:
            return f"Added (#{record.anki_note_id})"
        return "Added"
    return "Generated"


class HistoryWindow(QDialog):
    def __init__(
        self,
        history_store: HistoryStore,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.history_store = history_store

        self.setWindowTitle("Anki Agent — History")
        self.setMinimumSize(640, 420)

        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        controls.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._reload_table)
        controls.addWidget(refresh_btn)

        clear_btn = QPushButton("Clear history…")
        clear_btn.clicked.connect(self._clear_history)
        controls.addWidget(clear_btn)
        layout.addLayout(controls)

        self.summary_label = QLabel()
        layout.addWidget(self.summary_label)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["When", "Mode", "Selection", "Note type", "Status"]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        layout.addWidget(self.table)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.clicked.connect(self.accept)
        layout.addWidget(buttons)

        self._reload_table()

    def _reload_table(self) -> None:
        records = self.history_store.list_recent()
        total = self.history_store.count()
        shown = len(records)
        self.summary_label.setText(
            f"{total} record(s) in history"
            + (f" (showing latest {shown})" if shown < total else "")
        )

        self.table.setRowCount(len(records))
        for row_index, record in enumerate(records):
            values = [
                _format_when(record.created_at),
                record.mode.replace("_", " "),
                record.selected_text,
                record.template_name,
                _status_label(record),
            ]
            for col_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col_index == 2:
                    item.setToolTip(record.selected_text)
                if record.error and col_index == 4:
                    item.setToolTip(record.error)
                self.table.setItem(row_index, col_index, item)

    def _clear_history(self) -> None:
        total = self.history_store.count()
        if total == 0:
            QMessageBox.information(self, "History", "History is already empty.")
            return

        answer = QMessageBox.question(
            self,
            "Clear history",
            f"Delete all {total} record(s) from history? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        deleted = self.history_store.clear_all()
        self._reload_table()
        QMessageBox.information(self, "History cleared", f"Deleted {deleted} record(s).")
