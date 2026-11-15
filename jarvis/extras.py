"""Дополнительные офлайн-команды: единицы, время в городах, пароли, настройки."""
from __future__ import annotations

import random
import re
import secrets
from datetime import datetime
from difflib import SequenceMatcher

from . import actions


def _norm(text: str) -> str:
    text = (text or "").lower().replace("ё", "е")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .,!?;:")


def _plural(number: float, one: str, few: str, many: str) -> str:
    number = abs(int(number))
    if number % 10 == 1 and number % 100 != 11:
        return one
    if 2 <= number % 10 <= 4 and not 12 <= number % 100 <= 14:
        return few
    return many


def _fmt_number(value: float) -> str:
    value = round(float(value), 4)
    if abs(value) >= 10_000:
        text = f"{value:.0f}"
        return f"{int(text):,}".replace(",", " ")
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


# ----------------------------------------------------------------------
# Единицы измерения
class _Unit:
    __slots__ = ("kind", "factor", "forms", "aliases")

    def __init__(self, kind: str, factor: float, forms: tuple[str, ...],
                 aliases: tuple[str, ...] = ()) -> None:
        self.kind = kind
        self.factor = factor
        self.forms = forms
        self.aliases = aliases


_UNITS: dict[str, _Unit] = {}


def _add_unit(
    key: str,
    kind: str,
    factor: float,
    forms: tuple[str, ...],
    *aliases: str,
) -> None:
    _UNITS[key] = _Unit(kind, factor, forms, aliases)


# Длина: база — метр.
_add_unit("mm", "length", 0.001,
          ("миллиметр", "миллиметра", "миллиметров", "миллиметра"),
          "миллиметры", "миллиметрах", "мм")
_add_unit("cm", "length", 0.01,
          ("сантиметр", "сантиметра", "сантиметров", "сантиметра"),
          "сантиметры", "сантиметрах", "см")
_add_unit("m", "length", 1.0,
          ("метр", "метра", "метров", "метра"),
          "метры", "метрах", "м")
_add_unit("km", "length", 1000.0,
          ("километр", "километра", "километров", "километра"),
          "километры", "километрах", "км")
_add_unit("inch", "length", 0.0254,
          ("дюйм", "дюйма", "дюймов", "дюйма"),
          "дюймы", "дюймах")
_add_unit("ft", "length", 0.3048,
          ("фут", "фута", "футов", "фута"),
          "футы", "футах")
_add_unit("yd", "length", 0.9144,
          ("ярд", "ярда", "ярдов", "ярда"),
          "ярды", "ярдах")
_add_unit("mi", "length", 1609.344,
          ("миля", "мили", "миль", "мили"),
          "милю", "милях", "милями")

# Масса: база — грамм.
_add_unit("mg", "mass", 0.001,
          ("миллиграмм", "миллиграмма", "миллиграммов", "миллиграмма"),
          "миллиграммы", "мг")
_add_unit("g", "mass", 1.0,
          ("грамм", "грамма", "граммов", "грамма"),
          "граммы", "граммах", "г")
_add_unit("kg", "mass", 1000.0,
          ("килограмм", "килограмма", "килограммов", "килограмма"),
          "килограммы", "килограммах", "кг")
_add_unit("t", "mass", 1_000_000.0,
          ("тонна", "тонны", "тонн", "тонны"),
          "тонну", "тоннах", "тоннами")
_add_unit("lb", "mass", 453.59237,
          ("фунт", "фунта", "фунтов", "фунта"),
          "фунты", "фунтах")
_add_unit("oz", "mass", 28.349523125,
          ("унция", "унции", "унций", "унции"),
          "унцию", "унциях")

# Объём: база — литр.
_add_unit("ml", "volume", 0.001,
          ("миллилитр", "миллилитра", "миллилитров", "миллилитра"),
          "миллилитры", "миллилитрах", "мл")
_add_unit("l", "volume", 1.0,
          ("литр", "литра", "литров", "литра"),
          "литры", "литрах", "л")
_add_unit("gal", "volume", 3.785411784,
          ("галлон", "галлона", "галлонов", "галлона"),
          "галлоны", "галлонах")
_add_unit("pint", "volume", 0.473176473,
          ("пинта", "пинты", "пинт", "пинты"),
          "пинту", "пинтах")

# Данные: база — байт.
_add_unit("byte", "data", 1.0,
          ("байт", "байта", "байт", "байта"),
          "байты", "байтах", "б")
