"""Constantes e caminhos compartilhados (sem dependência de wxPython)."""
from __future__ import annotations

import os
import sys
import webbrowser
from pathlib import Path

from version import __version__  # noqa: F401  (reexportado)

APP_NAME = "JW Notícias"
APP_TITLE = "JW Notícias — Feed acessível"


def data_dir() -> Path:
    root = Path(os.environ.get("APPDATA", Path.home())) / "JWNoticiasFeed"
    root.mkdir(parents=True, exist_ok=True)
    return root


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_path(name: str) -> Path:
    """Caminho de um recurso, tanto em desenvolvimento quanto no .exe do PyInstaller."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def open_folder(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606
    else:
        webbrowser.open(Path(path).as_uri())
