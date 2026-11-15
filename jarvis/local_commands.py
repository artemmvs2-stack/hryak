"""Дополнительные локальные команды: окна, буфер, папки, система, мелочи."""
from __future__ import annotations

import random
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import actions, extras, word
from .calc import evaluate, format_result
from .memory import parse_reminder
from .text_style import format_dictation, match_raw_tail

JOKES = [
    "Программист ставит на ночь два стакана: один с водой, если захочет пить, "
    "второй пустой, если не захочет.",
    "Я не ленивый, я в энергосберегающем режиме, сэр.",
    "Оптимист верит, что стакан наполовину полон. Пессимист — что он всё равно "
    "протечёт. А инженер думает, почему стакан в два раза больше, чем нужно.",
    "На работе я как антивирус: всё проверяю, всех подозреваю, но без меня "
    "почему-то становится хуже.",
    "Искусственный интеллект не заменит человека. Кто-то же должен перезагружать "
    "компьютер, когда всё зависло.",
    "Мой любимый вид спорта — перетаскивание файлов на рабочий стол.",
    "Я бы рассказал шутку про Wi-Fi, но боюсь, вы не подключитесь.",
    "Совещание — это когда люди собираются вместе, чтобы решить, что им нужно "
    "было собраться вместе.",
]

FACTS = [
    "Мёд не портится тысячелетиями: археологи находили съедобный мёд в гробницах "
    "Древнего Египта.",
    "Осьминоги имеют три сердца и голубую кровь.",
    "На Венере день длиннее года: планета вращается вокруг своей оси медленнее, "
    "чем вокруг Солнца.",
    "Бананы — это ягоды, а малина — нет, с ботанической точки зрения.",
    "Первая компьютерная мышь была деревянной.",
    "Космос пахнет жареным мясом и горячим металлом — так говорят астронавты.",
    "У улитки около четырёх тысяч зубов.",
    "Свет от Солнца до Земли идёт примерно восемь минут двадцать секунд.",
]

KNOWN_FOLDERS = set(actions.FOLDER_ALIASES) | set(actions.SHELL_FOLDERS)


def _ok(flag: bool, success: str, failure: str) -> str:
    return success if flag else failure


def _truncate(text: str, limit: int = 300) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + ". Текст длинный, сэр, я озвучил начало."


def _words_to_digits(text: str) -> str:
    words = {
        "ноль": 0, "один": 1, "одну": 1, "одна": 1, "одной": 1,
        "два": 2, "две": 2, "двух": 2, "три": 3, "трех": 3,
        "четыре": 4, "четырех": 4, "пять": 5, "пяти": 5,
        "шесть": 6, "шести": 6, "семь": 7, "семи": 7,
        "восемь": 8, "восьми": 8, "девять": 9, "девяти": 9,
        "десять": 10, "десяти": 10,
        "одиннадцать": 11, "одиннадцати": 11,
        "двенадцать": 12, "двенадцати": 12,
        "пятнадцать": 15, "пятнадцати": 15,
        "двадцать": 20, "двадцати": 20,
        "тридцать": 30, "тридцати": 30,
        "сорок": 40, "сорока": 40,
        "пятьдесят": 50, "пятидесяти": 50,
        "шестьдесят": 60, "шестидесяти": 60,
        "сто": 100, "ста": 100, "полтора": "1.5", "полторы": "1.5",
    }
    pattern = r"\b(" + "|".join(words) + r")\b"
    return re.sub(pattern, lambda match: str(words[match.group(1)]), text)


_LINK_ORDINALS = {
    "первую": 1, "первая": 1, "первый": 1, "первой": 1, "первого": 1,
    "вторую": 2, "вторая": 2, "второй": 2, "второго": 2,
    "третью": 3, "третья": 3, "третий": 3, "третьей": 3, "третьего": 3,
    "четвертую": 4, "четвертая": 4, "четвертый": 4, "четвертой": 4,
    "четвертого": 4,
    "пятую": 5, "пятая": 5, "пятый": 5, "пятой": 5, "пятого": 5,
    "шестую": 6, "шестая": 6, "шестой": 6, "шестого": 6,
    "седьмую": 7, "седьмая": 7, "седьмой": 7, "седьмого": 7,
    "восьмую": 8, "восьмая": 8, "восьмой": 8, "восьмого": 8,
    "девятую": 9, "девятая": 9, "девятый": 9, "девятой": 9,
    "девятого": 9,
    "десятую": 10, "десятая": 10, "десятый": 10, "десятой": 10,
}


def _link_number(value: str) -> int | None:
    """Номер ссылки из слова: «первую», «2», «номер три»."""
    word = re.sub(r"^номер\s+", "", (value or "").strip().lower()).strip()
    word = word.replace("ё", "е")
    if word.isdigit():
        number = int(word)
        return number if 1 <= number <= 30 else None
    if word in _LINK_ORDINALS:
        return _LINK_ORDINALS[word]
    digits = _words_to_digits(word)
    if digits.isdigit() and 1 <= int(digits) <= 30:
        return int(digits)
    return None