_add_unit("kb", "data", 1024.0,
          ("килобайт", "килобайта", "килобайт", "килобайта"),
          "килобайты", "килобайтах", "кб", "kb")
_add_unit("mb", "data", 1024.0 ** 2,
          ("мегабайт", "мегабайта", "мегабайт", "мегабайта"),
          "мегабайты", "мегабайтах", "мб", "mb")
_add_unit("gb", "data", 1024.0 ** 3,
          ("гигабайт", "гигабайта", "гигабайт", "гигабайта"),
          "гигабайты", "гигабайтах", "гб", "gb")
_add_unit("tb", "data", 1024.0 ** 4,
          ("терабайт", "терабайта", "терабайт", "терабайта"),
          "терабайты", "терабайтах", "тб", "tb")

# Площадь: база — квадратный метр.
_add_unit("sqm", "area", 1.0,
          ("квадратный метр", "квадратных метра",
           "квадратных метров", "квадратного метра"),
          "квадратные метры", "квадратных метрах", "м2", "метр в квадрате")
_add_unit("hectare", "area", 10_000.0,
          ("гектар", "гектара", "гектаров", "гектара"),
          "гектары", "гектарах", "га")
_add_unit("acre", "area", 4046.8564224,
          ("акр", "акра", "акров", "акра"),
          "акры", "акрах")

# Температура: отдельные формулы.
_add_unit("c", "temperature", 1.0,
          ("градус Цельсия", "градуса Цельсия",
           "градусов Цельсия", "градуса Цельсия"),
          "цельсий", "цельсия", "цельсию", "цельсии",
          "градус цельсия", "градусов цельсия", "c", "ц")
_add_unit("f", "temperature", 1.0,
          ("градус Фаренгейта", "градуса Фаренгейта",
           "градусов Фаренгейта", "градуса Фаренгейта"),
          "фаренгейт", "фаренгейта", "фаренгейты", "фаренгейту",
          "градус фаренгейта", "градусов фаренгейта", "f")
_add_unit("k", "temperature", 1.0,
          ("кельвин", "кельвина", "кельвинов", "кельвина"),
          "кельвины", "кельвину", "k")

_UNIT_ALIASES: dict[str, str] = {}
for _key, _unit in _UNITS.items():
    for _alias in set(_unit.forms) | set(_unit.aliases):
        _UNIT_ALIASES[_norm(_alias)] = _key


def _unit_key(phrase: str) -> str | None:
    phrase = _norm(phrase)
    if not phrase:
        return None
    if phrase in _UNIT_ALIASES:
        return _UNIT_ALIASES[phrase]
    # «градусов цельсия», «градуса по цельсию».
    trimmed = re.sub(
        r"^(?:градус(?:а|ов|ы)?|по)\s+", "", phrase
    )
    if trimmed != phrase and trimmed in _UNIT_ALIASES:
        return _UNIT_ALIASES[trimmed]
    # Отбрасываем падежные окончания: «километрах», «галлонами».
    for cut in range(1, 4):
        stem = phrase[:-cut]
        if len(stem) >= 3 and stem in _UNIT_ALIASES:
            return _UNIT_ALIASES[stem]

    best_key = None
    best_score = 0.0
    for alias, key in _UNIT_ALIASES.items():
        if len(alias) < 4:
            continue
        score = SequenceMatcher(None, phrase, alias).ratio()
        if score > best_score:
            best_score = score
            best_key = key
    return best_key if best_score >= 0.86 else None


def _split_value(text: str) -> tuple[float, str] | None:
    match = re.search(r"(?<![\w])(-?\d+(?:[.,]\d+)?)(?![\w])", text)
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    rest = (text[: match.start()] + " " + text[match.end():]).strip()
    return value, rest


def _unit_label(key: str, value: float) -> str:
    unit = _UNITS[key]
    if not float(value).is_integer():
        return unit.forms[3]
    return _plural(value, unit.forms[0], unit.forms[1], unit.forms[2])


def _convert_temperature(value: float, source: str, target: str) -> float:
    if source == "c":
        celsius = value
    elif source == "f":
        celsius = (value - 32.0) * 5.0 / 9.0
    else:
        celsius = value - 273.15
    if target == "c":
        return celsius
    if target == "f":
        return celsius * 9.0 / 5.0 + 32.0
    return celsius + 273.15


