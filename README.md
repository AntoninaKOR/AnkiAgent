# Anki Agent

Local desktop app that turns selected text into Anki cards via global hotkeys.

## Requirements

- Python 3.11+
- [Anki](https://apps.ankiweb.net/) with the [AnkiConnect](https://foosoft.net/projects/anki-connect/) add-on
- **Linux only:** `xdotool` and `xclip` (or `xsel`) for clipboard and hotkey support

## Install

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**Linux — install system dependencies:**

```bash
sudo apt install xdotool xclip
```

**Linux — grant input device access (required for global hotkeys on Wayland and X11):**

The `keyboard` library reads `/dev/input/` directly and works on both X11 and Wayland.
It requires the user to be in the `input` group:

```bash
sudo usermod -a -G input $USER
```

Then **log out and log back in** for the group change to take effect.
After that, run `pip install -r requirements.txt` to install the `keyboard` package.

In Anki, create a deck or pick an existing one. Choose a note type in **Settings** (default: `Basic`).

## Run

```bash
python -m app.main
```

A status window and system tray icon appear. Leave the app running in the background.

**If global hotkeys do nothing**, use the menu bar or tray menu. Check `data/hotkeys.log` to see whether hotkeys fire.

## Hotkeys

Configured in `config.yaml`:

| Shortcut | Mode | Behavior |
|----------|------|----------|
| `cmd+shift+9` | Preview | Generate card → preview window → Add to Anki or Cancel |
| `cmd+shift+q` | Quick add | Generate card → add to Anki immediately → notification |

Change shortcuts, **deck**, and **note type** in **Anki Agent → Settings…** (or tray menu). Use **New deck…** or **New note type…** to create them in Anki (Anki must be running).

**macOS** — copy simulation uses **Cmd+C** (via Quartz); grant Accessibility to Terminal in System Settings → Privacy & Security if hotkeys do nothing.  
**Linux** — highlighted text is read from the X11/Wayland PRIMARY selection via `xclip`/`xsel`/`wl-paste`; no Ctrl+C simulation needed.  
**Windows** — copy simulation uses **Ctrl+C** via pynput.

## Flow

1. Select a word or phrase.
2. Keep that app focused and press a hotkey.
3. The app copies the selection, calls the LLM (fake for now) with your **note type** and its fields, and builds a card.
4. Optional row in `data/app.db` if history is enabled in Settings.
5. **Preview:** review fields, then add or cancel. **Quick add:** adds immediately.

## Configuration

`config.yaml`:

- `hotkeys.preview` / `hotkeys.quick_add` — global shortcuts
- `note_type` / `selected_deck` — target in Anki
- `restore_clipboard` — restore clipboard after reading selection
- `anki.url` — AnkiConnect endpoint (default `http://127.0.0.1:8765`)
- `behavior.save_history` — log generations to SQLite

## History

Each card generation is optionally saved to a local SQLite database.

### View history in the app

1. Open the status window (click the tray icon or run `python -m app.main`).
2. In the menu bar or tray menu choose **History…**.
3. The table shows: time, mode (preview / quick add), selected text, note type, and status (Generated / Added / Error).
4. Hover over a row to see the full selection or error message in a tooltip.
5. Click **Refresh** to reload after new cards are added.
6. Click **Clear history…** to delete all records (asks for confirmation).

### Enable or disable saving

Go to **Settings… → History → Save history when generating cards** and toggle the checkbox.  
This writes `behavior.save_history` in `config.yaml`.

### Inspect the database directly

```bash
sqlite3 data/app.db "SELECT id, mode, selected_text, template_name, added_to_anki, created_at FROM card_history ORDER BY id DESC LIMIT 20;"
```

Table `card_history` columns:

| Column | Description |
|--------|-------------|
| `id` | Auto-increment row id |
| `mode` | `preview` or `quick_add` |
| `selected_text` | Text that was highlighted |
| `template_name` | Anki note type used |
| `generated_fields_json` | JSON with note type and all generated field values |
| `added_to_anki` | `1` if the note was sent to Anki, `0` otherwise |
| `anki_note_id` | Anki note id returned by AnkiConnect (if added) |
| `error` | Error message if something went wrong |
| `created_at` | UTC ISO-8601 timestamp |

## Project layout

```
app/
  main.py                    # Bootstrap (entry point)
  core/
    models.py                # Pydantic models (AppConfig, PreparedAnkiNote, …)
    config.py                # Load / save / validate config.yaml
    note_builder.py          # build_prepared_note, NoteBuildError
    card_worker.py           # QThread background worker
  llm/
    base.py                  # LLMClient protocol
    fake.py                  # FakeLLMClient (placeholder)
  clients/
    anki_connect.py          # AnkiConnect HTTP client
    clipboard.py             # Selection capture (PRIMARY selection on Linux, Cmd/Ctrl+C elsewhere)
  hotkeys/
    manager.py               # GlobalHotkeyManager (picks backend by OS)
    macos.py                 # macOS NSEvent backend
    qt_bridge.py             # Routes hotkey callbacks onto Qt main thread
  storage/
    history.py               # HistoryStore (SQLite)
  ui/
    app.py                   # AnkiAgentApp — tray, status window, lifecycle
    card_service.py          # CardCreationService — UI orchestration
    preview_window.py
    settings_window.py
    history_window.py
    new_note_type_dialog.py
config.yaml
data/
  app.db
```

## Notes

- Replace `FakeLLMClient` (`app/llm/fake.py`) with a real LLM by implementing the `LLMClient` protocol from `app/llm/base.py` and passing the instance to `CardCreationService`.

## TODO

- **Native Wayland global hotkeys.** Currently hotkeys on Linux rely on pynput → XRecord (X11 extension), which works in Wayland sessions only because XWayland is usually running alongside. A proper Wayland-native solution would use the [XDG Desktop Portal `GlobalShortcuts`](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.GlobalShortcuts.html) DBus API (`org.freedesktop.portal.GlobalShortcuts`), but not universally available. pynput does not implement this yet, so it would require a custom DBus integration.