def _handle_browser_link(text: str) -> str | None:
    """Открывает ссылку по номеру на текущей странице браузера."""
    match = re.fullmatch(
        r"(?:открой|открыть|нажми|нажать|кликни|кликнуть|тыкни)\s+"
        r"(?:на\s+)?(?:(?:ссылку|ссылке)\s+(?:номер\s+)?(.+)|"
        r"(?:номер\s+)?(.+?)\s+ссылк[уае])",
        text,
    )
    if not match:
        return None
    number = _link_number(match.group(1) or match.group(2) or "")
    if number is None:
        return None
    name = actions.browser_open_link(number)
    if name:
        return f"Открыл ссылку «{_truncate(name)}», сэр."
    if not actions.browser_available():
        return "Не вижу открытого браузера, сэр."
    return "Не нашёл такую ссылку на странице, сэр."


def _handle_browser_page(text: str) -> str | None:
    answer = _handle_browser_link(text)
    if answer is not None:
        return answer
    if re.fullmatch(
        r"(?:обнови|обновить|перезагрузи|перезагрузить)\s+"
        r"(?:страницу|вкладку|браузер)",
        text,
    ):
        return _ok(
            actions.browser_refresh(),
            "Обновил страницу, сэр.",
            "Не вижу открытого браузера, сэр.",
        )
    if re.fullmatch(
        r"(?:вернись|перейди|перейти)\s+назад|"
        r"назад\s+по\s+странице|предыдущая\s+страница",
        text,
    ):
        return _ok(
            actions.browser_back(),
            "Вернулся назад, сэр.",
            "Не вижу открытого браузера, сэр.",
        )
    if re.fullmatch(
        r"(?:перейди|перейти)\s+впер[её]д|"
        r"впер[её]д\s+по\s+странице|следующая\s+страница",
        text,
    ):
        return _ok(
            actions.browser_forward(),
            "Перешёл вперёд, сэр.",
            "Не вижу открытого браузера, сэр.",
        )
    if re.fullmatch(
        r"(?:увеличь|приблизь|увеличить)\s+(?:масштаб|страницу)",
        text,
    ):
        return _ok(
            actions.browser_zoom_in(),
            "Увеличил масштаб, сэр.",
            "Не вижу открытого браузера, сэр.",
        )
    if re.fullmatch(
        r"(?:уменьши|отдали|уменьшить)\s+(?:масштаб|страницу)",
        text,
    ):
        return _ok(
            actions.browser_zoom_out(),
            "Уменьшил масштаб, сэр.",
            "Не вижу открытого браузера, сэр.",
        )
    if re.fullmatch(
        r"(?:сбрось|верни|сбросить)\s+масштаб|обычный\s+масштаб",
        text,
    ):
        return _ok(
            actions.browser_zoom_reset(),
            "Вернул обычный масштаб, сэр.",
            "Не вижу открытого браузера, сэр.",
        )
    if re.fullmatch(
        r"(?:яндекс[\s-]*браузер|браузер|хром|опера|edge)\s+"
        r"(?:во\s+)?(?:весь|полный)\s+экран",
        text,
    ):
        return _ok(
            actions.browser_maximize(),
            "Развернул браузер на весь экран, сэр.",
            "Не вижу открытого браузера, сэр.",
        )
    if re.match(
        r"^(?:(?:включи|открой|разверни|сделай)\s+)?(?:видео|ролик)\s+"
        r"(?:на\s+)?(?:полный|весь)\s+экран",
        text,
    ):
        return _ok(
            actions.browser_video_fullscreen(),
            "Включил видео на весь экран, сэр.",
            "Не вижу видео на странице, сэр.",
        )
    if re.fullmatch(
        r"(?:(?:сделай|включи|открой|разверни|переведи)\s+)?"
        r"(?:браузер\s+)?(?:на\s+)?(?:полный|весь)\s+экран|"
        r"полный\s+экран",
        text,
    ):
        return _ok(
            actions.browser_fullscreen(),
            "Включил полный экран, сэр.",
            "Не вижу открытого браузера, сэр.",
        )
    if re.fullmatch(
        r"(?:выйди|выйти|выключи|убери)\s+из\s+полного\s+экрана|"
        r"обычный\s+экран",
        text,
    ):
        return _ok(
            actions.browser_exit_fullscreen(),
            "Вышел из полного экрана, сэр.",
            "Не вижу открытого браузера, сэр.",
        )
    if re.fullmatch(
        r"(?:открой|включи|открыть)\s+(?:режим\s+)?инкогнито|"
        r"приватное\s+окно",
        text,
    ):
        return _ok(
            actions.browser_private(),
            "Открыл приватное окно, сэр.",
            "Не вижу открытого браузера, сэр.",
        )
    if re.fullmatch(
        r"(?:открой|создай|открыть)\s+новое\s+окно(?:\s+браузера)?",
        text,
    ):
        return _ok(
            actions.browser_new_window(),
            "Открыл новое окно браузера, сэр.",
            "Не вижу открытого браузера, сэр.",
        )
    match = re.fullmatch(r"(?:найди|поищи|найти)\s+на\s+странице\s+(.+)", text)
    if match:
        return _ok(
            actions.browser_find(match.group(1)),
            f"Ищу на странице «{match.group(1)}», сэр.",
            "Не удалось выполнить поиск по странице, сэр.",
        )
    match = re.fullmatch(
        r"(?:прокрути|пролистай|прокрутить)\s+(вниз|вверх|ниже|выше)",
        text,
    )
    if match:
        return _ok(
            actions.browser_scroll(match.group(1)),
            "Прокрутил страницу, сэр.",
            "Не вижу открытого браузера, сэр.",
        )
    if re.fullmatch(
        r"(?:в|перейди\s+в|перейти\s+в)\s+начало\s+страницы",
        text,
    ):
        return _ok(
            actions.browser_scroll_top(),
            "Перешёл в начало страницы, сэр.",
            "Не вижу открытого браузера, сэр.",
        )
    if re.fullmatch(
        r"(?:в|перейди\s+в|перейти\s+в)\s+конец\s+страницы",
        text,
    ):
        return _ok(
            actions.browser_scroll_bottom(),
            "Перешёл в конец страницы, сэр.",
            "Не вижу открытого браузера, сэр.",
        )
    match = re.fullmatch(
        r"перемотай\s+(впер[её]д|назад)"
        r"(?:\s+на\s+(\d{1,3})\s+секунд(?:ы|у)?)?",
        text,
    )
    if match:
        seconds = int(match.group(2) or 10)
        if match.group(1) == "назад":
            seconds = -seconds
        return _ok(
            actions.browser_seek(seconds),
            f"Перемотал на {abs(seconds)} секунд, сэр.",
            "Не вижу видео на YouTube, сэр.",
        )
    if re.fullmatch(
        r"(?:пауза|паузу)\s+видео|(?:останови|остановить)\s+видео|"
        r"(?:продолжи|возобнови|продолжить)\s+видео",
        text,
    ):
        if actions.browser_video_toggle():
            return "Переключил видео, сэр."
        actions.press_key(actions.VK["play_pause"])
        return "Переключил воспроизведение, сэр."
    if re.fullmatch(r"следующее\s+видео", text):
        return _ok(
            actions.browser_video_next(),
            "Включил следующее видео, сэр.",
            "Не вижу открытого браузера, сэр.",
        )
    if re.fullmatch(r"предыдущее\s+видео", text):
        return _ok(
            actions.browser_video_previous(),
            "Включил предыдущее видео, сэр.",
            "Не вижу открытого браузера, сэр.",
        )
    return None


