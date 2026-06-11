from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from app.clients.anki_connect import AnkiConnectClient, AnkiConnectError

SIDE_FRONT = "front"
SIDE_BACK = "back"


class NewNoteTypeDialog(QDialog):
    def __init__(
        self,
        anki_client: AnkiConnectClient,
        existing_models: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.anki_client = anki_client
        self.created_name: str | None = None
        self._side_combos: list[tuple[str, QComboBox]] = []

        self.setWindowTitle("New note type")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Fields on the <b>front</b> are the question. On the <b>back</b>, "
                "front fields repeat above the line, then back fields appear below "
                "(like Anki Basic)."
            )
        )
        layout.addWidget(
            QLabel(
                "<span style='color:#666'>Example: Word → front, Definition → back.</span>"
            )
        )

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("My vocabulary")
        form.addRow("Name:", self.name_edit)

        self.fields_edit = QLineEdit("Front, Back")
        self.fields_edit.setPlaceholderText("Front, Back")
        self.fields_edit.textChanged.connect(self._rebuild_side_rows)
        form.addRow("Fields:", self.fields_edit)

        layout.addLayout(form)

        self._sides_form = QFormLayout()
        self._sides_form.setContentsMargins(0, 8, 0, 0)
        layout.addLayout(self._sides_form)

        buttons = QDialogButtonBox()
        buttons.addButton("Create", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._create)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._existing = {m.lower() for m in existing_models}
        self._rebuild_side_rows()

    def _parse_fields(self, raw: str) -> list[str]:
        names = [part.strip() for part in raw.split(",") if part.strip()]
        if not names:
            raise ValueError("Enter at least one field name (e.g. Front, Back).")
        if len(set(names)) != len(names):
            raise ValueError("Field names must be unique.")
        return names

    def _previous_sides(self) -> dict[str, str]:
        sides: dict[str, str] = {}
        for name, combo in self._side_combos:
            sides[name] = combo.currentData(Qt.ItemDataRole.UserRole)
        return sides

    def _rebuild_side_rows(self) -> None:
        previous = self._previous_sides()
        while self._sides_form.rowCount():
            self._sides_form.removeRow(0)
        self._side_combos.clear()

        try:
            field_names = self._parse_fields(self.fields_edit.text())
        except ValueError:
            hint = QLabel("Enter comma-separated field names above.")
            hint.setStyleSheet("color: #666;")
            self._sides_form.addRow(hint)
            return

        if len(field_names) > 1:
            self._sides_form.addRow(QLabel("<b>Card layout</b>"))

        for index, name in enumerate(field_names):
            combo = QComboBox()
            combo.addItem("Front (question)", SIDE_FRONT)
            combo.addItem("Back (answer)", SIDE_BACK)
            default = previous.get(name)
            if default is None:
                default = SIDE_FRONT if index == 0 else SIDE_BACK
            idx = combo.findData(default, Qt.ItemDataRole.UserRole)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            self._side_combos.append((name, combo))
            self._sides_form.addRow(f"{name}:", combo)

    def _field_sides(self, field_names: list[str]) -> tuple[list[str], list[str]]:
        front_fields: list[str] = []
        back_fields: list[str] = []
        for name in field_names:
            combo = next(c for n, c in self._side_combos if n == name)
            side = combo.currentData(Qt.ItemDataRole.UserRole)
            if side == SIDE_FRONT:
                front_fields.append(name)
            else:
                back_fields.append(name)
        return front_fields, back_fields

    def _create(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Name required", "Enter a note type name.")
            return
        if name.lower() in self._existing:
            QMessageBox.warning(self, "Already exists", f'Note type "{name}" already exists.')
            return
        try:
            field_names = self._parse_fields(self.fields_edit.text())
            front_fields, back_fields = self._field_sides(field_names)
            if not front_fields:
                raise ValueError("At least one field must be on the front of the card.")
            self.anki_client.create_model(
                name,
                field_names,
                front_fields=front_fields,
                back_fields=back_fields,
            )
            self.created_name = name
        except (AnkiConnectError, ValueError) as exc:
            QMessageBox.warning(self, "Could not create note type", str(exc))
            return
        self.accept()
