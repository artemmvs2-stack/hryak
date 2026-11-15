"""Генерация и проигрывание образцов Piper."""
from __future__ import annotations

import time
import wave
from pathlib import Path

import pygame
from piper.voice import PiperVoice

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models" / "piper"
OUT = ROOT / "data" / "piper_samples"
TEXT = "Джарвис на связи, сэр. Все системы работают штатно."


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=1024)
    for voice_name in ("ruslan", "denis"):
        model_path = MODELS / f"ru_RU-{voice_name}-medium.onnx"
        started = time.time()
        voice = PiperVoice.load(str(model_path))
        load_time = time.time() - started
        out_path = OUT / f"{voice_name}.wav"
        started = time.time()
        with wave.open(str(out_path), "wb") as wav:
            voice.synthesize_wav(TEXT, wav)
        synth_time = time.time() - started
        with wave.open(str(out_path), "rb") as wav:
            duration = wav.getnframes() / wav.getframerate()
            rate = wav.getframerate()
        print(
            f"{voice_name:8} загрузка {load_time:4.2f} с, синтез {synth_time:4.2f} с, "
            f"аудио {duration:4.2f} с, {rate} Гц -> {out_path}"
        )
        pygame.mixer.music.load(str(out_path))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.05)
        pygame.mixer.music.unload()
        time.sleep(1.0)


if __name__ == "__main__":
    main()