def _handle_windows(text: str) -> str | None:
    if re.fullmatch(
        r"(?:сверни|свернуть)\s+все\s+окна|покажи\s+рабочий\s+стол",
        text,
    ):
        actions.show_desktop()
        return "Свернул все окна, сэр."
    if re.fullmatch(
        r"(?:переключи|смени|переключить)\s+окно|"
        r"(?:следующее|другое)\s+окно",
        text,
    ):
        actions.switch_window()
        return "Переключил окно, сэр."
    if re.fullmatch(
        r"(?:закрой|закрыть)\s+(?:это\s+|активное\s+|текущее\s+)?окно",
        text,
    ):
        actions.close_active_window()
        return "Закрыл активное окно, сэр."
    if re.fullmatch(
        r"(?:разверни|развернуть|максимизируй)\s+"
        r"(?:это\s+|активное\s+|текущее\s+)?окно",
        text,
    ):
        actions.maximize_active_window()
        return "Развернул окно, сэр."
    if re.fullmatch(
        r"(?:сверни|свернуть|минимизируй)\s+"
        r"(?:это\s+|активное\s+|текущее\s+)?окно",
        text,
    ):
        actions.minimize_active_window()
        return "Свернул окно, сэр."
    match = re.fullmatch(
        r"(?:прикрепи|закрепи|прикрепить)\s+окно\s+(влево|вправо)", text
    )
    if match:
        if match.group(1) == "влево":
            actions.snap_window_left()
        else:
            actions.snap_window_right()
        return f"Прикрепил окно {match.group(1)}, сэр."
    if re.fullmatch(
        r"(?:какое|что)\s+(?:окно\s+)?(?:сейчас\s+)?активно|"
        r"активное\s+окно",
        text,
    ):
        info = actions.active_window()
        if not info:
            return "Не вижу активного окна, сэр."
        return f"Активно окно «{info['title']}»."
    if re.fullmatch(
        r"(?:какие|что)\s+окна\s+открыты|список\s+окон",
        text,
    ):
        titles = actions.list_windows(8)
        if not titles:
            return "Не вижу открытых окон, сэр."
        return "Открыты: " + "; ".join(titles) + "."
    match = re.fullmatch(
        r"(?:переключись|переключи|перейди)\s+(?:на|в)\s+окно\s+(.+)",
        text,
    )
    if match:
        title = actions.focus_window_by_title(match.group(1))
        if title:
            return f"Переключился на окно «{title}», сэр."
        return f"Не нашёл окно «{match.group(1)}», сэр."
    match = re.fullmatch(r"(?:закрой|закрыть)\s+окно\s+(.+)", text)
    if match:
        title = actions.close_window_by_title(match.group(1))
        if title:
            return f"Закрыл окно «{title}», сэр."
        return f"Не нашёл окно «{match.group(1)}», сэр."
    return None


