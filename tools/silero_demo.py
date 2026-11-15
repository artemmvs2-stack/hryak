"""Демонстрация офлайн-голосов Silero."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jarvis.silero import SileroEngine  # noqa: E402

TEXT = "Добрый вечер, сэр. Все системы в норме. Чем могу помочь?"
VOICES = [("aidar", "Айдар"), ("eugene", "Евгений"), ("baya", "Бая")]


def main() -> int:
    class Log:
        def info(self, *a, **k):
            print("[i]", *a)

        warning = error = exception = info

    cfg = {"silero": {"speaker": "aidar"}}
    engine = SileroEngine(cfg, Log())
    print("Загружаю модель...")
    engine.load_async()
    if not engine._ready.wait(timeout=180) or engine.model is None:
        print("Модель не загрузилась.")
        return 1

    import pygame

    pygame.mixer.init(frequency=48000, size=-16, channels=1, buffer=1024)

    out_dir = ROOT / "data" / "silero_demo"
    out_dir.mkdir(parents=True, exist_ok=True)

    for speaker, title in VOICES:
        engine.speaker = speaker
        path = out_dir / f"{speaker}.wav"
        started = time.time()
        if not engine.synthesize(TEXT, path):
            print("не удалось:", speaker)
            continue
        print(f"{title}: синтез {time.time() - started:.1f} с, файл {path.stat().st_size // 1024} КБ")
        pygame.mixer.music.load(str(path))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        time.sleep(1.0)
    print("Готово. Файлы в", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
