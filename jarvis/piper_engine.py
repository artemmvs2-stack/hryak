"""Офлайн-синтез речи Piper (нейросетевые русские голоса, работает без интернета)."""
from __future__ import annotations

import threading
import time
import wave
from pathlib import Path

from .config import ROOT

MODELS_DIR = ROOT / "models" / "piper"

VOICES = {
    "ruslan": "Руслан — мужской",
    "denis": "Денис — мужской",
    "irina": "Ирина — женский",
}


class PiperEngine:
    def __init__(self, cfg: dict, log) -> None:
        self.cfg = cfg
        self.log = log
        params = cfg.get("piper", {})
        self.voice = params.get("voice", "ruslan")
        self.model_path = MODELS_DIR / f"ru_RU-{self.voice}-medium.onnx"
        self.model = None
        self._lock = threading.Lock()
        self._loading = threading.Lock()
        self._ready = threading.Event()
        self._failed = False

    # ------------------------------------------------------------------
    @property
    def ready(self) -> bool:
        return self.model is not None

    def load_async(self) -> None:
        if self._ready.is_set() or not self._loading.acquire(blocking=False):
            return
        threading.Thread(target=self._load, daemon=True, name="piper-load").start()

    def _load(self) -> None:
        try:
            if not self.model_path.exists():
                self.log.error("Модель Piper не найдена: %s", self.model_path)
                self._failed = True
                return
            from piper.voice import PiperVoice  # noqa: PLC0415

            started = time.time()
            self.model = PiperVoice.load(str(self.model_path))
            self.log.info(
                "Piper готов за %.1f с, голос %s", time.time() - started, self.voice
            )
        except Exception as exc:  # noqa: BLE001
            self.log.error("Piper не загрузился: %s", exc)
            self._failed = True
        finally:
            self._ready.set()
            if self._loading.locked():
                try:
                    self._loading.release()
                except RuntimeError:
                    pass

    # ------------------------------------------------------------------
    def synthesize(self, text: str, path: Path) -> bool:
        if self.model is None:
            if self._failed:
                return False
            self.load_async()
            if not self._ready.wait(timeout=60):
                return False
        if self.model is None:
            return False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                with wave.open(str(path), "wb") as wav:
                    self.model.synthesize_wav(text, wav)
            return path.exists() and path.stat().st_size > 44
        except Exception as exc:  # noqa: BLE001
            self.log.error("Ошибка синтеза Piper: %s", exc)
            return False
