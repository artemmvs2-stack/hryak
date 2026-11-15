"""Синтез речи: edge-tts (живой голос) -> Silero (офлайн) -> SAPI (крайний случай)."""
from __future__ import annotations

import asyncio
import hashlib
import re
import tempfile
import threading
import time
from pathlib import Path

from .config import ROOT
from .piper_engine import PiperEngine
from .silero import SileroEngine

CACHE_DIR = ROOT / "data" / "tts_cache"
CACHE_LIMIT = 300
MAX_CHUNK_CHARS = 140


def clean_for_speech(text: str) -> str:
    """Убираем markdown и лишние символы, чтобы голос звучал естественно."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"[*_#`>|]+", " ", text)
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
    text = re.sub(r"https?://\S+", "ссылка", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_for_speech(text: str, limit: int = MAX_CHUNK_CHARS) -> list[str]:
    """Делит ответ на короткие фразы: так edge-tts реже срывается,
    а первая фраза начинает звучать раньше."""
    text = text.strip()
    if not text:
        return []

    parts = re.split(r"(?<=[.!?…])\s+", text)
    chunks: list[str] = []
    current = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if not current:
            current = part
        elif len(current) + 1 + len(part) <= limit:
            current += " " + part
        else:
            chunks.append(current)
            current = part
    if current:
        chunks.append(current)

    result: list[str] = []
    for chunk in chunks:
        while len(chunk) > limit:
            cut = chunk.rfind(", ", 0, limit)
            if cut < limit // 2:
                cut = chunk.rfind(" ", 0, limit)
            if cut <= 0:
                cut = limit
            result.append(chunk[:cut].strip())
            chunk = chunk[cut:].lstrip(" ,")
        if chunk:
            result.append(chunk)
    return result


def _cache_path(text: str, voice: str, rate: str, pitch: str) -> Path:
    digest = hashlib.sha1(f"{text}|{voice}|{rate}|{pitch}".encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.mp3"


def _piper_cache_path(text: str, voice: str) -> Path:
    digest = hashlib.sha1(f"piper|{text}|{voice}".encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.wav"


def _prune_cache() -> None:
    try:
        files = list(CACHE_DIR.glob("*.mp3")) + list(CACHE_DIR.glob("*.wav"))
        files.sort(key=lambda p: p.stat().st_mtime)
        for old in files[:-CACHE_LIMIT]:
            old.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass


class Speaker:
    def __init__(self, cfg: dict, log) -> None:
        self.cfg = cfg
        self.log = log
        self.engine = cfg.get("tts_engine", "edge")
        self.voice = cfg.get("voice", "ru-RU-DmitryNeural")
        self.rate = cfg.get("voice_rate", "+10%")
        self.pitch = cfg.get("voice_pitch", "")
        self._lock = threading.Lock()
        self._speaking = threading.Event()
        self._stop = threading.Event()
        self._pygame = None
        self._edge_failures = 0

        try:
            import pygame  # noqa: PLC0415

            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
            self._pygame = pygame
        except Exception as exc:  # noqa: BLE001
            log.warning("pygame недоступен: %s", exc)

        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        self.silero: SileroEngine | None = None
        if cfg.get("silero", {}).get("enabled", True):
            # грузим лениво: только если edge-tts не справится
            self.silero = SileroEngine(cfg, log)

        self.piper: PiperEngine | None = None
        if cfg.get("piper", {}).get("enabled", False):
            self.piper = PiperEngine(cfg, log)
            self.piper.load_async()

    # ------------------------------------------------------------------
    @property
    def is_speaking(self) -> bool:
        return self._speaking.is_set()

    def stop(self) -> None:
        self._stop.set()
        if self._pygame is not None:
            try:
                self._pygame.mixer.music.stop()
            except Exception:  # noqa: BLE001
                pass

    def say(self, text: str, block: bool = True) -> None:
        text = clean_for_speech(text)
        if not text:
            return
        if block:
            self._speak(text)
        else:
            threading.Thread(target=self._speak, args=(text,), daemon=True).start()

    # ------------------------------------------------------------------
    def _speak(self, text: str) -> None:
        with self._lock:
            self._stop.clear()
            self._speaking.set()
            started = time.time()
            engines_used: list[str] = []
            order = self._engine_order()
            chosen: str | None = None
            try:
                for chunk in split_for_speech(text):
                    if self._stop.is_set():
                        break
                    chunk_order = (
                        order
                        if chosen is None
                        else [chosen] + [engine for engine in order if engine != chosen]
                    )
                    engine = self._speak_chunk(chunk, chunk_order)
                    engines_used.append(engine)
                    chosen = engine
            except Exception as exc:  # noqa: BLE001
                self.log.error("Ошибка озвучки: %s", exc)
                try:
                    self._tts_sapi(text)
                    engines_used.append("sapi")
                except Exception as exc2:  # noqa: BLE001
                    self.log.error("SAPI тоже не сработал: %s", exc2)
            finally:
                used = "+".join(dict.fromkeys(e for e in engines_used if e)) or "sapi"
                self.log.info(
                    "Озвучка: %s, %.2f с, %s", used, time.time() - started, text[:80]
                )
                self._speaking.clear()

    def _engine_order(self) -> list[str]:
        if self.engine == "piper":
            return ["piper", "edge", "silero"]
        if self.engine == "silero":
            return ["silero", "piper", "edge"]
        return ["edge", "piper", "silero"]

    def _speak_chunk(self, text: str, order: list[str]) -> str:
        for engine in order:
            if engine == "edge":
                path, from_cache = self._edge_render(text)
                if path is not None:
                    try:
                        if self._play(path):
                            return "edge"
                    finally:
                        if not from_cache:
                            path.unlink(missing_ok=True)
            elif engine == "piper" and self._piper_say(text):
                return "piper"
            elif engine == "silero" and self._silero_say(text):
                return "silero"
        self._tts_sapi(text)
        return "sapi"

    def _piper_say(self, text: str) -> bool:
        if self.piper is None or self._pygame is None:
            return False
        cached = _piper_cache_path(text, self.piper.voice)
        if cached.exists() and cached.stat().st_size > 44:
            return self._play(cached)
        wav = Path(tempfile.gettempdir()) / f"jarvis_piper_{abs(hash(text)) % 10**8}.wav"
        if not self.piper.synthesize(text, wav):
            return False
        try:
            played = self._play(wav)
            if played:
                try:
                    import shutil  # noqa: PLC0415

                    shutil.copyfile(wav, cached)
                    _prune_cache()
                except Exception:  # noqa: BLE001
                    pass
            return played
        finally:
            wav.unlink(missing_ok=True)

    def _silero_say(self, text: str) -> bool:
        if self.silero is None or self._pygame is None:
            return False
        wav = Path(tempfile.gettempdir()) / f"jarvis_{abs(hash(text)) % 10**8}.wav"
        if not self.silero.synthesize(text, wav):
            return False
        return self._play(wav)

    def _play(self, path: Path) -> bool:
        pygame = self._pygame
        if pygame is None:
            return False
        try:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
            deadline = time.time() + 120
            while pygame.mixer.music.get_busy() and not self._stop.is_set():
                if time.time() > deadline:
                    break
                time.sleep(0.05)
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
            return True
        except Exception as exc:  # noqa: BLE001
            self.log.warning("Не удалось воспроизвести %s: %s", path, exc)
            return False

    # ------------------------------------------------------------------
    def _edge_render(self, text: str) -> tuple[Path | None, bool]:
        """Синтезирует фразу. Возвращает (путь, из_кэша) или (None, False)."""
        if self._pygame is None:
            return None, False

        import edge_tts  # noqa: PLC0415

        cached = _cache_path(text, self.voice, self.rate, self.pitch)
        if cached.exists() and cached.stat().st_size > 0:
            return cached, True

        stem = abs(hash(text)) % 10**8
        rate = self.rate or None
        pitch = self.pitch or None
        tempdir = Path(tempfile.gettempdir())
        budget = 8.0
        started = time.time()

        # Первая попытка — с настроенной скоростью, вторая — без неё (другой запрос,
        # иногда помогает, когда сервис отдаёт пустой ответ на конкретные параметры).
        attempts = [(rate, pitch), (None, None)]

        for attempt, (attempt_rate, attempt_pitch) in enumerate(attempts):
            left = budget - (time.time() - started)
            if left <= 0:
                break
            path = tempdir / f"jarvis_{stem}_{attempt}.mp3"
            path.unlink(missing_ok=True)
            kwargs = {"voice": self.voice}
            if attempt_rate:
                kwargs["rate"] = attempt_rate
            if attempt_pitch:
                kwargs["pitch"] = attempt_pitch

            async def _render(target: Path = path, params: dict = kwargs) -> None:
                await edge_tts.Communicate(text, **params).save(str(target))

            try:
                asyncio.run(asyncio.wait_for(_render(), timeout=min(3.5, left)))
                if path.exists() and path.stat().st_size > 1024:
                    self._edge_failures = 0
                    try:
                        import shutil  # noqa: PLC0415

                        shutil.copyfile(path, cached)
                        _prune_cache()
                    except Exception:  # noqa: BLE001
                        pass
                    return path, False
            except Exception as exc:  # noqa: BLE001
                self.log.debug("edge-tts попытка %s: %s", attempt + 1, exc)
            finally:
                if not path.exists() or path.stat().st_size <= 1024:
                    path.unlink(missing_ok=True)

            # пауза перед следующей попыткой: серверу нужно время восстановиться
            if attempt + 1 < len(attempts):
                time.sleep(1.0)

        self._edge_failures += 1
        self.log.warning(
            "edge-tts не ответил (%s сбоев подряд), фразу озвучит Silero",
            self._edge_failures,
        )
        return None, False

    def _tts_sapi(self, text: str) -> None:
        import pyttsx3  # noqa: PLC0415

        engine = pyttsx3.init()
        wanted = self.cfg.get("sapi_voice", "")
        if wanted:
            for voice in engine.getProperty("voices"):
                if wanted.lower() in (voice.name or "").lower():
                    engine.setProperty("voice", voice.id)
                    break
        engine.setProperty("rate", 185)
        engine.say(text)
        engine.runAndWait()
        try:
            engine.stop()
        except Exception:  # noqa: BLE001
            pass
