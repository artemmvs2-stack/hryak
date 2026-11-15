"""Иконка в системном трее."""
from __future__ import annotations

import webbrowser
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

from .config import ROOT
from . import startup


def make_icon_image(size: int = 64) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((2, 2, size - 3, size - 3), fill=(8, 18, 28, 255), outline=(0, 210, 255, 255), width=3)
    draw.ellipse((16, 16, size - 17, size - 17), outline=(0, 235, 255, 255), width=3)
    draw.ellipse((26, 26, size - 27, size - 27), fill=(130, 245, 255, 255))
    return img


def ensure_icon_file() -> Path:
    path = ROOT / "assets" / "jarvis.ico"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        make_icon_image(256).save(
            path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (256, 256)]
        )
    return path


class Tray:
    def __init__(self, cfg, listener, speaker, log, on_quit) -> None:
        self.cfg = cfg
        self.listener = listener
        self.speaker = speaker
        self.log = log
        self.on_quit = on_quit
        wake_name = str((cfg.get("wake_words") or ["Джарвис"])[0]).capitalize()
        self.icon = pystray.Icon(
            "jarvis",
            make_icon_image(),
            f"{wake_name} — слушаю",
            menu=pystray.Menu(
                pystray.MenuItem(f"Слушать (скажите «{wake_name}»)", self._listen, default=True),
                pystray.MenuItem("Остановить речь", self._stop_speech),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Открыть журнал", self._open_log),
                pystray.MenuItem("Открыть папку Jarvis", self._open_folder),
                pystray.MenuItem(
                    "Автозапуск",
                    self._toggle_autostart,
                    checked=lambda item: startup.is_enabled(),
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Выход", self._quit),
            ),
        )

    # ------------------------------------------------------------------
    def _listen(self, icon=None, item=None) -> None:  # noqa: ANN001
        self.listener.trigger_manual()

    def _stop_speech(self, icon=None, item=None) -> None:  # noqa: ANN001
        self.speaker.stop()

    def _open_log(self, icon=None, item=None) -> None:  # noqa: ANN001
        log_file = ROOT / "logs" / "jarvis.log"
        if log_file.exists():
            webbrowser.open(log_file.as_uri())

    def _open_folder(self, icon=None, item=None) -> None:  # noqa: ANN001
        webbrowser.open(ROOT.as_uri())

    def _toggle_autostart(self, icon=None, item=None) -> None:  # noqa: ANN001
        if startup.is_enabled():
            startup.disable()
            self.log.info("Автозапуск отключён")
        else:
            startup.enable()
            self.log.info("Автозапуск включён")

    def _quit(self, icon=None, item=None) -> None:  # noqa: ANN001
        self.listener.stop()
        self.icon.stop()
        if self.on_quit:
            self.on_quit()

    def run(self) -> None:
        self.icon.run()