def _handle_clipboard(text: str, raw: str = "") -> str | None:
    if re.fullmatch(
        r"(?:что|покажи)\s+(?:сейчас\s+)?в\s+буфере(?:\s+обмена)?|"
        r"что\s+скопировано",
        text,
    ):
        value = actions.get_clipboard_text()
        if value is None:
            return "Не удалось прочитать буфер обмена, сэр."
        if not value.strip():
            return "Буфер обмена пуст, сэр."
        return "В буфере: " + _truncate(value)
    if re.fullmatch(r"(?:очисти|очистить)\s+буфер(?:\s+обмена)?", text):
        return _ok(
            actions.copy_text(""),
            "Очистил буфер обмена, сэр.",
            "Не удалось очистить буфер, сэр.",
        )
    if re.fullmatch(r"(?:вставь|вставить)(?:\s+текст)?", text):
        return _ok(
            actions.send_hotkey("^v"),
            "Вставил, сэр.",
            "Не удалось вставить текст, сэр.",
        )
    match = re.fullmatch(
        r"(?:скопируй|скопировать)\s+(?!ссылк)(.+)", text
    )
    if match:
        return _ok(
            actions.copy_text(format_dictation(match.group(1), raw)),
            "Скопировал, сэр.",
            "Не удалось скопировать текст, сэр.",
        )
    match = re.fullmatch(
        r"(?:напечатай|напечатать|набери|набрать|введи|ввести)\s+(.+)",
        text,
    )
    if match:
        return _ok(
            actions.type_text(format_dictation(match.group(1), raw)),
            "Напечатал, сэр.",
            "Не удалось напечатать текст, сэр.",
        )
    return None


def _handle_system(text: str) -> str | None:
    if re.fullmatch(
        r"(?:выключи|погаси|отключи|выключить)\s+(?:экран|монитор)", text
    ):
        return _ok(
            actions.monitor_off(),
            "Выключил экран, сэр.",
            "Не удалось выключить экран, сэр.",
        )
    if re.fullmatch(
        r"спящий\s+режим|режим\s+сна|усни|"
        r"переведи\s+(?:пк|компьютер)\s+в\s+сон",
        text,
    ):
        def _sleep() -> None:
            time.sleep(2.0)
            actions.sleep_pc()

        threading.Thread(target=_sleep, daemon=True).start()
        return "Перевожу компьютер в сон через две секунды, сэр."
    if re.fullmatch(
        r"(?:какой\s+(?:у\s+меня\s+)?ip|мой\s+ip|ip\s+адрес)", text
    ):
        ip = actions.local_ip()
        if ip:
            return f"Мой локальный IP: {ip}."
        return "Не удалось определить IP, сэр."
    if re.fullmatch(
        r"(?:проверь|проверить)\s+интернет|есть\s+ли\s+интернет|"
        r"интернет\s+работает",
        text,
    ):
        return (
            "Интернет работает, сэр."
            if actions.internet_available()
            else "Интернет недоступен, сэр."
        )
    if re.fullmatch(
        r"сколько\s+(?:свободного\s+)?места(?:\s+на\s+диске)?|"
        r"место\s+на\s+диске|свободно\s+на\s+диске",
        text,
    ):
        info = actions.disk_info()
        return (
            f"На диске {info['drive']} свободно {info['free']:.1f} гигабайт "
            f"из {info['total']:.1f}, занято {info['percent']} процентов."
        )
    if re.fullmatch(
        r"имя\s+компьютера|как\s+называется\s+компьютер", text
    ):
        return f"Компьютер называется {actions.system_details()['hostname']}."
    if re.fullmatch(
        r"(?:версия\s+windows|какая\s+(?:у\s+меня\s+)?windows|"
        r"какая\s+операционная\s+система)",
        text,
    ):
        return f"Установлена {actions.system_details()['os']}."
    if re.fullmatch(
        r"(?:какие\s+процессы\s+(?:жрут|едят|занимают)\s+память|"
        r"топ\s+процессов|что\s+жр[её]т\s+память)",
        text,
    ):
        items = actions.top_processes(4)
        if not items:
            return "Не удалось получить список процессов, сэр."
        return "Больше всего памяти занимают: " + ", ".join(
            f"{name} — {mb} мегабайт" for name, mb in items
        ) + "."
    match = re.fullmatch(
        r"яркость\s+(?:на\s+)?(\d{1,3})(?:\s+процент(?:ов|а)?)?", text
    )
    if match:
        value = max(0, min(100, int(match.group(1))))
        return _ok(
            actions.set_brightness(value),
            f"Яркость {value} процентов, сэр.",
            "Не удалось изменить яркость, сэр. Возможно, это стационарный компьютер.",
        )
    if re.fullmatch(r"яркость", text):
        return "На сколько процентов сделать яркость, сэр?"
    if re.fullmatch(
        r"ярче|сделай\s+ярче|увеличь\s+яркость|прибавь\s+яркость", text
    ):
        value = actions.change_brightness(10)
        if value is None:
            return "Не удалось изменить яркость, сэр. Возможно, это стационарный компьютер."
        return f"Сделал ярче: {value} процентов, сэр."
    if re.fullmatch(
        r"темнее|сделай\s+темнее|уменьши\s+яркость|убавь\s+яркость", text
    ):
        value = actions.change_brightness(-10)
        if value is None:
            return "Не удалось изменить яркость, сэр. Возможно, это стационарный компьютер."
        return f"Сделал темнее: {value} процентов, сэр."
    return None


