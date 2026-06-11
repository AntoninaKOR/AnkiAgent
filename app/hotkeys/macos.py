from __future__ import annotations

import logging
from typing import Callable

from AppKit import (
    NSEvent,
    NSEventMaskKeyDown,
    NSEventModifierFlagCommand,
    NSEventModifierFlagControl,
    NSEventModifierFlagOption,
    NSEventModifierFlagShift,
)
from app.hotkeys.manager import HotkeyRegistrationError, parse_hotkey_parts

logger = logging.getLogger(__name__)

# US keyboard key codes (macOS)
_KEY_CODES: dict[str, int] = {
    "a": 0, "b": 11, "c": 8, "d": 2, "e": 14, "f": 3, "g": 5, "h": 4,
    "i": 34, "j": 38, "k": 40, "l": 37, "m": 46, "n": 45, "o": 31, "p": 35,
    "q": 12, "r": 15, "s": 1, "t": 17, "u": 32, "v": 9, "w": 13, "x": 7,
    "y": 16, "z": 6,
    "0": 29, "1": 18, "2": 19, "3": 20, "4": 21, "5": 23, "6": 22, "7": 26, "8": 28, "9": 25,
}


class MacOSHotkeyManager:
    """Global hotkeys via NSEvent (works reliably with Qt on macOS)."""

    def __init__(self) -> None:
        self._combos: list[tuple[frozenset[str], int | None, Callable[[], None]]] = []
        self._monitor = None

    def register(self, hotkey: str, callback: Callable[[], None]) -> None:
        parts = parse_hotkey_parts(hotkey)
        main_keys = [p for p in parts if p not in {"ctrl", "shift", "alt", "cmd"}]
        if len(main_keys) != 1:
            raise HotkeyRegistrationError(
                f"Hotkey must include exactly one main key: {hotkey}"
            )
        key = main_keys[0]
        key_code = _KEY_CODES.get(key)
        if key.startswith("f") and key[1:].isdigit():
            key_code = None  # function keys not mapped yet
        elif key_code is None:
            raise HotkeyRegistrationError(f"Unknown key in hotkey: {hotkey}")
        self._combos.append((parts, key_code, callback))
        logger.info("Registered macOS hotkey %s (keyCode=%s)", hotkey, key_code)

    def start(self) -> None:
        if not self._combos:
            raise HotkeyRegistrationError("No hotkeys registered.")

        def handler(event) -> None:
            flags = event.modifierFlags()
            pressed_mods: set[str] = set()
            if flags & NSEventModifierFlagCommand:
                pressed_mods.add("cmd")
            if flags & NSEventModifierFlagShift:
                pressed_mods.add("shift")
            if flags & NSEventModifierFlagControl:
                pressed_mods.add("ctrl")
            if flags & NSEventModifierFlagOption:
                pressed_mods.add("alt")

            key_code = event.keyCode()
            for parts, expected_code, callback in self._combos:
                if expected_code is not None and key_code != expected_code:
                    continue
                mod_parts = {p for p in parts if p in {"ctrl", "shift", "alt", "cmd"}}
                if mod_parts.issubset(pressed_mods):
                    logger.info("macOS hotkey fired (keyCode=%s)", key_code)
                    callback()
                    return

        self._monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSEventMaskKeyDown, handler
        )
        logger.info("macOS NSEvent hotkey monitor started (%d combos)", len(self._combos))

    def stop(self) -> None:
        if self._monitor is not None:
            NSEvent.removeMonitor_(self._monitor)
            self._monitor = None
            logger.info("macOS NSEvent hotkey monitor stopped")

    def clear(self) -> None:
        self.stop()
        self._combos.clear()
