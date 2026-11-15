"""Диагностика звука: микрофон + распознавание синтезированной фразы.

Запуск: venv\\Scripts\\python.exe tools\\audio_test.py
"""
from __future__ import annotations

import audioop
import json
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sounddevice as sd  # noqa: E402
from vosk import KaldiRecognizer, Model, SetLogLevel  # noqa: E402

PHRASES = ["Джарвис, который час", "Джарвис, открой блокнот"]


def check_microphone() -> None:
    print("=== Микрофон ===")
    try:
        default = sd.query_devices(kind="input")
        print("Устройство:", default["name"], "| каналов:", default["max_input_channels"])
        frames = []
        with sd.RawInputStream(samplerate=16000, blocksize=4000, dtype="int16", channels=1,
                               callback=lambda indata, *a: frames.append(bytes(indata))):
            time.sleep(1.5)
        audio = b"".join(frames)
        rms = audioop.rms(audio, 2) if audio else 0
        peak = audioop.max(audio, 2) if audio else 0
        print(f"Записано {len(audio)} байт, RMS={rms}, пик={peak}")
        print("Микрофон:", "работает" if peak > 0 else "тишина (нет сигнала)")
    except Exception as exc:  # noqa: BLE001
        print("ОШИБКА микрофона:", exc)


def synth_wav(text: str, path: Path) -> None:
    import pyttsx3

    engine = pyttsx3.init()
    engine.setProperty("rate", 175)
    engine.save_to_file(text, str(path))
    engine.runAndWait()
    engine.stop()


def recognize(path: Path) -> str:
    with wave.open(str(path), "rb") as wav:
        rate = wav.getframerate()
        raw = wav.readframes(wav.getnframes())
    if rate != 16000:
        raw, _ = audioop.ratecv(raw, 2, 1, rate, 16000, None)
    model = Model(str(ROOT / "models" / "vosk-model-small-ru-0.22"))
    rec = KaldiRecognizer(model, 16000)
    rec.SetWords(True)
    chunk = 4000
    texts = []
    for i in range(0, len(raw), chunk):
        if rec.AcceptWaveform(raw[i:i + chunk]):
            texts.append(json.loads(rec.Result()).get("text", ""))
    texts.append(json.loads(rec.FinalResult()).get("text", ""))
    return " ".join(t for t in texts if t)


def main() -> int:
    SetLogLevel(-1)
    check_microphone()
    print("\n=== Распознавание ===")
    tmp = ROOT / "data" / "tts_test.wav"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    for phrase in PHRASES:
        synth_wav(phrase, tmp)
        heard = recognize(tmp)
        ok = "джарвис" in heard.lower()
        print(f"Сказано: {phrase!r}\nУслышано: {heard!r}  -> wake-word: {'OK' if ok else 'НЕТ'}")
    tmp.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
