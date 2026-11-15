"""Офлайн-синтез речи Silero (русские голоса, работает без интернета)."""
from __future__ import annotations

import os
import threading
import time
import wave
from pathlib import Path

import numpy as np

from .config import ROOT

MODEL_URL = "https://models.silero.ai/models/tts/ru/v4_ru.pt"
MODEL_PATH = ROOT / "models" / "silero_v4_ru.pt"

VOICES = {
    "aidar": "Айдар — низкий мужской",
    "eugene": "Евгений — мужской",
    "baya": "Бая — женский",
    "kseniya": "Ксения — женский",
    "xenia": "Ксения — женский",
    "random": "случайный",
}


class SileroEngine:
    def __init__(self, cfg: dict, log) -> None:
        self.cfg = cfg
        self.log = log
        params = cfg.get("silero", {})
        self.speaker = params.get("speaker", "aidar")
        self.sample_rate = int(params.get("sample_rate", 48000))
        self.put_accent = bool(params.get("put_accent", True))
        self.put_yo = bool(params.get("put_yo", True))
        self.model = None
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._loading = threading.Lock()
        self._failed = False

    # ------------------------------------------------------------------
    @property
    def ready(self) -> bool:
        return self.model is not None

    def load_async(self) -> None:
        if self._ready.is_set() or not self._loading.acquire(blocking=False):
            return
        threading.Thread(target=self._load, daemon=True, name="silero-load").start()

    def _download(self) -> bool:
        if MODEL_PATH.exists() and MODEL_PATH.stat().st_size > 10_000_000:
            return True
        self.log.info("Скачиваю модель Silero (~60 МБ)...")
        try:
            import requests

            MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = MODEL_PATH.with_suffix(".part")
            with requests.get(MODEL_URL, stream=True, timeout=60) as response:
                response.raise_for_status()
                with tmp.open("wb") as fh:
                    for chunk in response.iter_content(1024 * 256):
                        fh.write(chunk)
            tmp.replace(MODEL_PATH)
            self.log.info("Модель Silero загружена: %.1f МБ", MODEL_PATH.stat().st_size / 1e6)
            return True
        except Exception as exc:  # noqa: BLE001
            self.log.error("Не удалось скачать Silero: %s", exc)
            return False

    def _load(self) -> None:
        try:
            import ctypes  # noqa: PLC0415
            import importlib.util  # noqa: PLC0415

            torch_spec = importlib.util.find_spec("torch")
            if torch_spec and torch_spec.origin:
                libdir = Path(torch_spec.origin).parent / "lib"
                if libdir.exists():
                    os.add_dll_directory(str(libdir))  # type: ignore[attr-defined]
                    for dll in (
                        "torch_global_deps.dll",
                        "c10.dll",
                        "torch_cpu.dll",
                        "torch_python.dll",
                    ):
                        candidate = libdir / dll
                        if candidate.exists():
                            try:
                                ctypes.WinDLL(str(candidate))
                            except OSError:
                                pass

            import torch  # noqa: PLC0415
            from torch.package import PackageImporter  # noqa: PLC0415

            torch.set_num_threads(max(2, (os.cpu_count() or 4) - 1))
            if not self._download():
                self._failed = True
                return
            started = time.time()
            importer = PackageImporter(str(MODEL_PATH))
            self.model = importer.load_pickle("tts_models", "model", map_location="cpu")
            self.model.to(torch.device("cpu"))
            self.log.info(
                "Silero готов за %.1f с, голос %s", time.time() - started, self.speaker
            )
        except Exception as exc:  # noqa: BLE001
            self.log.error("Silero не загрузился: %s", exc)
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
            if not self._ready.wait(timeout=90):
                return False
        if self.model is None:
            return False
        try:
            with self._lock:
                audio = self.model.apply_tts(
                    text=text,
                    speaker=self.speaker,
                    sample_rate=self.sample_rate,
                    put_accent=self.put_accent,
                    put_yo=self.put_yo,
                )
            data = (audio.detach().cpu().numpy() * 32767).astype(np.int16)
            path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(self.sample_rate)
                wav.writeframes(data.tobytes())
            return path.exists() and path.stat().st_size > 44
        except Exception as exc:  # noqa: BLE001
            self.log.error("Ошибка синтеза Silero: %s", exc)
            return False
