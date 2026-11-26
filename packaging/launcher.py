"""Entry point for the desktop builds (PyInstaller). Double-click starts the UI."""

import sys

from claude_env_manager.cli import main

if __name__ == "__main__":
    # Old macOS versions pass a -psn_ argument to apps opened from Finder.
    args = [a for a in sys.argv[1:] if not a.startswith("-psn_")]
    raise SystemExit(main(args or ["serve"]))
