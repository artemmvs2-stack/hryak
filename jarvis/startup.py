"""Автозапуск при входе в Windows (ярлык в папке Startup)."""
from __future__ import annotations

import os
from pathlib import Path

from .config import ROOT

LNK_PATH = (
    Path(os.environ.get("APPDATA", ""))
    / "Microsoft/Windows/Start Menu/Programs/Startup"
    / "Jarvis.lnk"
)


def _pythonw() -> Path:
    return ROOT / "venv" / "Scripts" / "pythonw.exe"


def is_enabled() -> bool:
    return LNK_PATH.exists()


def enable() -> bool:
    try:
        import win32com.client  # noqa: PLC0415

        LNK_PATH.parent.mkdir(parents=True, exist_ok=True)
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(LNK_PATH))
        shortcut.TargetPath = str(_pythonw())
        shortcut.Arguments = f'"{ROOT / "jarvis.py"}"'
        shortcut.WorkingDirectory = str(ROOT)
        shortcut.IconLocation = str(ROOT / "assets" / "jarvis.ico")
        shortcut.Description = "Jarvis — голосовой ассистент"
        shortcut.WindowStyle = 7  # свёрнутое окно
        shortcut.Save()
        return True
    except Exception:  # noqa: BLE001
        return False


def disable() -> bool:
    try:
        LNK_PATH.unlink(missing_ok=True)
        return True
    except Exception:  # noqa: BLE001
        return False
