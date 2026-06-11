from __future__ import annotations

import logging
import platform
from pathlib import Path
from typing import Callable

from pynput import keyboard

logger = logging.getLogger(__name__)


class HotkeyRegistrationError(Exception):
    pass


def _setup_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def parse_hotkey_parts(hotkey: str) -> frozenset[str]:
    modifier_aliases = {
        "ctrl": "ctrl",
        "control": "ctrl",
        "shift": "shift",
        "alt": "alt",
        "option": "alt",
        "cmd": "cmd",
        "command": "cmd",
        "meta": "cmd",
    }
    parts = [p.strip().lower() for p in hotkey.split("+") if p.strip()]
    if not parts:
        raise HotkeyRegistrationError(f"Invalid hotkey: {hotkey}")

    normalized: set[str] = set()
    for part in parts:
        if part in modifier_aliases:
            normalized.add(modifier_aliases[part])
        elif part.startswith("f") and part[1:].isdigit() and 1 <= int(part[1:]) <= 24:
            normalized.add(part)
        elif len(part) == 1 or part.isdigit():
            normalized.add(part)
        else:
            raise HotkeyRegistrationError(f"Unknown key in hotkey: {hotkey}")
    return frozenset(normalized)


class _PynputHotkeyBackend:
    def __init__(self) -> None:
        self._combos: list[tuple[frozenset[str], Callable[[], None]]] = []
        self._pressed: set[str] = set()
        self._fired_for_press = False
        self._listener: keyboard.Listener | None = None

    def register(self, hotkey: str, callback: Callable[[], None]) -> None:
        parts = parse_hotkey_parts(hotkey)
        self._combos.append((parts, callback))
        logger.info("Registered pynput hotkey %s -> %s", hotkey, set(parts))

    def start(self) -> None:
        if not self._combos:
            raise HotkeyRegistrationError("No hotkeys registered.")
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
            suppress=False,
        )
        self._listener.start()
        logger.info("pynput hotkey listener started (%d combos)", len(self._combos))

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        self._pressed.clear()
        self._fired_for_press = False

    def clear(self) -> None:
        self.stop()
        self._combos.clear()

    def _on_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        name = _canonical_key(key)
        if name:
            self._pressed.add(name)
        if self._fired_for_press:
            return
        for parts, callback in self._combos:
            if parts.issubset(self._pressed):
                self._fired_for_press = True
                logger.info("pynput hotkey fired: %s", set(parts))
                callback()
                return

    def _on_release(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        name = _canonical_key(key)
        if name:
            self._pressed.discard(name)
        if not self._pressed:
            self._fired_for_press = False


def _canonical_key(key: keyboard.Key | keyboard.KeyCode) -> str | None:
    if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
        return "ctrl"
    if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
        return "shift"
    if key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr):
        return "alt"
    if key in (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r):
        return "cmd"
    if isinstance(key, keyboard.KeyCode):
        if key.char and len(key.char) == 1:
            return key.char.lower()
        vk_digits = {
            0x30: "0", 0x31: "1", 0x32: "2", 0x33: "3", 0x34: "4",
            0x35: "5", 0x36: "6", 0x37: "7", 0x38: "8", 0x39: "9",
        }
        if key.vk is not None and key.vk in vk_digits:
            return vk_digits[key.vk]
    return None


class GlobalHotkeyManager:
    """macOS: NSEvent monitor. Other platforms: pynput listener."""

    def __init__(self, log_path: Path | None = None) -> None:
        if log_path is not None:
            _setup_logging(log_path)
        self._backend: _PynputHotkeyBackend | object | None = None

    def _ensure_backend(self) -> None:
        if self._backend is not None:
            return
        if platform.system() == "Darwin":
            try:
                from app.hotkeys.macos import MacOSHotkeyManager

                self._backend = MacOSHotkeyManager()
                logger.info("Using macOS NSEvent hotkey backend")
                return
            except Exception as exc:
                logger.warning("NSEvent hotkeys unavailable, using pynput: %s", exc)
        self._backend = _PynputHotkeyBackend()
        logger.info("Using pynput hotkey backend")

    def register(self, hotkey: str, callback: Callable[[], None]) -> None:
        self._ensure_backend()
        assert self._backend is not None
        self._backend.register(hotkey, callback)

    def start(self) -> None:
        self._ensure_backend()
        assert self._backend is not None
        try:
            self._backend.start()
        except Exception as exc:
            raise HotkeyRegistrationError(str(exc)) from exc

    def stop(self) -> None:
        if self._backend is not None:
            self._backend.stop()

    def clear(self) -> None:
        self.stop()
        if self._backend is not None and hasattr(self._backend, "clear"):
            self._backend.clear()

    def shutdown(self) -> None:
        """Release global hotkey hooks so the process can exit."""
        self.clear()
        self._backend = None