def _handle_folders(text: str) -> str | None:
    if re.match(r"^(?:создай|создать|сделай)\s+папку\s+.+", text):
        body = re.sub(r"^(?:создай|создать|сделай)\s+папку\s+", "", text)
        parent = "desktop"
        for suffix, key in (
            (" на рабочем столе", "desktop"),
            (" в документах", "documents"),
            (" в загрузках", "downloads"),
            (" в домашней папке", "home"),
        ):
            if body.endswith(suffix):
                body = body[: -len(suffix)]
                parent = key
                break
        name = body.strip(" ,.")
        if not name:
            return "Как назвать папку, сэр?"
        result = actions.create_folder(name, parent)
        if result is None:
            return f"Не удалось создать папку «{name}», сэр."
        path, created = result
        if created:
            return f"Создал папку «{name}», сэр."
        return f"Папка «{name}» уже существует, сэр."
    if re.fullmatch(
        r"открой\s+последнюю\s+загрузку|"
        r"открой\s+последний\s+файл\s+из\s+загрузок",
        text,
    ):
        target = actions.open_latest_download()
        if target:
            return f"Открыл последнюю загрузку: {Path(target).name}."
        return "В загрузках нет файлов, сэр."
    if re.fullmatch(
        r"(?:какие|покажи)\s+последние\s+загрузки|"
        r"последние\s+загрузки",
        text,
    ):
        items = actions.latest_downloads(5)
        if not items:
            return "В загрузках нет файлов, сэр."
        return "Последние загрузки: " + "; ".join(
            Path(item).name for item in items
        ) + "."
    match = re.fullmatch(
        r"(?:открой|открыть|покажи|показать)\s+папку\s+(.+)", text
    )
    if match:
        name = match.group(1).strip()
        target = actions.open_folder(name)
        if target:
            return f"Открыл папку «{name}», сэр."
        return f"Не нашёл папку «{name}», сэр."
    match = re.fullmatch(
        r"(?:открой|открыть|покажи|показать)\s+(.+)", text
    )
    if match:
        name = re.sub(r"\s+", " ", match.group(1).strip())
        if name in KNOWN_FOLDERS:
            target = actions.open_folder(name)
            if target:
                return f"Открыл папку «{name}», сэр."
            return f"Не удалось открыть папку «{name}», сэр."
    return None


_FILE_FOLDER_HINTS = {
    "рабочем столе": "Desktop",
    "рабочий стол": "Desktop",
    "desktop": "Desktop",
    "документах": "Documents",
    "документы": "Documents",
    "documents": "Documents",
    "загрузках": "Downloads",
    "загрузки": "Downloads",
    "downloads": "Downloads",
    "картинках": "Pictures",
    "картинки": "Pictures",
    "pictures": "Pictures",
    "музыке": "Music",
    "музыка": "Music",
    "music": "Music",
    "видео": "Videos",
    "videos": "Videos",
}


def _word_phrase(value: str, raw: str) -> str:
    """Текст для Word без завершающей точки, которую добавила нормализация."""
    result = format_dictation(value, raw)
    if not result:
        return result
    # «Проверка.» внутри команды замены — это не конец предложения.
    if result.endswith((".", "!", "?")) and not raw.strip().endswith(
        (".", "!", "?")
    ):
        result = result.rstrip(".!?").strip()
    return result


def _raw_tail(value: str, raw: str) -> str:
    """Возвращает исходное написание хвоста команды, если оно распознано."""
    return match_raw_tail(value, raw) or value


