from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.clients.anki_connect import AnkiConnectClient, AnkiConnectError
from app.core.config import load_config, save_config, validate_hotkey
from app.hotkeys.manager import HotkeyRegistrationError
from app.core.models import AppConfig, HotkeysConfig
from app.ui.new_note_type_dialog import NewNoteTypeDialog


class SettingsWindow(QDialog):
    def __init__(
        self,
        config: AppConfig,
        config_path: Path,
        anki_client: AnkiConnectClient,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config_path = config_path
        self.anki_client = anki_client
        self._config = config
        self._decks: list[str] = []
        self._models: list[str] = []

        self.setWindowTitle("Anki Agent — Settings")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)

        hotkeys_group = QGroupBox("Hotkeys")
        hotkeys_form = QFormLayout(hotkeys_group)
        self.preview_edit = QLineEdit(config.hotkeys.preview)
        hotkeys_form.addRow("Preview:", self.preview_edit)
        self.quick_add_edit = QLineEdit(config.hotkeys.quick_add)
        hotkeys_form.addRow("Quick add:", self.quick_add_edit)
        layout.addWidget(hotkeys_group)

        anki_group = QGroupBox("Anki")
        anki_form = QFormLayout(anki_group)

        deck_row = QHBoxLayout()
        self.deck_combo = QComboBox()
        deck_row.addWidget(self.deck_combo, stretch=1)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._reload_anki_lists)
        deck_row.addWidget(refresh_btn)
        new_deck_btn = QPushButton("New deck…")
        new_deck_btn.clicked.connect(self._new_deck)
        deck_row.addWidget(new_deck_btn)
        deck_widget = QWidget()
        deck_widget.setLayout(deck_row)
        anki_form.addRow("Deck:", deck_widget)

        note_row = QHBoxLayout()
        self.note_type_combo = QComboBox()
        note_row.addWidget(self.note_type_combo, stretch=1)
        new_note_btn = QPushButton("New note type…")
        new_note_btn.clicked.connect(self._new_note_type)
        note_row.addWidget(new_note_btn)
        note_widget = QWidget()
        note_widget.setLayout(note_row)
        anki_form.addRow("Note type:", note_widget)

        self.fields_label = QLabel()
        self.fields_label.setWordWrap(True)
        anki_form.addRow("Fields:", self.fields_label)

        layout.addWidget(anki_group)

        history_group = QGroupBox("History")
        history_form = QFormLayout(history_group)
        self.save_history_check = QCheckBox("Save history when generating cards")
        self.save_history_check.setChecked(config.behavior.save_history)
        history_form.addRow(self.save_history_check)
        layout.addWidget(history_group)

        layout.addWidget(
            QLabel("<small>Open Anki before Refresh. Field layout is chosen automatically from the note type.</small>")
        )

        self.note_type_combo.currentTextChanged.connect(self._update_fields_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._reload_anki_lists()
        self._select_current_values()

    def _reload_anki_lists(self) -> None:
        deck_current = self.deck_combo.currentText()
        note_current = self.note_type_combo.currentText()
        try:
            self._decks = self.anki_client.deck_names()
            self._models = self.anki_client.model_names()
        except AnkiConnectError as exc:
            QMessageBox.warning(
                self,
                "AnkiConnect",
                f"{exc}\n\nOpen Anki to load decks and note types.",
            )
            self._decks = []
            self._models = []

        self.deck_combo.clear()
        if self._decks:
            self.deck_combo.addItems(self._decks)
        else:
            self.deck_combo.addItem("(Anki unavailable)")

        self.note_type_combo.clear()
        if self._models:
            self.note_type_combo.addItems(self._models)
        else:
            self.note_type_combo.addItem("(Anki unavailable)")

        if deck_current:
            idx = self.deck_combo.findText(deck_current)
            if idx >= 0:
                self.deck_combo.setCurrentIndex(idx)
        if note_current:
            idx = self.note_type_combo.findText(note_current)
            if idx >= 0:
                self.note_type_combo.setCurrentIndex(idx)

        self._update_fields_label(self.note_type_combo.currentText())

    def _select_current_values(self) -> None:
        deck = self._config.selected_deck
        if deck:
            if self.deck_combo.findText(deck) < 0:
                self.deck_combo.addItem(deck)
            self.deck_combo.setCurrentText(deck)

        note_type = self._config.note_type
        if note_type:
            if self.note_type_combo.findText(note_type) < 0:
                self.note_type_combo.addItem(note_type)
            self.note_type_combo.setCurrentText(note_type)

        self._update_fields_label(note_type)

    def _update_fields_label(self, note_type: str) -> None:
        if not note_type or note_type.startswith("("):
            self.fields_label.setText("—")
            return
        try:
            names = self.anki_client.model_field_names(note_type)
            self.fields_label.setText(", ".join(names) if names else "—")
        except AnkiConnectError as exc:
            self.fields_label.setText(str(exc))

    def _new_note_type(self) -> None:
        dialog = NewNoteTypeDialog(self.anki_client, self._models, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.created_name:
            return
        self._reload_anki_lists()
        self.note_type_combo.setCurrentText(dialog.created_name)
        QMessageBox.information(
            self, "Note type created", f'Created note type: {dialog.created_name}'
        )

    def _new_deck(self) -> None:
        name, ok = QInputDialog.getText(self, "New deck", "Deck name:")
        if not ok or not name.strip():
            return
        deck = name.strip()
        try:
            self.anki_client.create_deck(deck)
        except AnkiConnectError as exc:
            QMessageBox.warning(self, "AnkiConnect", str(exc))
            return
        self._reload_anki_lists()
        self.deck_combo.setCurrentText(deck)
        QMessageBox.information(self, "Deck created", f"Created deck: {deck}")

    def _save(self) -> None:
        try:
            preview = validate_hotkey(self.preview_edit.text())
            quick_add = validate_hotkey(self.quick_add_edit.text())
        except HotkeyRegistrationError as exc:
            QMessageBox.warning(self, "Invalid hotkey", str(exc))
            return

        deck_name = self.deck_combo.currentText().strip()
        note_type = self.note_type_combo.currentText().strip()
        if not deck_name or deck_name.startswith("("):
            QMessageBox.warning(self, "Deck", "Choose a deck (Anki must be running).")
            return
        if not note_type or note_type.startswith("("):
            QMessageBox.warning(self, "Note type", "Choose a note type.")
            return

        self._config = load_config(self.config_path)
        self._config.hotkeys = HotkeysConfig(preview=preview, quick_add=quick_add)
        self._config.selected_deck = deck_name
        self._config.note_type = note_type
        self._config.behavior.save_history = self.save_history_check.isChecked()
        save_config(self.config_path, self._config)
        self.accept()

    @property
    def config(self) -> AppConfig:
        return self._config
