"""Диагностика edge-tts: коды ответов и стабильность."""
from __future__ import annotations

import asyncio
import os
import time

import edge_tts
import requests

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "_bench.mp3")

TEXTS = [
    "Проверка один.",
    "Проверка два.",
    "Проверка три.",
    "Проверка четыре.",
    "Проверка пять.",
]


def check_http() -> None:
    url = (
        "https://speech.platform.bing.com/consumer/speech/synthesize/readaloud/voices/list"
        "?trustedclienttoken=6A5AA1D4EAFF4E9FB37E23D68491D6F4"
    )
    try:
        response = requests.get(url, timeout=20)
        print("voices/list HTTP", response.status_code, "bytes", len(response.content))
    except Exception as exc:  # noqa: BLE001
        print("voices/list ERROR", type(exc).__name__, exc)


async def main() -> None:
    check_http()
    ok = 0
    for i, text in enumerate(TEXTS, 1):
        started = time.time()
        try:
            await asyncio.wait_for(
                edge_tts.Communicate(text, "ru-RU-DmitryNeural").save(OUT), timeout=20
            )
            dt = time.time() - started
            print(f"#{i} OK   {dt:5.2f}s size={os.path.getsize(OUT)//1024}KB")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"#{i} FAIL {type(exc).__name__}: {str(exc)[:90]}")
        await asyncio.sleep(8)
    print(f"успешно {ok}/{len(TEXTS)}")


if __name__ == "__main__":
    asyncio.run(main())