def convert_units(text: str) -> str | None:
    """Переводит единицы: «10 километров в мили», «сколько литров в 3 галлонах»."""
    text = _norm(text)
    if not text:
        return None
    text = re.sub(
        r"^(?:переведи|перевести|сконвертируй|конвертируй|конвертировать|"
        r"пересчитай|сколько\s+будет|сколько\s+это)\s+",
        "",
        text,
    )
    if not text:
        return None

    if text.startswith("сколько "):
        body = text[len("сколько "):]
        match = re.match(r"^(.+?)\s+в\s+(.+)$", body)
        if not match:
            return None
        target_phrase, left = match.group(1), match.group(2)
    else:
        match = re.match(r"^(.+?)\s+(?:в|во)\s+(.+)$", text)
        if not match:
            return None
        left, target_phrase = match.group(1), match.group(2)

    split = _split_value(left)
    if not split:
        return None
    value, source_phrase = split
    source_key = _unit_key(source_phrase)
    target_key = _unit_key(target_phrase)
    if source_key is None or target_key is None:
        return None

    source = _UNITS[source_key]
    target = _UNITS[target_key]
    if source.kind != target.kind:
        return (
            f"Нельзя перевести {_unit_label(source_key, value)} "
            f"в {_unit_label(target_key, value)}, сэр."
        )

    if source.kind == "temperature":
        result = _convert_temperature(value, source_key, target_key)
        source_label = _unit_label(source_key, value)
        target_label = _unit_label(target_key, result)
        return (
            f"{_fmt_number(value)} {source_label} — это "
            f"{_fmt_number(result)} {target_label}."
        )

    result = value * source.factor / target.factor
    source_label = _unit_label(source_key, value)
    target_label = _unit_label(target_key, result)
    return (
        f"{_fmt_number(value)} {source_label} — это "
        f"{_fmt_number(result)} {target_label}."
    )


# ----------------------------------------------------------------------
# Время в других городах
CITY_ZONES = {
    "лондон": "GMT Standard Time",
    "париж": "Romance Standard Time",
    "берлин": "W. Europe Standard Time",
    "рим": "W. Europe Standard Time",
    "мадрид": "Romance Standard Time",
    "амстердам": "W. Europe Standard Time",
    "прага": "Central Europe Standard Time",
    "варшава": "Central European Standard Time",
    "афины": "GTB Standard Time",
    "хельсинки": "FLE Standard Time",
    "стокгольм": "W. Europe Standard Time",
    "осло": "W. Europe Standard Time",
    "копенгаген": "W. Europe Standard Time",
    "цюрих": "W. Europe Standard Time",
    "вена": "W. Europe Standard Time",
    "брюссель": "Romance Standard Time",
    "лиссабон": "GMT Standard Time",
    "дублин": "GMT Standard Time",
    "рейкьявик": "UTC",
    "москва": "Russian Standard Time",
    "казань": "Russian Standard Time",
    "санкт-петербург": "Russian Standard Time",
    "петербург": "Russian Standard Time",
    "питер": "Russian Standard Time",
    "калининград": "Kaliningrad Standard Time",
    "самара": "Russia Time Zone 3",
    "екатеринбург": "Ekaterinburg Standard Time",
    "омск": "Omsk Standard Time",
    "новосибирск": "N. Central Asia Standard Time",
    "красноярск": "North Asia Standard Time",
    "иркутск": "North Asia East Standard Time",
    "якутск": "Yakutsk Standard Time",
    "владивосток": "Vladivostok Standard Time",
    "магадан": "Magadan Standard Time",
    "камчатка": "Kamchatka Standard Time",
    "петропавловск-камчатский": "Kamchatka Standard Time",
    "киев": "FLE Standard Time",
    "минск": "Belarus Standard Time",
    "алматы": "Central Asia Standard Time",
    "тбилиси": "Georgian Standard Time",
    "ереван": "Caucasus Standard Time",
    "баку": "Azerbaijan Standard Time",
    "ташкент": "West Asia Standard Time",
    "бишкек": "Central Asia Standard Time",
    "душанбе": "West Asia Standard Time",
    "ашхабад": "West Asia Standard Time",
    "нью-йорк": "Eastern Standard Time",
    "вашингтон": "Eastern Standard Time",
    "бостон": "Eastern Standard Time",
    "майами": "Eastern Standard Time",
    "чикаго": "Central Standard Time",
    "даллас": "Central Standard Time",
    "хьюстон": "Central Standard Time",
    "денвер": "Mountain Standard Time",
    "финикс": "US Mountain Standard Time",
    "лос-анджелес": "Pacific Standard Time",
    "сан-франциско": "Pacific Standard Time",
    "сиэтл": "Pacific Standard Time",
    "ванкувер": "Pacific Standard Time",
    "торонто": "Eastern Standard Time",
    "мехико": "Central Standard Time (Mexico)",
    "гавана": "Cuba Standard Time",
    "сан-паулу": "E. South America Standard Time",
    "буэнос-айрес": "Argentina Standard Time",
    "сантьяго": "Pacific SA Standard Time",
    "лима": "SA Pacific Standard Time",
    "богота": "SA Pacific Standard Time",
    "каракас": "Venezuela Standard Time",
    "токио": "Tokyo Standard Time",
    "пекин": "China Standard Time",
    "шанхай": "China Standard Time",
    "гонконг": "China Standard Time",
    "сеул": "Korea Standard Time",
    "сингапур": "Singapore Standard Time",
    "бангкок": "SE Asia Standard Time",
    "джакарта": "SE Asia Standard Time",
    "манила": "Singapore Standard Time",
    "дели": "India Standard Time",
    "нью-дели": "India Standard Time",
    "мумбаи": "India Standard Time",
    "дубай": "Arabian Standard Time",
    "стамбул": "Turkey Standard Time",
    "тель-авив": "Israel Standard Time",
    "каир": "Egypt Standard Time",
    "йоханнесбург": "South Africa Standard Time",
    "найроби": "E. Africa Standard Time",
    "лагос": "W. Central Africa Standard Time",
    "касабланка": "Morocco Standard Time",
    "сидней": "AUS Eastern Standard Time",
    "мельбурн": "AUS Eastern Standard Time",
    "бризбен": "E. Australia Standard Time",
    "перт": "W. Australia Standard Time",
    "окленд": "New Zealand Standard Time",
}


