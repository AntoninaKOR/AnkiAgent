from __future__ import annotations

from app.ui.app import AnkiAgentApp


def main() -> None:
    app = AnkiAgentApp()
    raise SystemExit(app.run())


if __name__ == "__main__":
    main()
