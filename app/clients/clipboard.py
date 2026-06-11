from __future__ import annotations

import platform
import re
import time

import pyperclip


class ClipboardError(Exception):
    pass


# Suspicious patterns that indicate the selection is not a word or a phrase.
_SUSPICIOUS_PATTERNS = [
    re.compile(r"bus error", re.I),
    re.compile(r"zsh:", re.I),
    re.compile(r"bash:", re.I),
    re.compile(r"python -m\s", re.I),
    re.compile(r"Traceback \(most recent", re.I),
    re.compile(r"ModuleNotFoundError", re.I),
    re.compile(r"pip install", re.I),
    re.compile(r"\.venv/", re.I),
]

# macOS virtual key code for "c"
_MAC_KEY_C = 8


def _validate_selection(text: str) -> None:
    if len(text) > 120:
        raise ClipboardError(
            "Selection is too long. Highlight one word or a short phrase, not a whole paragraph."
        )
    if text.count("\n") >= 2:
        raise ClipboardError(
            "Selection spans multiple lines. Highlight a single word or phrase."
        )
    for pattern in _SUSPICIOUS_PATTERNS:
        if pattern.search(text):
            raise ClipboardError(
                "Captured text looks like Terminal output, not your selection. "
                "Click the app with the word, highlight it, "
                "then try again while that app is focused."
            )


def _simulate_copy_macos() -> None:
    """Cmd+C via Quartz — avoids a second pynput hook (prevents trace trap crashes)."""
    try:
        import Quartz
    except ImportError as exc:
        raise ClipboardError(
            "Missing pyobjc-framework-Quartz. Run: pip install pyobjc-framework-Quartz"
        ) from exc

    flags = Quartz.kCGEventFlagMaskCommand
    for key_down in (True, False):
        event = Quartz.CGEventCreateKeyboardEvent(None, _MAC_KEY_C, key_down)
        Quartz.CGEventSetFlags(event, flags)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def _simulate_copy_other() -> None:
    from pynput.keyboard import Controller, Key

    controller = Controller()
    with controller.pressed(Key.ctrl):
        controller.press("c")
        controller.release("c")


def _simulate_copy() -> None:
    try:
        if platform.system() == "Darwin":
            _simulate_copy_macos()
        else:
            _simulate_copy_other()
    except ClipboardError:
        raise
    except Exception as exc:
        raise ClipboardError(
            "Could not send copy shortcut. Enable Accessibility for Cursor or Terminal "
            "in System Settings, then restart the app."
        ) from exc


def capture_selected_text(restore_clipboard: bool = True) -> str:
    """Copy the current selection and return clipboard text."""
    previous = pyperclip.paste()

    _simulate_copy()
    time.sleep(0.35)
    selected = pyperclip.paste()

    if restore_clipboard:
        pyperclip.copy(previous)

    text = (selected or "").strip()
    if not text:
        raise ClipboardError(
            "Nothing was copied. Highlight a word, "
            "click that window so it is active, then try again."
        )

    _validate_selection(text)
    return text
