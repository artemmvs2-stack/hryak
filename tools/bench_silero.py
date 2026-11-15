"""Замер скорости Silero на 48 кГц и 24 кГц."""
from __future__ import annotations

import logging
import sys
import tempfile
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis.silero import SileroEngine  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("bench")

cfg = {
    "silero": {
        "enabled": True,
        "speaker": "aidar",
        "sample_rate": 48000,
        "put_accent": True,
        "put_yo": True,
    }
}

TEXT = "Открываю яндекс браузер, сэр."


def main() -> None:
    engine = SileroEngine(cfg, log)
    engine.load_async()
    while not engine.ready and not engine._failed:  # noqa: SLF001
        time.sleep(0.2)

    out = Path(tempfile.gettempdir()) / "jarvis_silero_bench.wav"
    for sample_rate in (48000, 24000, 48000, 24000):
        engine.sample_rate = sample_rate
        started = time.time()
        ok = engine.synthesize(TEXT, out)
        elapsed = time.time() - started
        duration = 0.0
        if ok:
            with wave.open(str(out), "rb") as wav:
                duration = wav.getnframes() / wav.getframerate()
        print(f"{sample_rate:>6} Гц: синтез {elapsed:5.2f} с, аудио {duration:5.2f} с, ok={ok}")


if __name__ == "__main__":
    main()
