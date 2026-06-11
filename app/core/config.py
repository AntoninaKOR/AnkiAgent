from __future__ import annotations

from pathlib import Path

import yaml

from app.hotkeys.manager import HotkeyRegistrationError, parse_hotkey_parts
from app.core.models import AppConfig, HotkeysConfig


def validate_hotkey(hotkey: str) -> str:
    """Normalize and validate a hotkey string from config/UI."""
    parts = [p.strip().lower() for p in hotkey.split("+") if p.strip()]
    if not parts:
        raise HotkeyRegistrationError("Hotkey cannot be empty.")
    normalized = "+".join(parts)
    parse_hotkey_parts(normalized)
    return normalized


def load_config(path: Path) -> AppConfig:
    return AppConfig.load(path)


def save_config(path: Path, config: AppConfig) -> None:
    """Write config to YAML, preserving other sections."""
    if path.exists():
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    data.update(config.model_dump())
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def update_hotkeys(path: Path, preview: str, quick_add: str) -> AppConfig:
    preview_norm = validate_hotkey(preview)
    quick_add_norm = validate_hotkey(quick_add)
    config = load_config(path)
    config.hotkeys = HotkeysConfig(preview=preview_norm, quick_add=quick_add_norm)
    save_config(path, config)
    return config
