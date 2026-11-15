#!/usr/bin/env python
"""Jarvis — голосовой ассистент для Windows.

Запуск:
    python jarvis.py              # обычный режим (трей + прослушивание)
    python jarvis.py --text "во сколько закат"   # проверить команду без микрофона
    python jarvis.py --say "привет"              # проверить голос
    python jarvis.py --no-tray                   # без иконки в трее
"""
from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from jarvis import actions, startup  # noqa: E402
from jarvis.brain import Brain  # noqa: E402
from jarvis.config import load_config  # noqa: E402
from jarvis.speech import Listener  # noqa: E402
from jarvis.tray import Tray, ensure_icon_file  # noqa: E402
from jarvis.voice import Speaker  # noqa: E402

LOCK_PORT = 47831


def setup_logging(level: str) -> logging.Logger:
    logs = ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("jarvis")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    file_handler = RotatingFileHandler(
        logs / "jarvis.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(getattr(logging, level.upper(), logging.INFO))
    console.setFormatter(fmt)
    logger.addHandler(console)
    return logger


def acquire_single_instance():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", LOCK_PORT))
        sock.listen(1)
        return sock
    except OSError:
        sock.close()
        return None


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description="Jarvis voice assistant")
    parser.add_argument("--say", help="озвучить текст и выйти")
    parser.add_argument("--text", help="выполнить команду текстом (без микрофона)")
    parser.add_argument("--once", action="store_true", help="обработать одну голосовую команду и выйти")
    parser.add_argument("--no-tray", action="store_true", help="запустить без иконки в трее")
    parser.add_argument("--debug", action="store_true", help="подробный журнал")
    args = parser.parse_args()

    cfg = load_config()
    log = setup_logging("DEBUG" if args.debug else cfg.get("log_level", "INFO"))
    ensure_icon_file()
    wake_name = str((cfg.get("wake_words") or ["Джарвис"])[0]).capitalize()

    speaker = Speaker(cfg, log)

    if args.say:
        speaker.say(args.say)
        return 0

    stopped = threading.Event()
    app_state: dict = {"tray": None, "listener": None}

    def quit_app() -> None:
        stopped.set()
        if app_state["listener"] is not None:
            app_state["listener"].stop()
        if app_state["tray"] is not None:
            try:
                app_state["tray"].icon.stop()
            except Exception:  # noqa: BLE001
                pass
        time.sleep(0.4)
        os._exit(0)

    brain = Brain(cfg, speaker, log, on_exit=quit_app)
    if not args.text:
        threading.Thread(target=actions.warm_app_cache, daemon=True).start()

    if args.text:
        brain.handle(args.text)
        return 0

    listener = Listener(
        cfg,
        speaker,
        brain.handle,
        log,
        on_followup=(
            brain.handle
            if cfg.get("followup_allow_llm", False)
            else brain.handle_followup
        ),
    )
    app_state["listener"] = listener

    if not args.once:
        lock = acquire_single_instance()
        if lock is None:
            print("Jarvis уже запущен. Второй экземпляр не нужен.")
            return 1

    log.info("Запуск Jarvis %s", time.strftime("%d.%m.%Y %H:%M:%S"))
    if not listener.load_model():
        speaker.say("Не удалось загрузить модель распознавания речи, сэр.")
        return 2

    if args.once:
        result: dict = {}

        def once_handler(command: str) -> None:
            result["command"] = command
            brain.handle(command)
            quit_app()

        listener.on_command = once_handler
        listener.start()
        print(f"Скажите «{wake_name}» и команду...")
        deadline = time.time() + 60
        while time.time() < deadline and not stopped.is_set():
            time.sleep(0.2)
        if "command" not in result:
            print("Команда не распознана.")
            listener.stop()
            return 3
        return 0

    # приветствие произносим до начала прослушивания, чтобы не услышать себя
    speaker.say(f"{wake_name} на связи, сэр.")

    if args.no_tray:
        listener.start()
        try:
            while not stopped.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            quit_app()
        return 0

    tray = Tray(cfg, listener, speaker, log, quit_app)
    app_state["tray"] = tray
    listener.start()
    tray.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