def _find_city(query: str) -> str | None:
    query = _norm(query)
    query = re.sub(r"\b(?:сейчас|пожалуйста|местное|местного|время)\b", " ", query)
    query = re.sub(r"\s+", " ", query).strip()
    if not query:
        return None
    if query in CITY_ZONES:
        return query
    best = None
    best_score = 0.0
    for city in CITY_ZONES:
        score = SequenceMatcher(None, query, city).ratio()
        if score > best_score:
            best_score = score
            best = city
    if best is not None and best_score >= 0.78:
        return best
    return None


def _city_display(city: str) -> str:
    return "-".join(part.capitalize() for part in city.split("-"))


def _fmt_clock(hour: int, minute: int) -> str:
    return (
        f"{hour} {_plural(hour, 'час', 'часа', 'часов')} "
        f"{minute:02d} {_plural(minute, 'минута', 'минуты', 'минут')}"
    )


def city_time(text: str) -> str | None:
    """«Который час в Лондоне», «сколько времени в Токио»."""
    match = re.match(
        r"^(?:котор\w+\s+(?:сейчас\s+)?час|сколько\s+(?:сейчас\s+)?времени|"
        r"во\s+сколько|время|сейчас)\s+"
        r"(?:сейчас\s+)?в\s+(.+)$",
        _norm(text),
    )
    if not match:
        return None
    raw_city = match.group(1)
    city = _find_city(raw_city)
    if city is None:
        return f"Не знаю часовой пояс «{raw_city.strip()}», сэр."
    data = actions.time_in_timezone(CITY_ZONES[city])
    if data is None:
        return f"Не удалось узнать время в городе {_city_display(city)}, сэр."
    hour, minute, city_date = data
    local_date = datetime.now().date()
    clock = _fmt_clock(hour, minute)
    display = _city_display(city)
    if city_date > local_date:
        return f"В городе {display} уже завтра, {clock}."
    if city_date < local_date:
        return f"В городе {display} ещё вчера, {clock}."
    return f"В городе {display} сейчас {clock}."


