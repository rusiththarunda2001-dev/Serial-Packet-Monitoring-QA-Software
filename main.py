"""Docklight application entry point."""

import os
import sys
from pathlib import Path


def _configure_tcl_tk():
    """Point Tcl/Tk at bundled libraries for venv and Windows Python layouts."""
    if os.environ.get("TCL_LIBRARY") and os.environ.get("TK_LIBRARY"):
        return

    search_roots = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        search_roots.append(Path(meipass))
    for base in (Path(sys.base_prefix), Path(sys.prefix)):
        if base not in search_roots:
            search_roots.append(base)

    local_python = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python"
    if local_python.is_dir():
        for install_root in sorted(local_python.glob("Python*"), reverse=True):
            if install_root not in search_roots:
                search_roots.append(install_root)

    for root in search_roots:
        tcl_candidates = (
            root / "tcl" / "tcl8.6",
            root / "Lib" / "tcl8.6",
        )
        tk_candidates = (
            root / "tcl" / "tk8.6",
            root / "Lib" / "tk8.6",
        )

        for tcl_dir in tcl_candidates:
            if not (tcl_dir / "init.tcl").is_file():
                continue
            os.environ.setdefault("TCL_LIBRARY", str(tcl_dir))
            for tk_dir in tk_candidates:
                if (tk_dir / "tk.tcl").is_file():
                    os.environ.setdefault("TK_LIBRARY", str(tk_dir))
                    return
            return


def main():
    _configure_tcl_tk()

    try:
        from ui.home_page import HomePage
    except ImportError as exc:
        print("Failed to import the home page:", exc, file=sys.stderr)
        print("Run this file from the project folder:", Path(__file__).resolve().parent, file=sys.stderr)
        sys.exit(1)

    project_path = sys.argv[1] if len(sys.argv) > 1 else None

    try:
        app = HomePage()
    except Exception as exc:
        print("Could not open the Docklight window:", exc, file=sys.stderr)
        print(file=sys.stderr)
        print("Try running with the project virtual environment:", file=sys.stderr)
        print("  .venv\\Scripts\\python.exe main.py", file=sys.stderr)
        sys.exit(1)

    if project_path:
        try:
            app.load_project_from_path(project_path)
        except Exception as exc:
            from core.project_file import ProjectFileError

            if isinstance(exc, ProjectFileError):
                print("Could not open project file:", exc, file=sys.stderr)
            else:
                print("Could not open project file:", exc, file=sys.stderr)
            sys.exit(1)

    app.mainloop()


if __name__ == "__main__":
    main()



