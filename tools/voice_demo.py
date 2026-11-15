"""Демонстрация вариантов голоса. Просто запустить и слушать."""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "voice_demo"

TEXT_RU = "Добрый вечер, сэр. Все системы в норме. Чем могу помочь?"
TEXT_EN = "Good evening, sir. All systems are operational. How may I assist you?"

VARIANTS = [
    ("1_мягкий", "ru-RU-DmitryNeural", "+5%", "-15Hz", TEXT_RU),
    ("2_глубокий", "ru-RU-DmitryNeural", "-5%", "-35Hz", TEXT_RU),
    ("3_стальной", "ru-RU-DmitryNeural", "-12%", "-50Hz", TEXT_RU),
    ("4_британец", "en-GB-ThomasNeural", "-5%", "-10Hz", TEXT_EN),
]


async def render(name: str, voice: str, rate: str, pitch: str, text: str) -> Path | None:
    path = OUT / f"{name}.mp3"
    for attempt in range(6):
        try:
            path.unlink(missing_ok=True)
            kwargs = {"voice": voice}
            if rate:
                kwargs["rate"] = rate
            if pitch:
                kwargs["pitch"] = pitch
            await edge_tts.Communicate(text, **kwargs).save(str(path))
            if path.exists() and path.stat().st_size > 0:
                return path
        except Exception as exc:  # noqa: BLE001
            print(f"  {name}: попытка {attempt + 1} ({type(exc).__name__})")
            await asyncio.sleep(2 + attempt * 1.5)
    return None


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    import pygame

    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)

    paths = []
    for name, voice, rate, pitch, text in VARIANTS:
        print("Готовлю:", name)
        path = asyncio.run(render(name, voice, rate, pitch, text))
        if path:
            paths.append(path)
            print("  готово")
        else:
            print("  пропущен (сервис не ответил)")
        time.sleep(1.0)

    if not paths:
        print("Не удалось получить ни одного образца — проверьте интернет/VPN.")
        return 1

    print("\nСлушайте по порядку:", ", ".join(p.stem for p in paths), "\n")
    for path in paths:
        print("Играет:", path.stem)
        pygame.mixer.music.load(str(path))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        time.sleep(1.2)
    print("Готово.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
