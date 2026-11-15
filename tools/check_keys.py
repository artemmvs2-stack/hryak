"""Проверка API-ключей локально, без отправки в чат.

Кладёте ключи в data/keys.txt (по одному в строке), запускаете:

    venv\\Scripts\\python.exe tools\\check_keys.py
    venv\\Scripts\\python.exe tools\\check_keys.py --base-url https://api.openai.com/v1 --model gpt-4o-mini
    venv\\Scripts\\python.exe tools\\check_keys.py --no-chat

Скрипт проверяет два уровня:
  1) GET /models — принимает ли провайдер ключ;
  2) POST /chat/completions с 1 токеном — есть ли реальный доступ к модели.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jarvis.config import load_config  # noqa: E402

KEYS_FILE = ROOT / "data" / "keys.txt"


def mask(key: str) -> str:
    if len(key) <= 12:
        return key[:4] + "***"
    return f"{key[:6]}...{key[-4:]}"


def load_keys(path: Path) -> list[str]:
    if not path.exists():
        return []
    keys = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            keys.append(line)
    return keys


def check_key(key: str, base_url: str, model: str, do_chat: bool) -> dict:
    result = {"key": mask(key), "models": "-", "chat": "-", "verdict": "?"}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    try:
        response = requests.get(f"{base_url}/models", headers=headers, timeout=20)
        result["models"] = str(response.status_code)
        if response.status_code in (401, 403):
            result["verdict"] = "недействителен"
            return result
    except Exception as exc:  # noqa: BLE001
        result["models"] = f"ERR {type(exc).__name__}"
        result["verdict"] = "сеть"
        return result

    if not do_chat:
        result["verdict"] = "ключ принят (без проверки модели)"
        return result

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }
    try:
        response = requests.post(
            f"{base_url}/chat/completions", headers=headers,
            data=json.dumps(payload), timeout=40,
        )
        result["chat"] = str(response.status_code)
        if response.status_code == 200:
            result["verdict"] = "РАБОТАЕТ"
        elif response.status_code in (401, 403):
            result["verdict"] = "недействителен"
        elif response.status_code == 402:
            result["verdict"] = "ключ верный, нет баланса"
        elif response.status_code == 404:
            result["verdict"] = "модель не найдена (проверьте --model)"
        elif response.status_code == 429:
            result["verdict"] = "лимит запросов, повторите позже"
        else:
            result["verdict"] = f"ошибка {response.status_code}"
    except Exception as exc:  # noqa: BLE001
        result["chat"] = f"ERR {type(exc).__name__}"
        result["verdict"] = "сеть"
    return result


def main() -> int:
    cfg = load_config()
    parser = argparse.ArgumentParser(description="Проверка API-ключей")
    parser.add_argument("--file", default=str(KEYS_FILE), help="файл с ключами")
    parser.add_argument("--base-url", default=cfg["llm"]["base_url"], help="адрес API")
    parser.add_argument("--model", default=cfg["llm"]["model"], help="модель для проверки")
    parser.add_argument("--no-chat", action="store_true", help="только /models, без запроса к модели")
    args = parser.parse_args()

    keys = load_keys(Path(args.file))
    if not keys:
        print(f"Нет ключей. Создайте файл {args.file} и вставьте ключи, по одному в строке.")
        return 1

    print(f"Провайдер: {args.base_url}")
    print(f"Модель:    {args.model}")
    print(f"Ключей:    {len(keys)}\n")

    working = []
    for key in keys:
        res = check_key(key, args.base_url.rstrip("/"), args.model, not args.no_chat)
        print(
            f"{res['key']:<18} /models={res['models']:<6} "
            f"/chat={res['chat']:<6} {res['verdict']}"
        )
        if res["verdict"] == "РАБОТАЕТ":
            working.append(key)

    print()
    if working:
        print(f"Рабочих ключей: {len(working)}")
        print("Вставьте лучший в config.json → llm.api_key")
    else:
        print("Рабочих ключей не найдено.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
