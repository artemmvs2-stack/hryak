"""Самопроверка команд без микрофона и без озвучки.

Запуск: venv\\Scripts\\python.exe tools\\selftest.py
Результат: data\\selftest.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jarvis.brain import Brain  # noqa: E402
from jarvis.config import load_config  # noqa: E402

COMMANDS = [
    "привет",
    "который час",
    "какая сегодня дата",
    "какой сегодня день недели",
    "что ты умеешь",
    "погода",
    "погода в Санкт-Петербурге",
    "курс доллара",
    "курс евро",
    "новости",
    "заряд батареи",
    "загрузка процессора",
    "громкость на 30",
    "громче",
    "тише",
    "скриншот",
    "запиши заметку купить молоко",
    "прочитай заметки",
    "напомни через 2 минуты проверить тест",
    "открой блокнот",
    "открой калькулятор",
    "закрой блокнот",
    "стоп",
    "придумай название для кота",
]


class FakeSpeaker:
    def __init__(self) -> None:
        self.said: list[str] = []

    @property
    def is_speaking(self) -> bool:
        return False

    def say(self, text: str, block: bool = True) -> None:
        self.said.append(text)

    def stop(self) -> None:
        pass


class Log:
    def info(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        pass

    warning = error = exception = info


def main() -> int:
    cfg = load_config()
    cfg["llm"]["enabled"] = False

    log = Log()
    speaker = FakeSpeaker()
    brain = Brain(cfg, speaker, log, on_exit=None)

    results = []
    for cmd in COMMANDS:
        speaker.said.clear()
        started = time.time()
        try:
            brain.handle(cmd)
        except Exception as exc:  # noqa: BLE001
            results.append({"command": cmd, "error": repr(exc)})
            continue
        results.append(
            {
                "command": cmd,
                "answer": speaker.said[-1] if speaker.said else None,
                "seconds": round(time.time() - started, 2),
            }
        )
        time.sleep(0.2)

    out = ROOT / "data" / "selftest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written {out} ({len(results)} commands)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