def _handle_word(text: str, raw: str = "") -> str | None:
    """Работа с Microsoft Word: документы, текст, PDF, таблицы."""
    explicit = bool(re.search(r"\b(?:ворд\w*|word|docx|докс)\b", text))
    document = bool(re.search(r"\bдокумент\w*\b", text))
    document_action = document and bool(
        re.search(
            r"\b(?:создай|создать|сделай|сделать|сохрани|сохранить|прочитай|"
            r"прочти|добавь|допиши|вставь|закрой|замени|заменить|сколько|pdf|"
            r"открой|открыть|написано|напиши|запиши|напечатай)\b",
            text,
        )
    )
    structural = bool(
        re.match(
            r"^(?:добавь|вставь)\s+(?:заголовок|таблицу|разрыв\s+страницы)|"
            r"^(?:сохрани|сохранить|экспорт\w*|выгрузи)\b.*\bpdf\b|"
            r"^(?:новая|добавь)\s+страниц|"
            r"^(?:сколько|посчитай)\s+слов|^объ[её]м\s+документа|"
            r"^(?:какой|что)\s+(?:документ\s+)?открыт|"
            r"^(?:замени|заменить)\s+",
            text,
        )
    )
    if not (explicit or document_action or structural):
        return None
    if not word.available():
        return (
            "Microsoft Word не установлен, сэр. "
            "Поставьте Word или скажите «создай текстовый файл»."
        )

    if re.fullmatch(
        r"(?:создай|создать|сделай|сделать|новый|открой|открыть)\s+"
        r"(?:новый\s+)?(?:документ|файл)\s*(?:ворд\w*|word)?|"
        r"(?:создай|создать|сделай|сделать|открой|открыть)\s+"
        r"(?:вордовск\w*|word)\s+(?:документ|файл)|"
        r"(?:создай|открой)\s+(?:ворд\w*|word)",
        text,
    ):
        name = word.new_document()
        return f"Создал документ «{name}», сэр."

    match = re.fullmatch(
        r"(?:создай|создать|сделай|сделать)\s+"
        r"(?:документ|файл)\s+(?:ворд\w*|word)\s+(?:с\s+текстом\s+)?(.+)|"
        r"(?:создай|создать|сделай|сделать)\s+"
        r"(?:вордовск\w*|word)\s+(?:документ|файл)\s+"
        r"(?:с\s+текстом\s+)?(.+)",
        text,
    )
    if match:
        body = format_dictation(match.group(1) or match.group(2), raw)
        name = word.new_document(body)
        return f"Создал документ «{name}» с текстом, сэр."

    if re.fullmatch(
        r"(?:сколько|посчитай)\s+слов(?:\s+в\s+(?:документе|ворде|тексте))?|"
        r"объ[её]м\s+документа",
        text,
    ):
        count = word.word_count()
        if count is None:
            return "Не вижу открытого документа, сэр."
        return f"В документе {count} слов, сэр."

    if re.fullmatch(r"(?:какой|что)\s+(?:документ\s+)?открыт|"
                    r"какой\s+документ\s+(?:сейчас\s+)?активен", text):
        info = word.document_info()
        if info is None:
            return "Не вижу открытого документа, сэр."
        tail = ""
        if info.get("words") is not None:
            tail = f", слов: {info['words']}"
        if info.get("pages") is not None:
            tail += f", страниц: {info['pages']}"
        return f"Открыт документ «{info['name']}»{tail}."

    match = re.fullmatch(
        r"открой\s+(?:документ|файл)\s+(?:ворд\s+)?(.+)", text
    )
    if match:
        name = word.open_document(_raw_tail(match.group(1), raw).strip(" ,."))
        if name is None:
            return None  # пусть попробует обычный поиск файлов
        return f"Открыл документ «{name}», сэр."

    match = re.fullmatch(
        r"(?:прочитай|прочти|что\s+(?:написано\s+)?в)\s+"
        r"(?:документ|документе|ворде)(?:\s+(.+))?",
        text,
    )
    if match:
        body = word.read_document(
            _raw_tail(match.group(1), raw) if match.group(1) else ""
        )
        if body is None:
            return "Не вижу открытого документа, сэр."
        if not body:
            return "Документ пуст, сэр."
        return "В документе: " + _truncate(body)

    match = re.fullmatch(
        r"(?:добавь|вставь|сделай)\s+таблицу\s+(\d{1,2})\s+на\s+(\d{1,2})",
        text,
    )
    if match:
        rows, cols = int(match.group(1)), int(match.group(2))
        if word.add_table(rows, cols):
            return f"Добавил таблицу {rows} на {cols}, сэр."
        return "Не удалось добавить таблицу, сэр."

    match = re.fullmatch(
        r"(?:добавь|вставь)\s+заголовок(?:\s+(\d)\s+уровня)?\s+(.+)", text
    )
    if match:
        level = int(match.group(1) or 1)
        body = _word_phrase(match.group(2), raw)
        if word.add_heading(body, level):
            return f"Добавил заголовок «{body}», сэр."
        return "Не удалось добавить заголовок, сэр."

    match = re.fullmatch(
        r"(?:добавь|допиши|вставь|напиши|запиши|напечатай)\s+"
        r"(?:в\s+(?:документ|ворд\w*|word)\s+)?"
        r"(?:текст\s+)?(.+)",
        text,
    )
    if match:
        body = format_dictation(match.group(1), raw)
        name = word.append_text(body)
        if name is None:
            return "Не удалось добавить текст в документ, сэр."
        return f"Добавил текст в документ «{name}», сэр."

    if re.fullmatch(
        r"(?:сохрани|сохранить)\s+(?:документ\s+)?(?:в\s+)?pdf|"
        r"(?:экспорт|выгрузи)\s+(?:документ\s+)?в\s+pdf|сделай\s+pdf",
        text,
    ):
        target = word.export_pdf()
        if target is None:
            return "Не вижу открытого документа, сэр."
        return f"Сохранил PDF: {target.name}, сэр."

    match = re.fullmatch(
        r"(?:сохрани|сохранить)\s+(?:документ|ворд|файл)"
        r"(?:\s+как\s+(.+))?", text
    )
    if match:
        target = word.save_document(
            _raw_tail(match.group(1), raw) if match.group(1) else ""
        )
        if target is None:
            return "Не вижу открытого документа, сэр."
        return f"Сохранил документ «{target.name}», сэр."

    match = re.fullmatch(r"(?:замени|заменить)\s+(.+?)\s+на\s+(.+)", text)
    if match:
        old = _word_phrase(match.group(1), raw)
        new = _word_phrase(match.group(2), raw)
        if word.replace_all(old, new):
            return f"Заменил «{old}» на «{new}», сэр."
        return "Не удалось заменить текст, сэр."

    if re.fullmatch(
        r"(?:закрой|закрыть)\s+документ(?:\s+без\s+сохранения)?", text
    ):
        save = "без сохранения" not in text
        name = word.close_document(save=save)
        if name is None:
            return "Не вижу открытого документа, сэр."
        return f"Закрыл документ «{name}», сэр."

    if re.fullmatch(r"(?:новая|добавь)\s+страниц[ау]|разрыв\s+страницы", text):
        if word.page_break():
            return "Добавил новую страницу, сэр."
        return "Не удалось добавить страницу, сэр."
    return None


