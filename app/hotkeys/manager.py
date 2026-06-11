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
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
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


# The `keyboard` library uses "windows" for the Super/Win key; our config uses "cmd".
_KB_LIB_KEY_MAP = {"cmd": "windows", "command": "windows", "meta": "windows"}


def _to_keyboard_lib_hotkey(hotkey: str) -> str:
    """Translate app hotkey format to keyboard-lib format."""
    parts = [p.strip().lower() for p in hotkey.split("+") if p.strip()]
    return "+".join(_KB_LIB_KEY_MAP.get(p, p) for p in parts)


class _KeyboardLibBackend:
    """Linux hotkey backend using the `keyboard` library (reads evdev directly).

    Works on both X11 and Wayland. Requires the process to run as root, or
    the user to be a member of the `input` group:

        sudo usermod -a -G input $USER   # then log out and back in
    """

    def __init__(self) -> None:
        self._pending: list[tuple[str, Callable[[], None]]] = []

    def register(self, hotkey: str, callback: Callable[[], None]) -> None:
        self._pending.append((hotkey, callback))
        logger.info("Queued keyboard-lib hotkey: %s", hotkey)

    def start(self) -> None:
        try:
            import keyboard as kb
        except ImportError as exc:
            raise HotkeyRegistrationError(
                "keyboard library not installed. Run: pip install keyboard"
            ) from exc

        try:
            for hotkey, callback in self._pending:
                translated = _to_keyboard_lib_hotkey(hotkey)
                kb.add_hotkey(translated, callback, suppress=False)
                logger.info("keyboard-lib hotkey registered: %s → %s", hotkey, translated)
        except PermissionError as exc:
            raise HotkeyRegistrationError(
                f"No permission to read input devices: {exc}\n"
                "Add yourself to the input group and re-login:\n"
                "  sudo usermod -a -G input $USER"
            ) from exc
        except Exception as exc:
            raise HotkeyRegistrationError(
                f"keyboard-lib failed to register hotkeys: {exc}"
            ) from exc

        logger.info("keyboard-lib hotkey listener started (%d combos)", len(self._pending))

    def stop(self) -> None:
        try:
            import keyboard as kb
            kb.remove_all_hotkeys()
        except Exception:
            pass

    def clear(self) -> None:
        self.stop()
        self._pending.clear()


# VK codes for digits (0x30–0x39) and letters (0x41–0x5A) are fixed on Windows
# and stable across keyboard layouts and modifier states.  Using them instead of
# key.char avoids two classes of bugs:
#   • Shift+9 → key.char='(' instead of '9'
#   • Ctrl+Q  → key.char='\x11' (control char) instead of 'q'
_VK_DIGITS = {c: str(c - 0x30) for c in range(0x30, 0x3A)}
_VK_LETTERS = {c: chr(c - 0x41 + ord("a")) for c in range(0x41, 0x5B)}
_VK_MAP = {**_VK_DIGITS, **_VK_LETTERS}


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
        if key.vk is not None and key.vk in _VK_MAP:
            return _VK_MAP[key.vk]
        if key.char and len(key.char) == 1:
            return key.char.lower()
    return None


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


class GlobalHotkeyManager:
    """Picks the best hotkey backend for the current platform:

    - macOS  → NSEvent monitor
    - Linux  → keyboard-lib (evdev, works on Wayland/X11) if available,
               falls back to pynput (XRecord, X11-only)
    - Other  → pynput
    """

    def __init__(self, log_path: Path | None = None) -> None:
        if log_path is not None:
            _setup_logging(log_path)
        self._backend: _PynputHotkeyBackend | _KeyboardLibBackend | object | None = None

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

        elif platform.system() == "Linux":
            try:
                import keyboard  # noqa: F401
                self._backend = _KeyboardLibBackend()
                logger.info("Using keyboard-lib (evdev) hotkey backend")
                return
            except ImportError:
                logger.warning(
                    "keyboard library not installed; falling back to pynput (may not work on Wayland). "
                    "Install with: pip install keyboard"
                )

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
