"""Установка: автозапуск + ярлык на рабочем столе."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jarvis import startup  # noqa: E402
from jarvis.tray import ensure_icon_file  # noqa: E402


def main() -> int:
    ensure_icon_file()
    print("Автозапуск:", "включён" if startup.enable() else "ОШИБКА")

    import win32com.client

    desktop = Path(os.path.expanduser("~")) / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    lnk = desktop / "Jarvis.lnk"
    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(str(lnk))
    shortcut.TargetPath = str(ROOT / "venv" / "Scripts" / "pythonw.exe")
    shortcut.Arguments = f'"{ROOT / "jarvis.py"}"'
    shortcut.WorkingDirectory = str(ROOT)
    shortcut.IconLocation = str(ROOT / "assets" / "jarvis.ico")
    shortcut.Description = "Jarvis - голосовой ассистент"
    shortcut.Save()
    print("Ярлык:", lnk, "->", lnk.exists())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
