from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
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


def _read_primary_selection_linux() -> str | None:
    """Read X11/Wayland primary selection (highlighted text) without simulating keystrokes.

    On Linux, any highlighted text is immediately placed in the PRIMARY selection buffer,
    so we can read it directly without Ctrl+C — and without triggering an XRecord/XTest
    conflict that causes segfaults when a pynput Listener is already running.
    """
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-paste"):
        try:
            r = subprocess.run(
                ["wl-paste", "--primary", "--no-newline"],
                capture_output=True, text=True, timeout=2,
            )
            if r.returncode == 0:
                return r.stdout
        except Exception:
            pass

    if shutil.which("xclip"):
        try:
            r = subprocess.run(
                ["xclip", "-selection", "primary", "-o"],
                capture_output=True, text=True, timeout=2,
            )
            if r.returncode == 0:
                return r.stdout
        except Exception:
            pass

    if shutil.which("xsel"):
        try:
            r = subprocess.run(
                ["xsel", "--primary", "--output"],
                capture_output=True, text=True, timeout=2,
            )
            if r.returncode == 0:
                return r.stdout
        except Exception:
            pass

    return None


def _simulate_copy_other() -> None:
    """Linux/Windows: simulate Ctrl+C to copy the active selection to clipboard.

    On Linux, prefer xdotool via subprocess to avoid the XRecord/XTest conflict
    that occurs when pynput's Controller is used while a pynput Listener is running.

    On Windows, the hotkey that triggered this call (e.g. Ctrl+Shift+9) may still
    have Shift physically held at the moment we run. Sending Ctrl+C with Shift held
    makes browsers receive Ctrl+Shift+C (opens DevTools) instead of copying.
    We release all extra modifiers first via SendInput before pressing Ctrl+C.
    """
    if platform.system() == "Linux" and shutil.which("xdotool"):
        try:
            r = subprocess.run(
                ["xdotool", "key", "--clearmodifiers", "ctrl+c"],
                capture_output=True, timeout=2,
            )
            if r.returncode == 0:
                return
        except Exception:
            pass

    from pynput.keyboard import Controller, Key

    controller = Controller()

    if platform.system() == "Windows":
        # Release Shift and Alt so they do not combine with the synthetic Ctrl+C.
        for mod in (Key.shift, Key.shift_l, Key.shift_r, Key.alt, Key.alt_l, Key.alt_r):
            try:
                controller.release(mod)
            except Exception:
                pass

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
        _os = platform.system()
        if _os == "Darwin":
            hint = (
                "Enable Accessibility for Cursor or Terminal "
                "in System Settings → Privacy & Security, then restart the app."
            )
        elif _os == "Linux":
            hint = (
                "Could not send copy shortcut. "
                "Install xdotool (sudo apt install xdotool) or grant X11 access."
            )
        else:
            hint = "Could not send copy shortcut."
        raise ClipboardError(hint) from exc


def capture_selected_text(restore_clipboard: bool = True) -> str:
    """Copy the current selection and return clipboard text.

    On Linux, highlighted text lands in the X11/Wayland PRIMARY selection automatically,
    so we read it directly with xclip/xsel/wl-paste without simulating Ctrl+C.  This
    avoids the XRecord ↔ XTest conflict that causes a segmentation fault when a pynput
    Listener is already running.  If PRIMARY is unavailable we fall back to the
    Ctrl+C-then-read-clipboard path.
    """
    if platform.system() == "Linux":
        primary = _read_primary_selection_linux()
        if primary is not None:
            text = primary.strip()
            if text:
                _validate_selection(text)
                return text

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

    if text == (previous or "").strip():
        raise ClipboardError(
            "Clipboard did not change after the copy shortcut — "
            "the app that holds your selection may have ignored it.\n"
            "Make sure the word is highlighted and that window is focused, then try again."
        )

    _validate_selection(text)
    return text
