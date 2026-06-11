from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QStyle,
    QVBoxLayout,
    QWidget,
    QLabel,
)

from app.clients.anki_connect import AnkiConnectClient
from app.core.config import load_config
from app.core.models import AppConfig
from app.hotkeys.manager import GlobalHotkeyManager, HotkeyRegistrationError
from app.hotkeys.qt_bridge import HotkeyBridge
from app.storage.history import HistoryStore
from app.ui.card_service import CardCreationService
from app.ui.history_window import HistoryWindow
from app.ui.settings_window import SettingsWindow


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


class AnkiAgentApp:
    def __init__(self) -> None:
        self.root = _project_root()
        self.config_path = self.root / "config.yaml"
        self.config = load_config(self.config_path)
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.qt_app.aboutToQuit.connect(self._shutdown)

        self.history_store = HistoryStore(self.root / "data" / "app.db")
        self.anki_client = AnkiConnectClient(self.config.anki.url)
        self.hotkey_manager = GlobalHotkeyManager(self.root / "data" / "hotkeys.log")
        self.hotkey_bridge: HotkeyBridge | None = None
        self.tray: QSystemTrayIcon | None = None
        self.status_window: QWidget | None = None
        self._hotkeys_label: QLabel | None = None
        self._anki_label: QLabel | None = None
        self.card_service: CardCreationService | None = None
        self._shutting_down = False
        self._force_close = False

    def _notify(self, title: str, message: str) -> None:
        if self.tray is not None and self.tray.isVisible():
            try:
                # On Linux, showMessage goes through org.freedesktop.Notifications via DBus, which may fail if the notification daemon is absent.
                self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 4000)
                return
            except Exception as exc:
                logger.warning("tray.showMessage failed, falling back to dialog: %s", exc)
        QMessageBox.information(None, title, message)

    @staticmethod
    def _selectable_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _update_status_labels(self) -> None:
        preview = self.config.hotkeys.preview
        quick = self.config.hotkeys.quick_add
        deck = self.config.selected_deck or "—"
        note_type = self.config.note_type or "—"
        if self._hotkeys_label is not None:
            self._hotkeys_label.setText(
                f"<b>Preview</b> <code>{preview}</code> — review, then add or cancel<br>"
                f"<b>Quick add</b> <code>{quick}</code> — add to Anki immediately"
            )
        if self._anki_label is not None:
            self._anki_label.setText(
                f"Deck <code>{deck}</code> · Note type <code>{note_type}</code>"
            )

    def _populate_app_menu(self, menu: QMenu, *, include_show_window: bool = False) -> None:
        preview_action = QAction("Preview from selection", menu)
        quick_action = QAction("Quick add from selection", menu)
        if self.card_service is not None:
            preview_action.triggered.connect(self.card_service.run_preview)
            quick_action.triggered.connect(self.card_service.run_quick_add)
        menu.addAction(preview_action)
        menu.addAction(quick_action)

        menu.addSeparator()
        settings_action = QAction("Settings…", menu)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)

        history_action = QAction("History…", menu)
        history_action.triggered.connect(self._open_history)
        menu.addAction(history_action)

        if include_show_window:
            show_action = QAction("Show window", menu)
            show_action.triggered.connect(self._show_status_window)
            menu.addAction(show_action)

        menu.addSeparator()
        quit_action = QAction("Quit", menu)
        quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        quit_action.triggered.connect(self._request_quit)
        menu.addAction(quit_action)

    def _build_status_window(self) -> QMainWindow:
        window = QMainWindow()
        window.setWindowTitle("Anki Agent")

        menu_bar = window.menuBar()
        app_menu = menu_bar.addMenu("Anki Agent")
        self._populate_app_menu(app_menu)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        layout.addWidget(self._selectable_label("<b style='font-size:15px'>Anki Agent</b>"))

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        self._hotkeys_label = self._selectable_label("")
        layout.addWidget(self._hotkeys_label)

        self._anki_label = self._selectable_label("")
        layout.addWidget(self._anki_label)

        layout.addWidget(
            self._selectable_label(
                "<span style='color:#666'>Select text, "
                "keep that app focused, then press a hotkey.</span>"
            )
        )

        settings_btn = QPushButton("Settings…")
        settings_btn.clicked.connect(self._open_settings)
        layout.addWidget(settings_btn)

        self._update_status_labels()
        window.setCentralWidget(central)
        window.setFixedSize(400, 220)
        window.closeEvent = self._on_status_window_close  # type: ignore[method-assign]
        return window

    def _on_status_window_close(self, event: QCloseEvent) -> None:
        if self._force_close:
            event.accept()
            return
        event.ignore()
        self._request_quit()

    def _request_quit(self) -> None:
        self.qt_app.quit()

    def _shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        if self.card_service is not None:
            self.card_service.shutdown()
        self.hotkey_manager.shutdown()
        if self.tray is not None:
            self.tray.hide()
            self.tray.setVisible(False)
            self.tray.deleteLater()
            self.tray = None
        if self.status_window is not None:
            self._force_close = True
            self.status_window.close()
            self.status_window.deleteLater()
            self.status_window = None

    def _build_tray_menu(self) -> QMenu:
        menu = QMenu()
        self._populate_app_menu(menu, include_show_window=True)
        return menu

    def _show_status_window(self) -> None:
        if self.status_window is None:
            return
        self.status_window.show()
        self.status_window.raise_()
        self.status_window.activateWindow()

    def _open_settings(self) -> None:
        dialog = SettingsWindow(
            self.config,
            self.config_path,
            self.anki_client,
            self.status_window,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self._apply_config(dialog.config)
        self._update_status_labels()

        try:
            self._reload_hotkeys()
            self._notify("Settings saved", "Settings updated.")
        except HotkeyRegistrationError as exc:
            QMessageBox.warning(
                self.status_window,
                "Hotkeys not applied",
                f"Settings were saved to config.yaml, but hotkeys could not start:\n\n{exc}",
            )

    def _apply_config(self, config: AppConfig) -> None:
        self.config = config
        if self.card_service is not None:
            self.card_service.config = config

    def _open_history(self) -> None:
        dialog = HistoryWindow(self.history_store, parent=self.status_window)
        dialog.exec()

    def _register_hotkeys(self) -> list[str]:
        if self.card_service is None:
            raise RuntimeError("Card service not initialized")

        if self.hotkey_bridge is None:
            self.hotkey_bridge = HotkeyBridge(self.card_service)

        errors: list[str] = []
        bindings = [
            ("preview", self.config.hotkeys.preview, self.hotkey_bridge.request_preview),
            ("quick_add", self.config.hotkeys.quick_add, self.hotkey_bridge.request_quick_add),
        ]

        for name, hotkey, callback in bindings:
            try:
                self.hotkey_manager.register(hotkey, callback)
            except HotkeyRegistrationError as exc:
                errors.append(f"{name} ({hotkey}): {exc}")

        if not errors:
            try:
                self.hotkey_manager.start()
            except Exception as exc:
                errors.append(str(exc))

        return errors

    def _reload_hotkeys(self) -> None:
        self.hotkey_manager.clear()
        errors = self._register_hotkeys()
        if errors:
            raise HotkeyRegistrationError("\n".join(errors))

    def run(self) -> int:
        self.status_window = self._build_status_window()
        self.card_service = CardCreationService(
            config=self.config,
            anki_client=self.anki_client,
            history_store=self.history_store,
            notify=self._notify,
            parent_widget=self.status_window,
        )
        icon = self.qt_app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        try:
            # QSystemTrayIcon requires a running DBus session on Linux; guard against environments where the system tray or notification daemon is unavailable.
            if QSystemTrayIcon.isSystemTrayAvailable():
                self.tray = QSystemTrayIcon(icon)
                self.tray.setToolTip("Anki Agent")
                self.tray.setContextMenu(self._build_tray_menu())
                self.tray.activated.connect(self._on_tray_activated)
                self.tray.show()
        except Exception as exc:
            logger.warning("System tray unavailable, notifications will use dialogs: %s", exc)
            self.tray = None

        errors = self._register_hotkeys()
        if errors:
            import platform as _platform
            _os = _platform.system()
            if _os == "Darwin":
                os_hint = (
                    "On macOS, grant Accessibility to Terminal or Cursor in "
                    "System Settings → Privacy & Security → Accessibility."
                )
            elif _os == "Linux":
                os_hint = (
                    "On Linux, pynput needs access to X11 keyboard events.\n"
                    "• X11/XWayland must be running (XRecord extension required).\n"
                    "• Install xdotool and xclip for clipboard support:\n"
                    "  sudo apt install xdotool xclip\n"
                    "• If you see a DBusException, check that a DBus session is active."
                )
            else:
                os_hint = "Open Settings (menu bar or tray) to fix hotkeys."
            QMessageBox.warning(
                self.status_window,
                "Hotkeys unavailable",
                (
                    "Global hotkeys could not be registered:\n\n"
                    + "\n".join(errors)
                    + "\n\n"
                    + os_hint
                ),
            )

        self._show_status_window()
        return self.qt_app.exec()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.status_window and self.status_window.isVisible():
                self.status_window.hide()
            else:
                self._show_status_window()