def _handle_settings(text: str) -> str | None:
    found = extras.windows_settings(text)
    if found is None:
        return None
    label, uri = found
    if actions.open_windows_settings(uri):
        return f"Открываю настройки {label}, сэр."
    return "Не удалось открыть настройки Windows, сэр."


def _handle_files(text: str) -> str | None:
    match = re.fullmatch(
        r"(найди|поищи|найти|где(?:\s+находится)?|открой|открыть)\s+"
        r"(?:мне\s+)?(?:файл|файлик|документ)\s+(.+)",
        text,
    )
    if not match:
        return None
    action, query = match.group(1), match.group(2).strip(" ,.")
    folder = None
    for suffix, name in _FILE_FOLDER_HINTS.items():
        for prefix in (" в ", " на ", " во "):
            tail = prefix + suffix
            if query.endswith(tail):
                query = query[: -len(tail)].strip(" ,.")
                folder = str(Path.home() / name)
                break
        if folder:
            break
    if not query:
        return "Что именно искать, сэр?"
    found = actions.find_files(query, folder=folder, limit=5)
    if not found:
        where = f" в папке «{Path(folder).name}»" if folder else ""
        return f"Не нашёл файл «{query}»{where}, сэр."
    if action in ("открой", "открыть"):
        target = found[0]
        if actions.open_file(target):
            return f"Открываю файл «{target.name}», сэр."
        return f"Нашёл файл «{target.name}», но открыть не удалось, сэр."
    if action.startswith("где"):
        target = found[0]
        return (
            f"Файл «{target.name}» находится в папке "
            f"«{target.parent.name}», сэр."
        )
    names = "; ".join(f"«{path.name}»" for path in found[:3])
    if len(found) == 1:
        return f"Нашёл файл {names} в папке «{found[0].parent.name}», сэр."
    return f"Нашёл несколько файлов: {names}. Уточните название, сэр."


def _handle_units(text: str) -> str | None:
    if re.search(r"\b(?:доллар|евро|рубл|юан|гривн|тенге|лир|йен)\w*", text):
        return None
    explicit = bool(
        re.match(
            r"(?:переведи|перевести|сконвертируй|конвертируй|"
            r"конвертировать|пересчитай)\b",
            text,
        )
    )
    howmany = bool(re.match(r"сколько\s+.+\s+(?:в|во)\s+", text))
    if not (explicit or howmany):
        return None
    spoken = _words_to_digits(text)
    spoken = re.sub(r"\bминус\s+", "-", spoken)
    spoken = re.sub(
        r"\b([2-9]0)\s+([1-9])\b",
        lambda match: str(int(match.group(1)) + int(match.group(2))),
        spoken,
    )
    answer = extras.convert_units(spoken)
    if answer is not None:
        return answer
    if explicit and re.search(r"\d", spoken) and re.search(r"\s(?:в|во)\s", spoken):
        return (
            "Не понял единицы измерения, сэр. Например: "
            "переведи десять километров в мили."
        )
    return None


def _handle_password(text: str) -> str | None:
    if not re.search(
        r"(?:сгенерируй|сгенерировать|создай|создать|придумай|сделай|дай|"
        r"нужен|нужен новый)\s+(?:мне\s+)?(?:случайный\s+|новый\s+|"
        r"надёжный\s+|надежный\s+)?(?:пароль|пин)",
        text,
    ) and not re.fullmatch(r"(?:пароль|пин)(?:\s+на\s+\d{1,3}\s*\w*)?", text):
        return None
    result = extras.generate_password(text)
    if not result:
        return None
    if "пин" in text:
        return f"Ваш ПИН-код: {result}."
    copied = actions.copy_text(result)
    if copied:
        return f"Ваш пароль: {result}. Скопировал в буфер обмена, сэр."
    return f"Ваш пароль: {result}."


def _handle_random_choice(text: str) -> str | None:
    return extras.random_choice(text)


def _fmt_due(due: datetime) -> str:
    now = datetime.now()
    if due.date() == now.date():
        return f"сегодня в {due:%H:%M}"
    if due.date() == (now + timedelta(days=1)).date():
        return f"завтра в {due:%H:%M}"
    return f"{due:%d.%m} в {due:%H:%M}"