# ----------------------------------------------------------------------
# Пароли и случайный выбор
def generate_password(text: str) -> str | None:
    """«Сгенерируй пароль на 20 символов» -> строка пароля."""
    normalized = _norm(text)
    if "парол" not in normalized and "пин" not in normalized:
        return None
    if "пин" in normalized or "pin" in normalized:
        length = _password_length(normalized, 4)
        length = max(4, min(8, length))
        return "".join(secrets.choice("0123456789") for _ in range(length))

    length = _password_length(normalized, 16)
    length = max(8, min(128, length))
    if "без символ" in normalized or "только буквы" in normalized:
        alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        return "".join(secrets.choice(alphabet) for _ in range(length))

    groups = [
        "abcdefghijkmnopqrstuvwxyz",
        "ABCDEFGHJKLMNPQRSTUVWXYZ",
        "23456789",
        "!@#$%^&*()-_=+",
    ]
    chars = [secrets.choice(group) for group in groups]
    chars.extend(
        secrets.choice("".join(groups)) for _ in range(length - len(chars))
    )
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def _password_length(text: str, default: int) -> int:
    match = re.search(
        r"(?:на|из|длиной|длина)?\s*(\d{1,3})\s*(?:символ\w*|знак\w*)?",
        text,
    )
    if not match:
        return default
    try:
        return int(match.group(1))
    except ValueError:
        return default


def random_choice(text: str) -> str | None:
    """«Выбери пиццу или суши» -> случайный вариант."""
    match = re.match(
        r"^(?:выбери|выбрать|что\s+выбрать|случайно\s+выбери)\s+"
        r"(?:из\s+|между\s+)?(.+)$",
        _norm(text),
    )
    if not match:
        return None
    body = match.group(1)
    parts = re.split(r"\s+(?:или|либо)\s+", body)
    parts = [part.strip(" ,.") for part in parts if part.strip(" ,.")]
    if len(parts) < 2:
        if len(parts) == 1:
            return "Тут не из чего выбирать, сэр."
        return None
    return f"Я выбираю «{random.choice(parts)}», сэр."


# ----------------------------------------------------------------------
# Настройки Windows
_SETTINGS_TOPICS = [
    (("bluetooth", "блютуз", "блютус", "зуб"), "Bluetooth", "ms-settings:bluetooth"),
    (("вайфай", "wi-fi", "wifi", "wi fi"), "Wi-Fi", "ms-settings:network-wifi"),
    (("сеть", "сети", "интернет"), "сети", "ms-settings:network"),
    (("звук", "звука", "аудио", "динамик"), "звука", "ms-settings:sound"),
    (("дисплей", "экран", "монитор", "яркость"), "дисплея", "ms-settings:display"),
    (("уведомлен",), "уведомлений", "ms-settings:notifications"),
    (("принтер", "печат"), "принтеров", "ms-settings:printers"),
    (("обновлен", "windows update", "апдейт"), "обновления Windows",
     "ms-settings:windowsupdate"),
    (("приложен", "программ"), "приложений", "ms-settings:appsfeatures"),
    (("питани", "энергосбереж", "спящ"), "питания", "ms-settings:powersleep"),
    (("мышь", "тачпад"), "мыши и тачпада", "ms-settings:mousetouchpad"),
    (("клавиатур",), "клавиатуры", "ms-settings:keyboard"),
    (("дата", "время", "часы"), "даты и времени", "ms-settings:dateandtime"),
    (("язык", "раскладк", "регион"), "языка", "ms-settings:regionlanguage"),
    (("конфиденциальн", "приватн"), "конфиденциальности", "ms-settings:privacy"),
    (("камер",), "камеры", "ms-settings:privacy-webcam"),
    (("микрофон",), "микрофона", "ms-settings:privacy-microphone"),
    (("аккаунт", "учетн", "учётн"), "учётных записей", "ms-settings:accounts"),
    (("персонализац", "обои", "тема", "темн"), "персонализации",
     "ms-settings:personalization"),
    (("игр",), "игр", "ms-settings:gaming"),
    (("доступност", "специальн"), "специальных возможностей",
     "ms-settings:easeofaccess"),
    (("хранилищ", "память", "диск"), "хранилища", "ms-settings:storagesense"),
]


def windows_settings(text: str) -> tuple[str, str] | None:
    """Возвращает (название, ms-settings-URI) для «открой настройки ...»."""
    match = re.match(
        r"^(?:открой|открыть|покажи|запусти|перейди)\s+"
        r"(?:в\s+)?(?:настройки|параметры)(?:\s+(.+))?$",
        _norm(text),
    )
    if not match:
        return None
    topic = (match.group(1) or "").strip()
    if not topic:
        return ("Windows", "ms-settings:")
    for keys, label, uri in _SETTINGS_TOPICS:
        if any(key in topic for key in keys):
            return (label, uri)
    return ("Windows", "ms-settings:")
