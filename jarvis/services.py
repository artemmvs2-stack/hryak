"""Внешние сервисы: погода, курс валют, новости, поиск."""
from __future__ import annotations

import os
import re
import subprocess
import urllib.parse
import xml.etree.ElementTree as ET

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Jarvis/1.0"}

WEATHER_RU = {
    113: "ясно", 116: "переменная облачность", 119: "облачно", 122: "пасмурно",
    143: "дымка", 176: "местами дождь", 179: "местами снег", 182: "местами мокрый снег",
    185: "местами слабая изморозь", 200: "гроза", 227: "метель", 230: "сильная метель",
    248: "туман", 260: "ледяной туман", 263: "слабая морось", 266: "морось",
    281: "ледяная морось", 284: "сильная ледяная морось", 293: "местами слабый дождь",
    296: "слабый дождь", 299: "местами умеренный дождь", 302: "умеренный дождь",
    305: "местами сильный дождь", 308: "сильный дождь", 311: "слабый ледяной дождь",
    314: "умеренный ледяной дождь", 317: "слабый мокрый снег", 320: "мокрый снег",
    323: "местами слабый снег", 326: "слабый снег", 329: "местами умеренный снег",
    332: "умеренный снег", 335: "местами сильный снег", 338: "сильный снег",
    350: "ледяная крупа", 353: "слабый ливень", 356: "сильный ливень",
    359: "проливной дождь", 362: "слабый ливень с мокрым снегом",
    365: "сильный ливень с мокрым снегом", 368: "слабый снегопад",
    371: "сильный снегопад", 374: "слабая ледяная крупа", 377: "сильная ледяная крупа",
    386: "слабый дождь с грозой", 389: "сильный дождь с грозой",
    392: "слабый снег с грозой", 395: "сильный снег с грозой",
}


def _plural(number: int, one: str, few: str, many: str) -> str:
    number = abs(int(number))
    if number % 10 == 1 and number % 100 != 11:
        return one
    if 2 <= number % 10 <= 4 and not 12 <= number % 100 <= 14:
        return few
    return many


def _title_city(city: str) -> str:
    parts = []
    for chunk in city.split():
        parts.append("-".join(piece.capitalize() for piece in chunk.split("-")))
    return " ".join(parts)


