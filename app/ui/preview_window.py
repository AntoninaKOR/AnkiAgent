from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.models import PreparedAnkiNote


class PreviewWindow(QDialog):
    def __init__(
        self,
        selected_text: str,
        prepared: PreparedAnkiNote,
        field_names: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._prepared = prepared
        self._field_edits: dict[str, QLineEdit] = {}

        self.setWindowTitle("Anki Agent — Preview")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Selected: <b>{selected_text}</b>"))
        layout.addWidget(QLabel(f"Deck: {prepared.deck} · Note type: {prepared.model}"))
        layout.addWidget(
            QLabel("<span style='color:#666'>Edit fields below before adding to Anki.</span>")
        )

        form_widget = QWidget()
        form = QFormLayout(form_widget)
        order = field_names if field_names else list(prepared.fields.keys())
        shown = False
        for name in order:
            if name not in prepared.fields:
                continue
            self._add_field_row(form, name, prepared.fields[name])
            shown = True
        for name, value in prepared.fields.items():
            if name in order:
                continue
            self._add_field_row(form, name, value)
            shown = True
        if not shown:
            form.addRow(QLabel("(no fields)"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_widget)
        scroll.setMaximumHeight(320)
        layout.addWidget(scroll)

        tags_label = QLabel("Tags: " + ", ".join(prepared.tags))
        tags_label.setWordWrap(True)
        layout.addWidget(tags_label)

        buttons = QDialogButtonBox()
        add_btn = buttons.addButton("Add to Anki", QDialogButtonBox.AcceptRole)
        cancel_btn = buttons.addButton("Cancel", QDialogButtonBox.RejectRole)
        add_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def _add_field_row(self, form: QFormLayout, label: str, value: str) -> None:
        field = QLineEdit(value)
        self._field_edits[label] = field
        form.addRow(f"{label}:", field)

    def edited_prepared(self) -> PreparedAnkiNote:
        fields = {name: edit.text() for name, edit in self._field_edits.items()}
        return self._prepared.model_copy(update={"fields": fields})
