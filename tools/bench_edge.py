"""Замер скорости edge-tts."""
from __future__ import annotations

import asyncio
import os
import time

import edge_tts

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "_bench.mp3")

TEXTS = [
    "Сейчас два часа пятнадцать минут.",
    "Открываю телеграм, сэр.",
    "Добрый вечер. Все системы в норме.",
    "Курс доллара восемьдесят два рубля.",
    "Записал, сэр.",
]


async def main() -> None:
    times = []
    for text in TEXTS:
        started = time.time()
        try:
            await asyncio.wait_for(
                edge_tts.Communicate(text, "ru-RU-DmitryNeural", rate="+10%").save(OUT),
                timeout=15,
            )
            dt = time.time() - started
            size = os.path.getsize(OUT) // 1024
            print(f"{dt:5.2f}s  size={size}KB  {text}")
            times.append(dt)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {type(exc).__name__} {text}")
        await asyncio.sleep(1.0)
    if times:
        print(f"min={min(times):.2f} avg={sum(times)/len(times):.2f} max={max(times):.2f}")


if __name__ == "__main__":
    asyncio.run(main())
