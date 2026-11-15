"""Загрузка настроек Jarvis."""
from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"

DEFAULTS = {
    "wake_words": ["хряк", "хряг"],
    "model_dir": "models/vosk-model-small-ru-0.22",
    "sample_rate": 16000,
    "silence_timeout": 1.8,
    "max_command_seconds": 12,
    "followup_seconds": 30,
    "followup_allow_llm": False,
    "stt_engine": "vosk",
    "gigaam": {
        "enabled": False,
        "python": "venv_gigaam/Scripts/python.exe",
        "worker": "gigaam_worker.py",
        "model": "gigaam-v3-e2e-ctc",
        "quantization": "int8",
        "download_root": "models/gigaam_e2e",
        "timeout": 30,
        "threads": 4,
        "pre_roll_seconds": 3.0,
        "restarts": 2,
    },
    "voice": "ru-RU-DmitryNeural",
    "voice_rate": "+10%",
    "voice_pitch": "",
    "sapi_voice": "Microsoft Irina Desktop",
    "tts_engine": "edge",
    "silero": {
        "enabled": True,
        "speaker": "aidar",
        "sample_rate": 48000,
        "put_accent": True,
        "put_yo": True,
    },
    "piper": {
        "enabled": False,
        "voice": "denis",
    },
    "telegram": {
        "enabled": True,
        "aliases": {},
    },
    "city": "Москва",
    "search_engine": "yandex",
    "beep": True,
    "llm": {
        "enabled": True,
        "base_url": "https://ai.starimg.ru/v1",
        "api_key": "",
        "model": "gpt-6-astra",
        "max_tokens": 200,
        "temperature": 0.6,
        "history_messages": 6,
        "timeout": 60,
        "thinking_filler": "Секунду, сэр.",
        "computer_control": True,
        "tool_rounds": 3,
        "system_prompt": (
            "Ты — Хряк, голосовой ассистент в стиле Тони Старка. "
            "Отвечай по-русски, кратко (1-3 предложения), вежливо, обращайся 'сэр'. "
            "Без markdown, без списков и символов разметки — ответ будет озвучен. "
            "Если перечисляешь варианты — не больше трёх. "
            "Если не знаешь ответа, честно скажи об этом."
        ),
    },
    "log_level": "INFO",
}


def _deep_update(base: dict, extra: dict) -> dict:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def load_config() -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            user = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(user, dict):
                _deep_update(cfg, user)
        except Exception as exc:  # noqa: BLE001
            print(f"[config] не удалось прочитать config.json: {exc}")
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )
