"""GigaAM worker: держит модель в памяти и распознаёт WAV по JSON-запросам.

Используется GigaAM v3 CTC в ONNX через onnx-asr: не нужны torch, ffmpeg
и torchaudio. Запускается отдельным процессом из venv_gigaam, общение —
по одной JSON-строке на stdin/stdout; вывод библиотек уходит в stderr.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback

PROTOCOL = sys.stdout
sys.stdout = sys.stderr  # библиотеки не должны ломать протокол

for stream in (sys.stdin, sys.stderr, PROTOCOL):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


def _send(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), file=PROTOCOL, flush=True)


def main() -> int:
    model_name = sys.argv[1] if len(sys.argv) > 1 else "gigaam-v3-ctc"
    model_path = sys.argv[2] if len(sys.argv) > 2 else None
    quantization = sys.argv[3] if len(sys.argv) > 3 else "int8"
    if quantization.lower() in {"", "none", "null", "fp32"}:
        quantization = None

    started = time.time()
    try:
        import onnx_asr  # noqa: PLC0415

        model = onnx_asr.load_model(
            model_name,
            model_path or None,
            quantization=quantization,
        )
    except Exception as exc:  # noqa: BLE001
        _send({"ready": False, "error": f"{type(exc).__name__}: {exc}"})
        traceback.print_exc()
        return 1

    _send(
        {
            "ready": True,
            "model": model_name,
            "quantization": quantization or "fp32",
            "load_seconds": round(time.time() - started, 1),
            "pid": os.getpid(),
        }
    )

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            _send({"ok": False, "error": "bad json"})
            continue

        request_id = request.get("id")
        started = time.time()
        try:
            text = model.recognize(str(request["wav"]))
            if isinstance(text, list):
                text = text[0] if text else ""
            _send(
                {
                    "id": request_id,
                    "ok": True,
                    "text": text,
                    "seconds": round(time.time() - started, 2),
                }
            )
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            _send(
                {
                    "id": request_id,
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
