"""A/B-тест edge-tts: с параметром rate и без него."""
from __future__ import annotations

import asyncio
import os
import time

import edge_tts

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "_ab.mp3")

TEXTS = [
    "Сегодня хорошая погода, сэр.",
    "Напоминаю о встрече в три часа.",
    "Все системы работают штатно.",
    "Курс доллара немного вырос.",
]


async def synthesize(text: str, rate: str | None) -> tuple[bool, float]:
    kwargs = {"voice": "ru-RU-DmitryNeural"}
    if rate:
        kwargs["rate"] = rate
    started = time.time()
    try:
        await asyncio.wait_for(
            edge_tts.Communicate(text, **kwargs).save(OUT), timeout=15
        )
        size = os.path.getsize(OUT) if os.path.exists(OUT) else 0
        return size > 1024, time.time() - started
    except Exception as exc:  # noqa: BLE001
        print(f"    {type(exc).__name__}: {str(exc)[:60]}")
        return False, time.time() - started


async def main() -> None:
    results = {"rate": [0, 0], "plain": [0, 0]}  # [успехи, всего]
    for text in TEXTS:
        for label, rate in (("rate", "+10%"), ("plain", None)):
            ok, elapsed = await synthesize(text, rate)
            results[label][1] += 1
            results[label][0] += int(ok)
            print(f"{label:5} {'OK  ' if ok else 'FAIL'} {elapsed:5.2f}s  {text}")
            await asyncio.sleep(8)
    print("\nИтог:")
    for label, (ok, total) in results.items():
        print(f"  {label:5}: {ok}/{total}")


if __name__ == "__main__":
    asyncio.run(main())