# ----------------------------------------------------------------------
def weather(city: str, log) -> str | None:
    try:
        url = f"https://wttr.in/{urllib.parse.quote(city)}?format=j1&lang=ru"
        data = requests.get(url, timeout=12, headers=HEADERS).json()
        current = data["current_condition"][0]
        temp = int(current["temp_C"])
        feels = int(current["FeelsLikeC"])
        code = int(current.get("weatherCode", 113))
        desc = WEATHER_RU.get(code, "без осадков")
        humidity = int(current.get("humidity", 0))
        wind = int(float(current.get("windspeedKmph", 0)))
        return (
            f"В городе {_title_city(city)} сейчас {desc}, {temp} "
            f"{_plural(temp, 'градус', 'градуса', 'градусов')}, "
            f"ощущается как {feels}. "
            f"Влажность {humidity} {_plural(humidity, 'процент', 'процента', 'процентов')}, "
            f"ветер {wind} {_plural(wind, 'километр', 'километра', 'километров')} в час."
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Погода недоступна: %s", exc)
        return None


def weather_forecast(city: str, log=None) -> str | None:
    """Прогноз погоды на завтра."""
    try:
        url = f"https://wttr.in/{urllib.parse.quote(city)}?format=j1&lang=ru"
        data = requests.get(url, timeout=12, headers=HEADERS).json()
        days = data.get("weather") or []
        if len(days) < 2:
            return None
        item = days[1]
        low = int(item["mintempC"])
        high = int(item["maxtempC"])
        hourly = item.get("hourly") or []
        code = 113
        if hourly:
            code = int(hourly[len(hourly) // 2].get("weatherCode", 113))
        desc = WEATHER_RU.get(code, "без осадков")
        return (
            f"Завтра в городе {_title_city(city)} ожидается {desc}, "
            f"от {low} до {high} градусов."
        )
    except Exception as exc:  # noqa: BLE001
        if log:
            log.warning("Прогноз погоды недоступен: %s", exc)
        return None


def currency(code: str = "USD", log=None) -> str | None:
    try:
        data = requests.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=12).json()
        valute = data.get("Valute", {})
        item = valute.get(code)
        if not item:
            return None
        name = {"USD": "доллара", "EUR": "евро", "CNY": "юаня", "GBP": "фунта"}.get(code, code)
        value = round(item["Value"], 2)
        prev = item.get("Previous", value)
        trend = "вырос" if value > prev else ("упал" if value < prev else "не изменился")
        return f"Курс {name} сегодня {value} рублей, за день {trend}."
    except Exception as exc:  # noqa: BLE001
        if log:
            log.warning("Курс валют недоступен: %s", exc)
        return None


def news(limit: int = 5, log=None) -> list[str] | None:
    feeds = [
        "https://lenta.ru/rss/news",
        "https://www.interfax.ru/rss.asp",
    ]
    for feed in feeds:
        try:
            rss = requests.get(feed, timeout=12, headers=HEADERS).content
            root = ET.fromstring(rss)
            items = []
            for item in root.iter("item"):
                title = item.findtext("title")
                if title:
                    title = re.sub(r"<[^>]+>", "", title).strip()
                    items.append(title)
                if len(items) >= limit:
                    break
            if items:
                return items
        except Exception as exc:  # noqa: BLE001
            if log:
                log.warning("Новости (%s) недоступны: %s", feed, exc)
    return None


# ----------------------------------------------------------------------
SEARCH_ENGINES = {
    "yandex": "https://ya.ru/search/?text={query}",
    "google": "https://www.google.com/search?q={query}",
    "bing": "https://www.bing.com/search?q={query}",
    "duckduckgo": "https://duckduckgo.com/?q={query}",
}

IMAGE_ENGINES = {
    "yandex": "https://yandex.ru/images/search?text={query}",
    "google": "https://www.google.com/search?tbm=isch&q={query}",
    "bing": "https://www.bing.com/images/search?q={query}",
    "duckduckgo": "https://duckduckgo.com/?q={query}&iax=images&ia=images",
}

VIDEO_ENGINES = {
    "youtube": "https://www.youtube.com/results?search_query={query}",
    "yandex": "https://yandex.ru/video/search?text={query}",
}


def _build_url(templates: dict, query: str, engine: str | None) -> str:
    key = (engine or "yandex").lower()
    template = templates.get(key, templates["yandex"])
    return template.format(query=urllib.parse.quote_plus(query.strip()))


def search_url(query: str, engine: str | None = None) -> str:
    return _build_url(SEARCH_ENGINES, query, engine)


def image_search_url(query: str, engine: str | None = None) -> str:
    return _build_url(IMAGE_ENGINES, query, engine)


def video_search_url(query: str, engine: str | None = None) -> str:
    return _build_url(VIDEO_ENGINES, query, engine or "youtube")


def normalize_url(text: str) -> str | None:
    """Превращает «example.com/page» в https://example.com/page."""
    text = (text or "").strip().strip("<>\"'")
    if not text:
        return None
    if re.match(r"^https?://", text, re.IGNORECASE):
        return text
    if re.match(
        r"^(?:[a-zа-я0-9](?:[a-zа-я0-9-]*[a-zа-я0-9])?\.)+[a-zа-я]{2,}"
        r"(?:/\S*)?$",
        text,
        re.IGNORECASE,
    ):
        return "https://" + text
    return None


def open_url(url: str, browser: str | None = None) -> bool:
    """Открывает URL в выбранном или стандартном браузере."""
    if not url:
        return False
    try:
        from . import actions  # noqa: PLC0415

        return actions.open_url_in_browser(url, browser) is not None
    except Exception:
        try:
            os.startfile(url)  # noqa: S606
            return True
        except Exception:
            return False


def web_search(query: str, engine: str | None = None, browser: str | None = None) -> bool:
    query = (query or "").strip()
    if not query:
        return False
    return open_url(search_url(query, engine), browser)


def image_search(query: str, engine: str | None = None, browser: str | None = None) -> bool:
    query = (query or "").strip()
    if not query:
        return False
    return open_url(image_search_url(query, engine), browser)


def video_search(query: str, browser: str | None = None) -> bool:
    query = (query or "").strip()
    if not query:
        return False
    return open_url(video_search_url(query, "youtube"), browser)


def youtube_play(query: str, browser: str | None = None) -> bool:
    query = (query or "").strip()
    if not query:
        return False
    url = "https://music.youtube.com/search?q=" + urllib.parse.quote_plus(query)
    return open_url(url, browser)


def youtube_first(query: str, log=None) -> tuple[str, str] | None:
    """Ищет первое видео на YouTube и возвращает (url, название)."""
    query = (query or "").strip()
    if not query:
        return None
    try:
        import yt_dlp  # noqa: PLC0415

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": True,
            "noplaylist": True,
            "playlist_items": "1",
            "socket_timeout": 8,
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=False)
        entries = (info or {}).get("entries") or []
        if not entries:
            return None
        entry = entries[0]
        url = str(entry.get("url") or "")
        video_id = entry.get("id")
        if not url.startswith("http") and video_id:
            url = f"https://www.youtube.com/watch?v={video_id}"
        if not url.startswith("http"):
            return None
        title = str(entry.get("title") or query)
        return url, title
    except Exception as exc:  # noqa: BLE001
        if log:
            log.warning("YouTube: не удалось найти видео: %s", exc)
        return None


def copy_link(url: str) -> bool:
    try:
        from . import actions  # noqa: PLC0415

        return actions.copy_text(url)
    except Exception:
        return False


def run_detached(command: str) -> None:
    subprocess.Popen(  # noqa: S602
        command, shell=True, creationflags=0x08000000
    )