def _handle_reminders(brain, text: str) -> str | None:
    if re.fullmatch(
        r"(?:какие|покажи|показать|список|мои|у меня)\s+"
        r"(?:есть\s+)?(?:напоминания|таймеры)|"
        r"что\s+там\s+по\s+(?:напоминаниям|таймерам)|"
        r"напоминания|таймеры",
        text,
    ):
        items = brain.reminders.upcoming()
        if not items:
            return "Активных напоминаний и таймеров нет, сэр."
        parts = []
        for due, what in items:
            what = re.sub(r"\s+сработал$", "", what)
            parts.append(f"{_fmt_due(due)} — {what}")
        return "Ближайшие: " + "; ".join(parts[:5]) + "."
    match = re.fullmatch(
        r"отмени\s+(?:(все|последнее|последний)\s+)?"
        r"(напоминания|напоминание|таймеры|таймер)"
        r"(?:\s+(?:о|про|на)\s+(.+))?",
        text,
    )
    if not match:
        return None
    mode, noun, query = match.group(1), match.group(2), match.group(3)
    kind = "timer" if noun.startswith("таймер") else "reminder"
    if query:
        removed = brain.reminders.cancel(query)
        if not removed:
            return f"Не нашёл напоминание про «{query}», сэр."
        return f"Отменил напоминание про «{query}», сэр."
    if mode == "все":
        count = brain.reminders.clear(kind)
        if not count:
            return "Там и так пусто, сэр."
        label = "таймеры" if kind == "timer" else "напоминания"
        return f"Отменил все {label}, сэр."
    what = brain.reminders.cancel_last(kind)
    if what is None:
        label = "таймеров" if kind == "timer" else "напоминаний"
        return f"Активных {label} нет, сэр."
    what = re.sub(r"\s+сработал$", "", what)
    return f"Отменил «{what}», сэр."


def _handle_small_stuff(text: str) -> str | None:
    match = re.fullmatch(
        r"(?:посчитай|вычисли|сколько\s+будет|чему\s+равно)\s+(.+)", text
    )
    if match:
        expression = _words_to_digits(match.group(1))
        if not re.search(r"\d", expression):
            return None
        value = evaluate(expression)
        if value is None:
            return "Не понял выражение, сэр. Скажите, например: два плюс два."
        return f"Получится {format_result(value)}."
    if re.fullmatch(
        r"(?:подбрось|брось|кинь)\s+монет(?:ку|у)|монетка", text
    ):
        return f"{random.choice(['Орёл', 'Решка'])}, сэр."
    if re.fullmatch(r"(?:брось|кинь)\s+кубик|кубик", text):
        return f"Выпало {random.randint(1, 6)}."
    match = re.fullmatch(
        r"(?:случайное|рандомное)\s+число"
        r"(?:\s+от\s+(\d{1,9})\s+до\s+(\d{1,9}))?",
        text,
    )
    if match:
        low = int(match.group(1) or 1)
        high = int(match.group(2) or 100)
        if low > high:
            low, high = high, low
        return f"Случайное число: {random.randint(low, high)}."
    if re.fullmatch(r"расскажи\s+шутку|пошути|шутку", text):
        return random.choice(JOKES)
    if re.fullmatch(r"расскажи\s+факт|интересный\s+факт|факт", text):
        return random.choice(FACTS)
    if re.fullmatch(
        r"кто\s+ты|как\s+тебя\s+зовут|тво[её]\s+имя|представься",
        text,
    ):
        return (
            "Я Хряк, ваш голосовой ассистент, сэр. Управляю компьютером, "
            "браузером, Telegram и отвечаю на вопросы."
        )
    if re.fullmatch(r"сколько\s+тебе\s+лет", text):
        return "Ровно столько, сколько нужно, сэр."
    if re.fullmatch(r"ты\s+лучший|молодец", text):
        return "Стараюсь, сэр."
    if re.fullmatch(r"доброй\s+ночи|спокойной\s+ночи", text):
        return "Доброй ночи, сэр. Отдыхайте."
    return None


def handle(brain, text: str) -> str | None:
    """Возвращает ответ или None, если команда не распознана."""
    raw = getattr(brain, "_raw_text", "")
    answer = _handle_browser_link(text)
    if answer is not None:
        return answer
    for handler in (
        _handle_word,
        _handle_windows,
        _handle_clipboard,
        _handle_browser_page,
        _handle_system,
        _handle_folders,
        _handle_settings,
        _handle_files,
        _handle_units,
        _handle_password,
        _handle_random_choice,
    ):
        answer = (
            handler(text, raw)
            if handler in (_handle_clipboard, _handle_word)
            else handler(text)
        )
        if answer is not None:
            return answer

    answer = _handle_reminders(brain, text)
    if answer is not None:
        return answer

    # Таймер требует доступа к brain.reminders, поэтому обрабатываем здесь.
    match = re.fullmatch(r"(?:поставь\s+)?таймер\s+(?:на\s+)?(.+)", text)
    if match:
        raw = match.group(1).strip()
        parsed = parse_reminder(f"через {raw} таймер")
        if parsed is None:
            return "Уточните время таймера, сэр. Например: таймер на пять минут."
        due, _rest = parsed
        brain.reminders.add(due, f"Таймер на {raw} сработал")
        return f"Поставил таймер на {raw}, сэр."

    return _handle_small_stuff(text)
