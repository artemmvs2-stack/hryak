"""Заметки и напоминания (хранятся в data/)."""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from .config import ROOT

DATA_DIR = ROOT / "data"
NOTES_PATH = DATA_DIR / "notes.md"
REMINDERS_PATH = DATA_DIR / "reminders.json"


class Notes:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def add(self, text: str) -> None:
        stamp = datetime.now().strftime("%d.%m.%Y %H:%M")
        with NOTES_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"- [{stamp}] {text}\n")

    def last(self, count: int = 5) -> list[str]:
        if not NOTES_PATH.exists():
            return []
        lines = [
            ln.strip()
            for ln in NOTES_PATH.read_text(encoding="utf-8").splitlines()
            if ln.strip().startswith("-")
        ]
        return lines[-count:]


class Reminders:
    def __init__(self, speaker, log) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.speaker = speaker
        self.log = log
        self.items = self._load()
        self._lock = threading.Lock()
        threading.Thread(target=self._loop, daemon=True, name="reminders").start()

    # ------------------------------------------------------------------
    def _load(self) -> list[dict]:
        if not REMINDERS_PATH.exists():
            return []
        try:
            return [i for i in json.loads(REMINDERS_PATH.read_text(encoding="utf-8")) if i.get("due")]
        except Exception:  # noqa: BLE001
            return []

    def _save(self) -> None:
        REMINDERS_PATH.write_text(
            json.dumps(self.items, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def add(self, due: datetime, text: str) -> None:
        with self._lock:
            self.items.append({"due": due.isoformat(timespec="seconds"), "text": text})
            self._save()

    def upcoming(self, limit: int = 10) -> list[tuple[datetime, str]]:
        """Ближайшие напоминания: [(время, текст)] по возрастанию времени."""
        with self._lock:
            raw = list(self.items)
        result: list[tuple[datetime, str]] = []
        for item in raw:
            try:
                due = datetime.fromisoformat(item["due"])
            except Exception:  # noqa: BLE001
                continue
            result.append((due, str(item.get("text") or "")))
        result.sort(key=lambda pair: pair[0])
        return result[:limit]

    def cancel(self, query: str | None = None) -> list[str]:
        """Удаляет напоминания по подстроке (или все) и возвращает их тексты."""
        removed: list[str] = []
        needle = (query or "").strip().lower()
        with self._lock:
            keep: list[dict] = []
            for item in self.items:
                text = str(item.get("text") or "")
                if not needle or needle in text.lower():
                    removed.append(text)
                else:
                    keep.append(item)
            if removed:
                self.items = keep
                self._save()
        return removed

    def cancel_last(self, kind: str | None = None) -> str | None:
        """Удаляет напоминание с самой поздней датой (kind: timer/reminder)."""
        with self._lock:
            candidates = [
                (index, item)
                for index, item in enumerate(self.items)
                if self._matches_kind(item, kind)
            ]
            if not candidates:
                return None
            index, item = max(
                candidates, key=lambda pair: str(pair[1].get("due") or "")
            )
            self.items.pop(index)
            self._save()
        return str(item.get("text") or "")

    def clear(self, kind: str | None = None) -> int:
        """Удаляет все напоминания (или только таймеры/только напоминания)."""
        with self._lock:
            keep = [
                item for item in self.items if not self._matches_kind(item, kind)
            ]
            removed = len(self.items) - len(keep)
            if removed:
                self.items = keep
                self._save()
        return removed

    @staticmethod
    def _matches_kind(item: dict, kind: str | None) -> bool:
        if kind is None:
            return True
        is_timer = str(item.get("text") or "").startswith("Таймер")
        return is_timer if kind == "timer" else not is_timer

    def _loop(self) -> None:
        time.sleep(8)  # даём ассистенту поздороваться, не перебиваем
        while True:
            time.sleep(5)
            now = datetime.now()
            due_now = []
            with self._lock:
                for item in list(self.items):
                    try:
                        due = datetime.fromisoformat(item["due"])
                    except Exception:  # noqa: BLE001
                        self.items.remove(item)
                        continue
                    if due <= now:
                        due_now.append(item)
                        self.items.remove(item)
                if due_now:
                    self._save()
            for item in due_now:
                self.log.info("Напоминание: %s", item["text"])
                self.speaker.say(f"Напоминаю, сэр: {item['text']}", block=False)


# ----------------------------------------------------------------------
WORD_NUMBERS = {
    "пол": 0.5,
    "один": 1, "одну": 1, "два": 2, "две": 2, "три": 3, "четыре": 4,
    "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10,
    "пятнадцать": 15, "двадцать": 20, "тридцать": 30, "сорок": 40,
    "пятьдесят": 50, "шестьдесят": 60,
}


def _to_number(raw: str) -> float | None:
    raw = raw.strip()
    if raw.isdigit():
        return float(raw)
    return WORD_NUMBERS.get(raw)


def parse_reminder(text: str) -> tuple[datetime, str] | None:
    """Ищет 'через N минут' / 'через полчаса' / 'в 18:30' и остаток как текст."""
    m = re.search(
        r"(?:через|спустя)\s+(\d+|пол|один|одну|два|две|три|четыре|пять|шесть|семь|восемь|девять|десять|пятнадцать|двадцать|тридцать|сорок|пятьдесят|шестьдесят)?\s*"
        r"(час(?:а|ов)?|минут(?:у|ы)?|секунд(?:у|ы)?|полчаса)",
        text,
    )
    if m:
        amount = _to_number(m.group(1) or "")
        unit = m.group(2)
        if "полчаса" in text and amount is None:
            amount = 0.5
            unit = "час"
        if amount is None:
            amount = 1
        if unit.startswith("час"):
            delta = timedelta(hours=amount)
        elif unit.startswith("секунд"):
            delta = timedelta(seconds=amount)
        else:
            delta = timedelta(minutes=amount)
        rest = (text[: m.start()] + " " + text[m.end():]).strip(" ,.")
        if rest:
            return datetime.now() + delta, rest

    m = re.search(r"\bв\s+(\d{1,2})[:.](\d{2})\b", text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour < 24 and 0 <= minute < 60:
            now = datetime.now()
            due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if due <= now:
                due += timedelta(days=1)
            rest = (text[: m.start()] + " " + text[m.end():]).strip(" ,.")
            if rest:
                return due, rest
    return None
