"""Docklight application entry point."""

import os
import sys
from pathlib import Path


def _configure_tcl_tk():
    """Point Tcl/Tk at the bundled libraries inside the active Python prefix."""
    base = Path(getattr(sys, "_MEIPASS", sys.prefix))
    tcl_dir = base / "Lib" / "tcl8.6"
    tk_dir = base / "Lib" / "tk8.6"

    if tcl_dir.is_dir():
        os.environ.setdefault("TCL_LIBRARY", str(tcl_dir))
    if tk_dir.is_dir():
        os.environ.setdefault("TK_LIBRARY", str(tk_dir))


def main():
    _configure_tcl_tk()

    try:
        from ui.home_page import HomePage
    except ImportError as exc:
        print("Failed to import the home page:", exc, file=sys.stderr)
        print("Run this file from the project folder:", Path(__file__).resolve().parent, file=sys.stderr)
        sys.exit(1)

    try:
        app = HomePage()
    except Exception as exc:
        print("Could not open the Docklight window:", exc, file=sys.stderr)
        print(file=sys.stderr)
        print("Try running with the project virtual environment:", file=sys.stderr)
        print("  .venv\\Scripts\\python.exe main.py", file=sys.stderr)
        sys.exit(1)

    app.mainloop()


if __name__ == "__main__":
    main()
