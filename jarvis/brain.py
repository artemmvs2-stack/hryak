"""Мозг: разбор команд и диалог с LLM."""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime

import requests

from . import actions, extras, local_commands, pc_tools, services
from .memory import Notes, Reminders, parse_reminder
from .speech import normalize
from .text_style import format_dictation

MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]


def plural(number: int, one: str, few: str, many: str) -> str:
    number = abs(int(number))
    if number % 10 == 1 and number % 100 != 11:
        return one
    if 2 <= number % 10 <= 4 and not 12 <= number % 100 <= 14:
        return few
    return many


def fmt_time(hour: int, minute: int) -> str:
    return (
        f"{hour} {plural(hour, 'час', 'часа', 'часов')} "
        f"{minute:02d} {plural(minute, 'минута', 'минуты', 'минут')}"
    )


def fmt_datetime(dt: datetime) -> str:
    return f"{dt.day} {MONTHS[dt.month - 1]} в {fmt_time(dt.hour, dt.minute)}"

RESTART_RE = re.compile(r"^(перезагрузи|перезагрузка|ребут)")
SHUTDOWN_RE = re.compile(r"^(выключи компьютер|выключи пк|заверши работу|завершение работы|выключение)")
CANCEL_RE = re.compile(r"^(отмена|отмени|останови выключение|не выключай)")

SITE_URLS = {
    "ютуб": "https://www.youtube.com",
    "ютюб": "https://www.youtube.com",
    "ютубе": "https://www.youtube.com",
    "ютубом": "https://www.youtube.com",
    "youtube": "https://www.youtube.com",
    "youtube.com": "https://www.youtube.com",
    "вк": "https://vk.com",
    "вконтакте": "https://vk.com",
    "vk": "https://vk.com",
    "гугл": "https://www.google.com",
    "гугле": "https://www.google.com",
    "google": "https://www.google.com",
    "яндекс": "https://ya.ru",
    "яндексе": "https://ya.ru",
    "yandex": "https://ya.ru",
    "почта": "https://mail.ru",
    "mail": "https://mail.ru",
    "одноклассники": "https://ok.ru",
    "ok": "https://ok.ru",
    "озон": "https://ozon.ru",
    "ozon": "https://ozon.ru",
    "вайлдберриз": "https://www.wildberries.ru",
    "wildberries": "https://www.wildberries.ru",
    "авито": "https://www.avito.ru",
    "avito": "https://www.avito.ru",
    "госуслуги": "https://www.gosuslugi.ru",
    "gosuslugi": "https://www.gosuslugi.ru",
    "кинопоиск": "https://www.kinopoisk.ru",
    "kinopoisk": "https://www.kinopoisk.ru",
    "рутуб": "https://rutube.ru",
    "rutube": "https://rutube.ru",
    "тикток": "https://www.tiktok.com",
    "tiktok": "https://www.tiktok.com",
    "инстаграм": "https://www.instagram.com",
    "instagram": "https://www.instagram.com",
    "гитхаб": "https://github.com",
    "github": "https://github.com",
    "чатгпт": "https://chatgpt.com",
    "chatgpt": "https://chatgpt.com",
    "дипсик": "https://chat.deepseek.com",
    "deepseek": "https://chat.deepseek.com",
    "погода": "https://yandex.ru/pogoda",
    "карты": "https://yandex.ru/maps",
    "переводчик": "https://translate.yandex.ru",
}

ENGINE_LABELS = {
    "yandex": "Яндексе",
    "google": "Google",
    "bing": "Bing",
    "duckduckgo": "DuckDuckGo",
}

LINK_VERBS = (
    r"(?:создай|сделай|сгенерируй|скопируй|задай|дай|скинь|пришли)"
)

BROWSER_PHRASES = [
    ("в яндекс браузере", "yandex"),
    ("в яндекс браузера", "yandex"),
    ("в хроме", "chrome"),
    ("в хрома", "chrome"),
    ("в хром", "chrome"),
    ("в chrome", "chrome"),
    ("в эдже", "msedge"),
    ("в edge", "msedge"),
    ("в опере", "opera"),
    ("в opera", "opera"),
    ("в файрфоксе", "firefox"),
    ("в фаерфоксе", "firefox"),
    ("в firefox", "firefox"),
]

BROWSER_WORD_KEYS = {
    "яндекс браузере": "yandex",
    "яндекс браузера": "yandex",
    "хроме": "chrome",
    "хрома": "chrome",
    "хром": "chrome",
    "chrome": "chrome",
    "эдже": "msedge",
    "edge": "msedge",
    "опере": "opera",
    "opera": "opera",
    "файрфоксе": "firefox",
    "фаерфоксе": "firefox",
    "firefox": "firefox",
}

ENGINE_PHRASES = [
    ("в яндексе", "yandex"),
    ("в яндекс", "yandex"),
    ("в гугле", "google"),
    ("в google", "google"),
    ("в бинге", "bing"),
    ("в bing", "bing"),
    ("в дакдакго", "duckduckgo"),
    ("в duckduckgo", "duckduckgo"),
]


def _extract_browser(text: str) -> tuple[str, str]:
    """Убирает «в хроме» и возвращает (запрос, ключ браузера)."""
    for phrase, key in BROWSER_PHRASES:
        match = re.search(r"(?:^|\s)" + re.escape(phrase) + r"\b", text)
        if match:
            cleaned = (text[: match.start()] + " " + text[match.end() :]).strip()
            return cleaned, key
    return text, ""


def _extract_engine(text: str) -> tuple[str, str]:
    """Убирает «в гугле» и возвращает (запрос, ключ поисковика)."""
    for phrase, key in ENGINE_PHRASES:
        match = re.search(r"(?:^|\s)" + re.escape(phrase) + r"\b", text)
        if match:
            cleaned = (text[: match.start()] + " " + text[match.end() :]).strip()
            return cleaned, key
    return text, ""


def _strip_youtube(text: str) -> tuple[str, bool]:
    cleaned = re.sub(r"\b(?:на|в)\s+(?:ютубе|youtube)\b", " ", text)
    return cleaned.strip(), cleaned != text


def _clean_query(text: str) -> str:
    text = re.sub(
        r"\b(?:в\s+(?:браузере|интернете|новой\s+вкладке)|"
        r"из\s+интернета|пожалуйста|мне|сэр)\b",
        " ",
        text,
    )
    text = re.sub(
        r"\s+в\s+(?:новой|новую)\s+вкладк[еу]$", "", text
    )
    text = re.sub(r"\s+в\s+(?:новом|новое)\s+окне$", "", text)
    text = re.sub(r"^(?:сайт|страницу|ссылку)\s+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ,.!?")


def _split_fullscreen(text: str) -> tuple[str, bool]:
    """Убирает хвост «на полный/весь экран» и сообщает, нужен ли он."""
    cleaned = re.sub(
        r"\s+(?:на|во|в)\s+(?:полный|весь|полноэкранный)\s+экран[а-я]*$",
        "",
        text,
    )
    return cleaned.strip(" ,."), cleaned != text

TG_OPEN_RE = re.compile(
    r"^(?:открой|покажи|переключись(?:\s+на)?|найди)\s+"
    r"(?:в\s+(?:телеграме|телеге|тг)\s+)?"
    r"(?:чат|час|чад|чатик|переписку|диалог|контакт)\s+"
    r"(?:(?:с|со)\s+)?(.+)$"
)
TG_OPEN_TAIL_RE = re.compile(
    r"^(?:открой|покажи|переключись(?:\s+на)?)\s+(.+?)\s+"
    r"(?:в\s+)?(?:телеграме|телеге|тг)$"
)
TG_SEND_RE = re.compile(
    r"^(ответь|напиши|отправь)(?:\s+(сообщение|смс))?\s*(.*)$"
)
TG_MARKERS_RE = re.compile(r"\b(?:в\s+)?(?:телеграме|телеграм|телеге|тг)\b")
TG_PRONOUNS = {
    "я", "мы", "ты", "он", "она", "они", "это", "мне", "ему", "ей",
    "им", "вам", "тебе", "себе", "нас", "вас",
}
TG_STOP_CONTACTS = {"на", "в", "во", "про", "о", "об", "что", "как", "зачем"}
TG_DATIVE_ENDINGS = ("е", "у", "ю", "ой", "ей", "и")


def looks_like_contact(word: str) -> bool:
    word = (word or "").strip().lower()
    return len(word) >= 3 and word.endswith(TG_DATIVE_ENDINGS)


def parse_telegram_send(text: str) -> tuple[str, str, bool] | None:
    """Разбирает «ответь/напиши/отправь ...» -> (контакт, текст, явный_контекст)."""
    match = TG_SEND_RE.match(text)
    if not match:
        return None
    verb = match.group(1)
    message_word = match.group(2) or ""
    rest = (match.group(3) or "").strip(" ,:")
    explicit = bool(message_word) or bool(TG_MARKERS_RE.search(rest))
    rest = TG_MARKERS_RE.sub(" ", rest).strip(" ,:")
    if not rest:
        return ("", "", explicit)

    # «напиши в чат Суета привет» — контакт после «в чат»
    chat_marker = re.match(r"^в\s+(?:чат|час|чад)\s+(.+)$", rest)
    if chat_marker:
        rest = chat_marker.group(1).strip(" ,:")
        parts = rest.split(maxsplit=1)
        first = parts[0]
        if first in TG_PRONOUNS or first in TG_STOP_CONTACTS:
            return ("", rest, True)
        if len(parts) == 2:
            return (first, parts[1].strip(), True)
        return (first, "", True)

    # «ответь на вопрос», «ответь мне», «ответь про погоду» — это не Telegram
    if re.match(r"^(?:на\s+(?:вопрос|вопросы|это|тему)|мне\b|про\b|об?\b)", rest):
        return None

    # «ответь, что я скоро буду» — в текущий чат
    m = re.match(r"^что\s+(.+)$", rest)
    if m and (explicit or verb in {"ответь", "отправь"}):
        return ("", m.group(1).strip(), True)

    # «напиши Ане: я скоро буду»
    m = re.match(r"^(.+?)\s*:\s*(?:что\s+)?(.+)$", rest)
    if m:
        return (m.group(1).strip(" ,"), m.group(2).strip(), True)

    # «ответь Ане, что я скоро буду» (запятая уже убрана нормализацией)
    m = re.match(r"^(\S+)\s+что\s+(.+)$", rest)
    if m and m.group(1) not in TG_PRONOUNS and m.group(1) not in TG_STOP_CONTACTS:
        return (m.group(1), m.group(2).strip(), explicit)

    parts = rest.split(maxsplit=1)
    if len(parts) == 2:
        first = parts[0]
        if first in TG_PRONOUNS or first in TG_STOP_CONTACTS:
            return ("", rest, explicit)
        return (first, parts[1].strip(), explicit)

    word = parts[0]
    if word in TG_PRONOUNS or word in TG_STOP_CONTACTS:
        return ("", rest, explicit)
    if looks_like_contact(word):
        return (word, "", explicit)
    return ("", rest, explicit)

MEDIA_CMDS = {
    "пауза": "play_pause",
    "поставь на паузу": "play_pause",
    "останови музыку": "play_pause",
    "продолжи": "play_pause",
    "плей": "play_pause",
    "следующий трек": "next",
    "следующая песня": "next",
    "дальше": "next",
    "предыдущий трек": "prev",
    "предыдущая песня": "prev",
    "назад": "prev",
}


class Brain:
    def __init__(self, cfg: dict, speaker, log, on_exit=None) -> None:
        self.cfg = cfg
        self.speaker = speaker
        self.log = log
        self.on_exit = on_exit
        self.notes = Notes()
        self.reminders = Reminders(speaker, log)
        self.history: list[dict] = []
        self._lock = threading.Lock()
        self._llm_warned = False
        self._tools_unsupported = False
        self._pending_tg: tuple[str, str, float] | None = None
        self._pending_confirm: tuple[str, str, float] | None = None
        self._raw_text = ""
        self._last_answer = ""

    # ------------------------------------------------------------------
    def handle(self, raw: str, allow_llm: bool = True) -> None:
        text = normalize(raw)
        if not text:
            return
        self.log.info("Команда: %r", text)
        try:
            with self._lock:
                self._raw_text = (raw or "").strip()
                answer = self._handle_pending(text)
                if answer is None:
                    answer = self._route(text, allow_llm=allow_llm)
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Сбой обработки команды: %s", exc)
            answer = "Прошу прощения, сэр, произошла ошибка при выполнении команды."
        if answer:
            self.log.info("Ответ: %s", answer)
            self._last_answer = answer
            self.speaker.say(answer)
        elif not allow_llm:
            self.log.info("Без обращения: пропускаю %r", text)

    def handle_followup(self, raw: str) -> None:
        """Команда без wake-word: только локальные команды, без свободного чата.

        Так фоновый разговор в комнате не уходит в GPT и не тратит запросы.
        Для вопроса достаточно снова позвать «Хряк».
        """
        self.handle(raw, allow_llm=False)

    # ------------------------------------------------------------------
    def _handle_pending(self, text: str) -> str | None:
        """Продолжение диалога: подтверждение отправки, «кому?» и «что?»."""
        if self._pending_confirm is not None:
            chat, message, until = self._pending_confirm
            if time.monotonic() > until:
                self._pending_confirm = None
            elif re.match(
                r"^(?:да|давай|отправляй|подтверждаю|верно|ага|конечно)\b",
                text,
            ):
                self._pending_confirm = None
                self._pending_tg = None
                try:
                    from . import telegram  # noqa: PLC0415
                except Exception as exc:  # noqa: BLE001
                    self.log.error("Telegram-модуль недоступен: %s", exc)
                    return "Не установлен компонент управления Telegram, сэр."
                telegram.set_aliases(
                    self.cfg.get("telegram", {}).get("aliases")
                )
                result = telegram.send_message(chat, message, self.log)
                return self._telegram_send_answer(chat, result)
            elif re.match(
                r"^(?:нет|не надо|не отправляй|отмена|отмени|стоп)\b",
                text,
            ):
                self._pending_confirm = None
                return "Отменил, сэр."
            else:
                # Любая другая фраза отменяет подтверждение.
                self._pending_confirm = None

        if self._pending_tg is None:
            return None
        step, contact, until = self._pending_tg
        if time.monotonic() > until:
            self._pending_tg = None
            return None
        if re.match(r"^(?:отмена|отмени|не надо|стоп)\b", text):
            self._pending_tg = None
            return "Отменил, сэр."
        if re.match(
            r"^(?:открой|закрой|покажи|напиши|ответь|отправь|найди|включи|"
            r"выключи|поставь|убери|сделай|переключись|запусти|перезагрузи|"
            r"громче|тише|стоп|замолчи)\b",
            text,
        ):
            # Новая команда важнее незаконченного сообщения.
            self._pending_tg = None
            return None

        try:
            from . import telegram  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            self._pending_tg = None
            self.log.error("Telegram-модуль недоступен: %s", exc)
            return "Не установлен компонент управления Telegram, сэр."
        telegram.set_aliases(self.cfg.get("telegram", {}).get("aliases"))

        if step == "contact":
            result = telegram.open_chat(text, self.log)
            if not result.ok:
                self._pending_tg = None
                return self._telegram_open_answer(text, result)
            self._pending_tg = ("message", result.chat, time.monotonic() + 60)
            return f"Что написать в чат «{result.chat}», сэр?"

        self._pending_tg = None
        message = format_dictation(text, self._raw_text)
        result = telegram.send_message(contact, message, self.log)
        if result.error == "unsure" and result.chat:
            self._pending_confirm = (
                result.chat,
                message,
                time.monotonic() + 60,
            )
            return (
                f"Не уверен, что чат «{result.chat}» — тот самый. "
                "Отправить? Скажите «да» или «нет»."
            )
        return self._telegram_send_answer(contact, result)

    # ------------------------------------------------------------------
    def _route(self, text: str, allow_llm: bool = True) -> str | None:
        cfg = self.cfg

        # --- повторить последний ответ ---
        if re.fullmatch(
            r"(?:повтори|повторите)(?:\s+(?:последний\s+)?ответ)?|"
            r"что\s+ты\s+(?:сказал|говорил)",
            text,
        ):
            return self._last_answer or "Я пока ничего не говорил, сэр."

        # --- отмена напоминаний и таймеров ---
        if re.match(
            r"^отмени\s+(?:(?:все|последнее|последний)\s+)?"
            r"(?:напоминани|таймер)",
            text,
        ):
            answer = local_commands.handle(self, text)
            if answer is not None:
                return answer

        # --- служебные ---
        if CANCEL_RE.search(text):
            actions.cancel_shutdown()
            return "Отменил, сэр."
        if re.search(r"\b(стоп|замолчи|тихо|хватит)\b", text) and len(text.split()) <= 3:
            self.speaker.stop()
            return None
        if (
            re.search(r"\b(отключись|выключись|пока|до свидания)\b", text)
            and len(text.split()) <= 3
        ):
            if self.on_exit:
                threading.Thread(target=self._delayed_exit, daemon=True).start()
            return "Отключаюсь, сэр. Буду рядом."

        # --- болтовня ---
        if re.match(
            r"^(?:привет(?:ствую)?|здравствуй(?:те)?|здорово|"
            r"добрый\s+(?:день|вечер)|доброе\s+утро)\b",
            text,
        ):
            return "Здравствуйте, сэр. Слушаю вас."
        if re.match(r"^как\s+(?:дела|ты|сам|настроение|жизнь)\b", text):
            return "Все системы в норме, сэр. Готов к работе."
        if re.match(r"^(?:что\s+делаешь|чем\s+занят)\b", text):
            return "Слежу за порядком и жду ваших команд, сэр."
        if re.match(r"^(?:спасибо|благодарю)\b", text):
            return "Всегда к вашим услугам, сэр."
        if re.search(r"(?:что ты умеешь|твои команды)", text) or re.fullmatch(
            r"(?:помощь|справка)", text
        ):
            return (
                "Я умею запускать программы, управлять окнами, браузером, "
                "вкладками, громкостью и музыкой, печатать текст, работать "
                "с буфером обмена и папками, делать скриншоты, ставить таймеры "
                "и напоминания, переводить единицы измерения, подсказывать "
                "время в других городах, искать файлы, открывать настройки "
                "Windows, генерировать пароли, выбирать из вариантов, считать, "
                "работать с документами Word и сохранять их в PDF, "
                "открывать чаты и отправлять сообщения в Telegram, "
                "подсказывать погоду, курс валют и новости. "
                "А сложные действия я выполняю через ИИ-управление компьютером."
            )

        # --- время в других городах ---
        answer = extras.city_time(text)
        if answer is not None:
            return answer

        # --- время и дата ---
        if re.search(r"(котор\w+ час|сколько времени|текущее время|время сейчас|^время$)", text):
            now = datetime.now()
            return f"Сейчас {fmt_time(now.hour, now.minute)}."
        if re.search(r"(какой сегодня день недели|какой день недели)", text):
            return f"Сегодня {WEEKDAYS[datetime.now().weekday()]}."
        if re.search(r"(какое сегодня число|какая (сегодня )?дата|какой сегодня день|какое число)", text):
            now = datetime.now()
            return (
                f"Сегодня {now.day} {MONTHS[now.month - 1]} {now.year} года, "
                f"{WEEKDAYS[now.weekday()]}."
            )

        # --- напоминания ---
        if re.search(r"\bнапомни(?:ть)?\b", text):
            body = re.sub(r"^\s*напомни(?:ть)?\s*", "", text)
            parsed = parse_reminder(body)
            if parsed is None:
                return "Уточните время, сэр. Например: напомни через десять минут позвонить маме."
            due, what = parsed
            self.reminders.add(due, what)
            return f"Хорошо, напомню {fmt_datetime(due)}: {what}."

        # --- заметки ---
        if re.search(r"(прочитай|покажи)\s+(заметки|мои заметки)", text):
            lines = self.notes.last(5)
            if not lines:
                return "Заметок пока нет, сэр."
            return "Ваши последние заметки. " + "; ".join(
                ln.lstrip("- ").split("] ", 1)[-1] for ln in lines
            )
        if re.search(r"^(запиши|заметка|запомни|добавь заметку)", text):
            body = re.sub(
                r"^(запиши|заметка|запомни|добавь)\s*(заметку)?\s*", "", text
            ).strip()
            if not body:
                return "Что именно записать, сэр?"
            self.notes.add(format_dictation(body, self._raw_text))
            return "Записал, сэр."

        # --- громкость и медиа ---
        m = re.search(r"громкость (?:на )?(\d{1,3})", text)
        if m:
            value = int(m.group(1))
            if actions.set_volume_percent(value):
                return f"Громкость {value} процентов."
            return "Не удалось изменить громкость, сэр."
        if re.search(r"(громче|прибавь (звук|громкость)|увеличь громкость)", text):
            actions.press_key(actions.VK["vol_up"], 6)
            return "Сделал громче."
        if re.search(r"(тише|убавь (звук|громкость)|уменьши громкость)", text):
            actions.press_key(actions.VK["vol_down"], 6)
            return "Сделал тише."
        if re.search(r"(выключи|включи) звук|без звука| mute", text):
            actions.mute_toggle()
            return "Переключил звук."

        for phrase, key in MEDIA_CMDS.items():
            if re.fullmatch(re.escape(phrase) + r"(\s+музыку|\s+видео)?", text) or text == phrase:
                actions.press_key(actions.VK[key])
                return "Готово."

        m = re.search(r"(включи|поставь|запусти)\s+(песню|музыку|трек|плейлист)\s*(.*)", text)
        if m:
            query = m.group(3).strip() or "любимая музыка"
            services.youtube_play(query)
            return f"Открываю музыку по запросу «{query}»."

        m = re.search(r"(включи|поставь)\s+(.+)", text)
        if (
            m
            and "видео" not in m.group(2)
            and re.search(r"(ютуб|youtube)", m.group(2))
        ):
            query = re.sub(r"(на )?(ютубе|youtube)", "", m.group(2)).strip()
            services.youtube_play(query or "музыка")
            return f"Открываю YouTube: {query}."

        # --- система ---
        if re.search(r"(скриншот|снимок экрана|скрин)", text):
            path = actions.screenshot()
            return f"Скриншот сохранён: {path}"

        if re.search(r"(заблокируй|блокировка|заблокировать)", text):
            actions.lock_pc()
            return "Блокирую компьютер, сэр."

        if SHUTDOWN_RE.search(text) or RESTART_RE.search(text):
            restart = bool(RESTART_RE.search(text))
            actions.shutdown(delay=15, restart=restart)
            word = "перезагрузку" if restart else "выключение"
            return f"Запускаю {word} через 15 секунд. Скажите «отмена», чтобы остановить."

        if re.search(r"(заряд|батаре|аккумулятор)", text):
            bat = actions.battery_status()
            if bat is None:
                return "Батарея не обнаружена, сэр. Похоже, это стационарный компьютер."
            state = "заряжается" if bat["plugged"] else "работает от батареи"
            return f"Заряд {bat['percent']} процентов, {state}."

        if re.search(r"(загрузк\w+ процессора|сколько памяти|оперативк|система загружена|нагрузк)", text):
            info = actions.system_info()
            cpu = int(round(info["cpu"]))
            ram = int(round(info["ram"]))
            return (
                f"Процессор загружен на {cpu} {plural(cpu, 'процент', 'процента', 'процентов')}, "
                f"память на {ram} {plural(ram, 'процент', 'процента', 'процентов')}, "
                f"свободно {info['disk']:.1f} гигабайт на диске C."
            )

        # --- погода / курсы / новости ---
        m = re.search(r"погод\w*\s+на\s+завтра(?:\s+в\s+(.+))?", text)
        if m:
            city = (m.group(1) or cfg.get("city", "Москва")).strip(" ,.")
            answer = services.weather_forecast(city, self.log)
            return answer or "Не удалось узнать прогноз погоды, сэр."

        m = re.search(r"погод\w*(?:\s+(?:в|во|на)\s+(.+))?", text)
        if m:
            city = (m.group(1) or cfg.get("city", "Москва")).strip(" ,.")
            answer = services.weather(city, self.log)
            return answer or "Не удалось узнать погоду, сэр. Проверьте подключение к интернету."

        if re.search(r"курс", text):
            code = "USD"
            if "евро" in text:
                code = "EUR"
            elif "юан" in text:
                code = "CNY"
            elif "фунт" in text:
                code = "GBP"
            answer = services.currency(code, self.log)
            return answer or "Не удалось получить курс валют, сэр."

        if re.search(r"(новости|что в мире|что нового)", text):
            items = services.news(3, self.log)
            if not items:
                return "Не удалось получить новости, сэр."
            return "Главные новости. " + " ".join(
                f"{i + 1}. {t}." for i, t in enumerate(items)
            )

        # --- Telegram ---
        answer = self._telegram_command(text)
        if answer is not None:
            return answer

        # --- дополнительные локальные команды ---
        answer = local_commands.handle(self, text)
        if answer is not None:
            return answer

        # --- браузер: поиск, видео, ссылки, вкладки ---
        answer = self._browser_command(text)
        if answer is not None:
            return answer

        # --- программы ---
        m = re.search(r"\b(открой|запусти|включи)\s+(.+)$", text)
        if m:
            target = re.sub(r"^(программу|приложение|мне|пожалуйста)\s+", "", m.group(2)).strip()
            target, browser = _extract_browser(target)
            target = re.sub(
                r"\s+в\s+(?:браузере|интернете|новой\s+вкладке)$", "", target
            ).strip(" ,.")
            site = self._site_url(target)
            if site:
                opened = services.open_url(site, browser or None)
                self.log.info("open_site(%r) -> %r", target, opened)
                return f"Открываю {target}, сэр." if opened else f"Не удалось открыть {target}."
            if re.search(r"(сайт|страниц|ссылк)", target):
                query = re.sub(r"(сайт|страницу|ссылку)\s*", "", target) or "ya.ru"
                url = self._open_target_url(query)
                if url:
                    services.open_url(url)
                    return f"Открываю {query}."
                if services.web_search(query, self._search_engine()):
                    return f"Ищу: {query}."
                return "Не удалось открыть браузер, сэр."
            opened = actions.open_app(target)
            self.log.info("open_app(%r) -> %r", target, opened)
            return f"Открываю {target}, сэр." if opened else f"Не нашёл «{target}», сэр."

        m = re.search(r"\b(закрой|заверши|убей)\s+(.+)$", text)
        if m:
            target = m.group(2).strip()
            closed = actions.close_app(target)
            self.log.info("close_app(%r) -> %r", target, closed)
            if closed:
                return f"Закрыл {target}, сэр."
            return f"Не удалось закрыть {target}."

        # --- всё остальное -> LLM (только после обращения по имени) ---
        if not allow_llm:
            return None
        return self._ask_llm(text)

    # ------------------------------------------------------------------
    def _search_engine(self) -> str:
        return str(self.cfg.get("search_engine") or "yandex").lower()

    def _site_url(self, target: str) -> str | None:
        """Находит сайт по названию, в том числе при смешанной раскладке."""
        key = (target or "").strip().lower()
        if not key:
            return None
        known = SITE_URLS.get(key)
        if known:
            return known
        best_url = None
        best_score = 0.0
        for site_key, url in SITE_URLS.items():
            score = actions.app_name_score(target, site_key)
            if score > best_score:
                best_score = score
                best_url = url
        if best_score >= 0.8:
            self.log.info("Сайт %r -> %r (%.2f)", target, best_url, best_score)
            return best_url
        return None

    def _open_target_url(self, target: str) -> str:
        known = SITE_URLS.get(target.strip().lower())
        if known:
            return known
        return services.normalize_url(target) or ""

    def _make_link(self, target: str) -> str:
        known = SITE_URLS.get(target.strip().lower())
        if known:
            return known
        url = services.normalize_url(target)
        if url:
            return url
        video = re.match(r"^(?:видео|ролик)\s+(.+)$", target)
        if video:
            found = services.youtube_first(video.group(1), self.log)
            if found:
                return found[0]
            return services.video_search_url(video.group(1), "youtube")
        return services.search_url(target, self._search_engine())

    def _video_fullscreen_later(self, delay: float = 2.5) -> None:
        time.sleep(delay)
        if actions.browser_video_fullscreen():
            self.log.info("Браузер: включил видео на весь экран")

    def _play_first_video(
        self, query: str, browser: str = "", fullscreen: bool = False
    ) -> None:
        found = services.youtube_first(query, self.log)
        if found:
            url, title = found
            if services.open_url(url, browser):
                self.log.info("YouTube: включил первое видео %r (%s)", title, url)
                if fullscreen:
                    self._video_fullscreen_later()
                return
        self.log.warning("YouTube: видео не найдено, открываю поиск: %s", query)
        services.video_search(query, browser)

    def _open_first_video(
        self, query: str, browser: str = "", fullscreen: bool = False
    ) -> str:
        """Открывает прямую ссылку или первое найденное видео на YouTube."""
        query = _clean_query(query)
        if not query:
            return "Какое видео открыть, сэр?"
        url = self._open_target_url(query)
        if url:
            ok = services.open_url(url, browser)
            if ok and fullscreen:
                threading.Thread(
                    target=self._video_fullscreen_later,
                    daemon=True,
                ).start()
            return (
                "Открываю видео, сэр."
                if ok
                else "Не удалось открыть видео, сэр."
            )
        threading.Thread(
            target=self._play_first_video,
            args=(query, browser, fullscreen),
            daemon=True,
        ).start()
        if fullscreen:
            return f"Включаю видео «{query}» на весь экран, сэр."
        return f"Включаю видео «{query}», сэр."

    def _browser_command(self, text: str) -> str | None:
        """Поиск в браузере, видео, картинки, ссылки и вкладки."""
        text = re.sub(
            r"^(?:сделай|выполни|запусти)\s+"
            r"(?:поисковый\s+)?(?:запрос|поиск)\s+",
            "поиск ",
            text,
        )
        text, want_fullscreen = _split_fullscreen(text)

        # --- новая вкладка ---
        if re.fullmatch(
            r"(?:открой|создай|сделай)\s+(?:мне\s+)?(?:новую\s+)?вкладку",
            text,
        ) or text in {"новая вкладка", "новую вкладку"}:
            ok = actions.new_browser_tab()
            return (
                "Открыл новую вкладку, сэр."
                if ok
                else "Не удалось открыть новую вкладку, сэр."
            )

        # --- управление вкладками ---
        if re.fullmatch(
            r"(?:закрой|закрыть|убери)\s+(?:эту\s+|текущую\s+)?вкладку", text
        ):
            ok = actions.close_browser_tab()
            return (
                "Закрыл вкладку, сэр."
                if ok
                else "Не удалось закрыть вкладку, сэр."
            )
        if re.fullmatch(
            r"(?:следующая|следующую)\s+вкладк[ау]|"
            r"(?:переключись|переключи)\s+на\s+следующую\s+вкладку",
            text,
        ):
            ok = actions.next_browser_tab()
            return (
                "Переключил на следующую вкладку, сэр."
                if ok
                else "Не удалось переключить вкладку, сэр."
            )
        if re.fullmatch(
            r"(?:предыдущая|предыдущую)\s+вкладк[ау]|"
            r"(?:переключись|переключи)\s+на\s+предыдущую\s+вкладку",
            text,
        ):
            ok = actions.previous_browser_tab()
            return (
                "Переключил на предыдущую вкладку, сэр."
                if ok
                else "Не удалось переключить вкладку, сэр."
            )
        if re.fullmatch(
            r"(?:восстанови|верни|открой заново)\s+"
            r"(?:закрытую\s+)?вкладку",
            text,
        ):
            ok = actions.reopen_browser_tab()
            return (
                "Восстановил закрытую вкладку, сэр."
                if ok
                else "Не удалось восстановить вкладку, сэр."
            )
        match = re.fullmatch(
            r"(?:переключись|переключи)(?:\s+на)?\s+вкладку\s+"
            r"(?:номер\s+)?(\d{1,2})",
            text,
        )
        if not match:
            match = re.fullmatch(
                r"(?:переключись|переключи)(?:\s+на)?\s+"
                r"(?:номер\s+)?(\d{1,2})\s+вкладку",
                text,
            )
        if not match:
            match = re.fullmatch(
                r"открой\s+вкладку\s+(?:номер\s+)?(\d{1,2})", text
            )
        if not match:
            match = re.fullmatch(
                r"открой\s+(?:номер\s+)?(\d{1,2})\s+вкладку", text
            )
        if not match:
            match = re.fullmatch(r"вкладка\s+(?:номер\s+)?(\d{1,2})", text)
        if match:
            number = int(match.group(1))
            ok = actions.switch_browser_tab(number)
            return (
                f"Переключил на вкладку {number}, сэр."
                if ok
                else "Не удалось переключить вкладку, сэр."
            )

        # --- пустые команды ---
        if re.fullmatch(
            r"(?:найди|поищи|погугли|загугли|поиск|ищи)", text
        ):
            return "Что найти, сэр?"
        if re.fullmatch(
            r"(?:найди|поищи|покажи|открой|поиск)\s+(?:мне\s+)?видео",
            text,
        ):
            return "Что найти, сэр?"
        if re.fullmatch(
            r"(?:найди|поищи|покажи|поиск)\s+(?:мне\s+)?"
            r"(?:картинки|картинок|картинку|фото|изображения|изображение)",
            text,
        ):
            return "Что найти, сэр?"
        if re.fullmatch(
            r"(?:найди|поищи|покажи|открой)\s+(?:мне\s+)?"
            r"(?:на|в)\s+(?:ютубе|youtube)",
            text,
        ):
            return "Что найти на YouTube, сэр?"
        if re.fullmatch(
            r"открой\s+(?:ссылку|ссылке|сайт|сайту|страницу|странице|url|адрес)",
            text,
        ):
            return "Какую ссылку открыть, сэр?"
        if re.fullmatch(r"открой\s+в\s+(?:браузере|интернете)", text):
            return "Что открыть, сэр?"
        if re.fullmatch(
            r"(?:переключись|переключи)(?:\s+на)?\s+вкладку(?:\s+номер)?",
            text,
        ):
            return "На какую вкладку переключиться, сэр? Назовите номер."
        if re.fullmatch(
            r"(?:открой|включи|запусти)\s+(?:мне\s+)?ссылку\s+на\s+видео",
            text,
        ):
            return "Какое видео открыть, сэр?"
        if re.fullmatch(
            r"(?:открой|включи|запусти)\s+(?:мне\s+)?(?:"
            r"видео\s+(?:на|в)\s+(?:ютубе|youtube)|"
            r"(?:youtube|ютуб)\s+видео)",
            text,
        ):
            return "Какое видео открыть, сэр?"

        # --- открой ссылку на видео ---
        match = re.match(
            r"^(?:открой|включи|запусти)\s+(?:мне\s+)?"
            r"ссылку\s+на\s+видео\s+(.+)$",
            text,
        )
        if match:
            query, browser = _extract_browser(match.group(1))
            return self._open_first_video(query, browser, want_fullscreen)

        # --- открой в хроме / эдже / яндекс браузере ---
        match = re.match(
            r"^открой\s+в\s+(яндекс\s+браузере|яндекс\s+браузера|"
            r"хроме|хрома|хром|chrome|эдже|edge|опере|opera|"
            r"файрфоксе|фаерфоксе|firefox)\s+(.+)$",
            text,
        )
        if match:
            browser = BROWSER_WORD_KEYS.get(match.group(1), "")
            query = _clean_query(match.group(2))
            if not query:
                return "Что открыть, сэр?"
            url = self._open_target_url(query)
            if url:
                ok = services.open_url(url, browser)
                return "Открываю, сэр." if ok else "Не удалось открыть, сэр."
            ok = services.web_search(query, self._search_engine(), browser)
            return (
                f"Ищу в браузере: «{query}»."
                if ok
                else "Не удалось открыть браузер, сэр."
            )

        # --- открой ссылку / сайт / страницу ---
        match = re.match(
            r"^(?:открой|перейди(?:\s+по|\s+на)?)\s+"
            r"(?:ссылку|ссылке|сайт|сайту|страницу|странице|url|адрес)\s+(.+)$",
            text,
        )
        if match:
            target, browser = _extract_browser(match.group(1))
            target = _clean_query(target)
            if not target:
                return "Какую ссылку открыть, сэр?"
            url = self._open_target_url(target)
            if not url:
                ok = services.web_search(
                    target, self._search_engine(), browser
                )
                return (
                    f"Ищу: «{target}»."
                    if ok
                    else "Не удалось открыть браузер, сэр."
                )
            ok = services.open_url(url, browser)
            return (
                "Открываю ссылку, сэр."
                if ok
                else "Не удалось открыть ссылку, сэр."
            )

        # --- создай / скопируй ссылку ---
        match = re.match(
            rf"^{LINK_VERBS}\s+(?:мне\s+)?(?:новую\s+)?"
            r"(?:ссылку|ссылочку)(?:\s+(?:на|для)\s+(.+))?$",
            text,
        )
        if not match:
            match = re.match(
                rf"^{LINK_VERBS}\s+(?:мне\s+)?"
                r"(?:ссылку|ссылочку)\s+(.+)$",
                text,
            )
        if match:
            target = _clean_query(match.group(1) or "")
            if not target:
                return "На что создать ссылку, сэр?"
            url = self._make_link(target)
            if not url:
                return "Не понял, на что создать ссылку, сэр."
            if services.copy_link(url):
                self.log.info("Браузер: ссылка %s", url)
                return "Ссылка скопирована в буфер обмена, сэр."
            return "Не удалось скопировать ссылку, сэр."

        if re.fullmatch(
            r"(?:включи|открой|запусти|воспроизведи)\s+(?:мне\s+)?"
            r"(?:видео|ролик)",
            text,
        ):
            return "Что включить, сэр? Назовите видео."

        # --- открой/включи видео на YouTube (сразу первое видео) ---
        match = re.match(
            r"^(?:открой|включи|запусти|воспроизведи)\s+(?:мне\s+)?"
            r"(?:первое\s+)?видео\s+(?:на|в)\s+(?:ютубе|youtube)\s+(.+)$",
            text,
        )
        if not match:
            match = re.match(
                r"^(?:открой|включи|запусти|воспроизведи)\s+(?:мне\s+)?"
                r"(?:youtube|ютуб)\s+видео\s+(.+)$",
                text,
            )
        if match:
            query, browser = _extract_browser(match.group(1))
            return self._open_first_video(query, browser, want_fullscreen)

        # --- включи первое видео ---
        match = re.match(
            r"^(?:включи|запусти|воспроизведи)\s+(?:мне\s+)?"
            r"(?:первое\s+)?видео\s+(.+)$",
            text,
        )
        if match:
            query, browser = _extract_browser(match.group(1))
            query, _ = _strip_youtube(query)
            query = _clean_query(query)
            if not query:
                return "Что включить, сэр?"
            return self._open_first_video(query, browser, want_fullscreen)

        # --- включи на ютубе (результаты поиска) ---
        match = re.match(
            r"^(?:включи|запусти)\s+(?:мне\s+)?(?:на|в)\s+"
            r"(?:ютубе|youtube)\s+(.+)$",
            text,
        )
        if match:
            query, browser = _extract_browser(match.group(1))
            query = _clean_query(query)
            if not query:
                return "Что найти на YouTube, сэр?"
            ok = services.video_search(query, browser)
            return (
                f"Ищу на YouTube: «{query}»."
                if ok
                else "Не удалось открыть YouTube, сэр."
            )

        # --- найди / покажи / открой видео ---
        match = re.match(
            r"^(?:найди|поищи|покажи|открой|поиск)\s+(?:мне\s+)?"
            r"видео\s+(.+)$",
            text,
        )
        if match:
            query, browser = _extract_browser(match.group(1))
            query, _ = _strip_youtube(query)
            query = _clean_query(query)
            if not query:
                return "Что найти, сэр?"
            # «открой/покажи видео ...» — сразу включаем первое видео,
            # без промежуточной страницы с результатами поиска.
            if re.match(r"^(?:открой|покажи)\b", text):
                return self._open_first_video(query, browser, want_fullscreen)
            url = self._open_target_url(query)
            if url:
                ok = services.open_url(url, browser)
                if ok and want_fullscreen:
                    threading.Thread(
                        target=self._video_fullscreen_later,
                        daemon=True,
                    ).start()
                return "Открываю видео, сэр." if ok else "Не удалось открыть видео, сэр."
            ok = services.video_search(query, browser)
            return (
                f"Открываю видео по запросу «{query}»."
                if ok
                else "Не удалось открыть видео, сэр."
            )

        # --- картинки / фото ---
        match = re.match(
            r"^(?:найди|поищи|покажи|поиск)\s+(?:мне\s+)?"
            r"(?:картинки|картинок|картинку|фото|изображения|изображение)\s+(.+)$",
            text,
        )
        if match:
            query, browser = _extract_browser(match.group(1))
            query, engine = _extract_engine(query)
            query = _clean_query(query)
            if not query:
                return "Что найти, сэр?"
            ok = services.image_search(
                query, engine or self._search_engine(), browser
            )
            return (
                f"Ищу картинки: «{query}»."
                if ok
                else "Не удалось открыть поиск картинок, сэр."
            )

        # --- поиск на ютубе ---
        match = re.match(
            r"^(?:найди|поищи|покажи|открой)\s+(?:мне\s+)?"
            r"(?:на|в)\s+(?:ютубе|youtube)\s+(.+)$",
            text,
        )
        if match:
            query, browser = _extract_browser(match.group(1))
            query = _clean_query(query)
            if not query:
                return "Что найти на YouTube, сэр?"
            ok = services.video_search(query, browser)
            return (
                f"Ищу на YouTube: «{query}»."
                if ok
                else "Не удалось открыть YouTube, сэр."
            )

        # --- открыть в браузере / новой вкладке ---
        match = re.match(
            r"^открой\s+(?:в\s+(?:браузере|интернете|новой\s+вкладке))\s+(.+)$",
            text,
        )
        if not match:
            match = re.match(
                r"^открой\s+(?:новую\s+)?вкладку\s+(?:(?:с|на)\s+)?(.+)$",
                text,
            )
        if not match:
            match = re.match(
                r"^открой\s+(.+?)\s+в\s+(?:браузере|интернете)$", text
            )
        if match:
            query, browser = _extract_browser(match.group(1))
            query, engine = _extract_engine(query)
            query = _clean_query(query)
            if not query:
                return "Что открыть, сэр?"
            url = self._open_target_url(query)
            if url:
                ok = services.open_url(url, browser)
                return "Открываю, сэр." if ok else "Не удалось открыть, сэр."
            ok = services.web_search(
                query, engine or self._search_engine(), browser
            )
            return (
                f"Ищу в браузере: «{query}»."
                if ok
                else "Не удалось открыть браузер, сэр."
            )

        # --- открой известный сайт или прямую ссылку ---
        match = re.match(
            r"^(?:открой|запусти|перейди\s+на|зайди\s+на)\s+(.+)$", text
        )
        if match:
            target, browser = _extract_browser(match.group(1))
            target, engine = _extract_engine(target)
            target = _clean_query(target)
            url = self._open_target_url(target)
            if url:
                ok = services.open_url(url, browser)
                return (
                    f"Открываю {target}, сэр."
                    if ok
                    else "Не удалось открыть, сэр."
                )

        # --- общий поиск ---
        match = re.match(
            r"^(?:найди|поищи|погугли|загугли|поиск|ищи)\s+(.+)$",
            text,
        )
        if match:
            query = match.group(1)
            query, browser = _extract_browser(query)
            query, engine = _extract_engine(query)
            if not engine and text.startswith(("погугли", "загугли")):
                engine = "google"
            query = _clean_query(query)
            if not query:
                return "Что найти, сэр?"
            engine = engine or self._search_engine()
            ok = services.web_search(query, engine, browser)
            label = ENGINE_LABELS.get(engine, "поиске")
            return (
                f"Ищу в {label}: «{query}»."
                if ok
                else "Не удалось открыть браузер, сэр."
            )

        return None

    # ------------------------------------------------------------------
    def _telegram_command(self, text: str) -> str | None:
        """Команды Telegram. None — это не команда Telegram, идём дальше."""
        if not self.cfg.get("telegram", {}).get("enabled", True):
            return None

        # «открой Аню в телеграме»
        match = TG_OPEN_TAIL_RE.match(text)
        if match:
            name = re.sub(
                r"^(?:чат|час|чад|чатик|переписку|диалог|контакт)\s+"
                r"(?:(?:с|со)\s+)?",
                "",
                match.group(1),
            ).strip(" ,.")
            if name:
                return self._telegram_open(name)

        # «открой чат с Аней»
        match = TG_OPEN_RE.match(text)
        if match:
            name = re.sub(
                r"\s+в\s+(?:телеграме|телеге|тг)$", "", match.group(1)
            ).strip(" ,.")
            if not name:
                return "Какой чат открыть, сэр?"
            return self._telegram_open(name)

        # «ответь Ане, что...» / «напиши маме...»
        parsed = parse_telegram_send(text)
        if parsed is None:
            return None
        contact, message, explicit = parsed
        verb_match = TG_SEND_RE.match(text)
        verb = verb_match.group(1) if verb_match else ""

        if contact in TG_STOP_CONTACTS:
            return None
        if verb not in {"ответь", "напиши", "отправь"}:
            return None
        if not contact and not message and not explicit:
            return None

        # Отделяем полное имя контакта от текста: «Мария Иванова привет»
        # -> контакт «Мария Иванова», сообщение «привет».
        known_name = ""
        if contact:
            try:
                from . import telegram  # noqa: PLC0415

                telegram.set_aliases(self.cfg.get("telegram", {}).get("aliases"))
                split = telegram.split_known_name(f"{contact} {message}".strip())
                if split:
                    contact, message = split
                    known_name = contact
            except Exception:  # noqa: BLE001
                pass

        if (
            verb == "напиши"
            and not explicit
            and not known_name
            and not looks_like_contact(contact)
        ):
            # «напиши код на python», «напиши текст песни» — это не Telegram.
            return None

        if not message:
            if contact:
                self._pending_tg = ("message", contact, time.monotonic() + 60)
                return f"Что написать в чат «{contact}», сэр?"
            self._pending_tg = ("contact", "", time.monotonic() + 60)
            return "Кому написать, сэр?"

        message = format_dictation(message, self._raw_text)

        try:
            from . import telegram  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            self.log.error("Telegram-модуль недоступен: %s", exc)
            return "Не установлен компонент управления Telegram, сэр."
        telegram.set_aliases(self.cfg.get("telegram", {}).get("aliases"))
        result = telegram.send_message(contact, message, self.log)
        if result.error == "unsure" and result.chat:
            self._pending_confirm = (
                result.chat,
                message,
                time.monotonic() + 60,
            )
            return (
                f"Не уверен, что чат «{result.chat}» — тот самый. "
                "Отправить? Скажите «да» или «нет»."
            )
        return self._telegram_send_answer(contact, result)

    def _telegram_open(self, name: str) -> str:
        try:
            from . import telegram  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            self.log.error("Telegram-модуль недоступен: %s", exc)
            return "Не установлен компонент управления Telegram, сэр."
        telegram.set_aliases(self.cfg.get("telegram", {}).get("aliases"))
        result = telegram.open_chat(name, self.log)
        return self._telegram_open_answer(name, result)

    def _telegram_open_answer(self, name: str, result) -> str:
        if result.ok:
            return f"Открыл чат «{result.chat}», сэр."
        if result.error == "ambiguous":
            hint = ""
            if result.candidates:
                hint = " Похожие: " + ", ".join(result.candidates[:3]) + "."
            return f"Нашёл несколько похожих чатов, сэр.{hint} Назовите точнее."
        if result.error == "not_found":
            hint = ""
            if result.candidates:
                hint = " Похожие: " + ", ".join(result.candidates[:3]) + "."
            return f"Не нашёл чат «{name}», сэр." + hint
        if result.error == "telegram":
            return "Не удалось открыть Telegram, сэр."
        if result.error == "focus":
            return "Telegram не вышел на передний план, сэр. Попробуйте ещё раз."
        return "Не удалось открыть чат, сэр."

    def _telegram_send_answer(self, contact: str, result) -> str:
        if result.ok:
            return f"Отправил в чат «{result.chat}», сэр."
        if result.error == "ambiguous":
            hint = ""
            if result.candidates:
                hint = " Похожие: " + ", ".join(result.candidates[:3]) + "."
            return (
                f"Нашёл несколько похожих чатов, сэр.{hint} "
                "Не стал отправлять. Назовите точнее."
            )
        if result.error == "not_found":
            return f"Не нашёл чат «{contact}», сэр."
        if result.error == "no_chat":
            return "Откройте чат в Telegram или назовите контакт, сэр."
        if result.error == "no_input":
            return "В этом чате нельзя писать, сэр."
        if result.error == "wrong_chat":
            actual = result.chat or "другой чат"
            return f"Открылся чат «{actual}», а не «{contact}». Не стал отправлять, сэр."
        if result.error == "unsure":
            return (
                f"Не уверен, что чат «{result.chat or contact}» — тот самый. "
                "Не стал отправлять, сэр."
            )
        if result.error == "focus":
            return "Telegram не вышел на передний план, сэр. Попробуйте ещё раз."
        if result.error == "not_sent":
            return "Не удалось отправить сообщение, сэр."
        return "Не удалось отправить сообщение, сэр."

    # ------------------------------------------------------------------
    def _delayed_exit(self) -> None:
        import time  # noqa: PLC0415

        time.sleep(3)
        if self.on_exit:
            self.on_exit()

    def _llm_error(self, response) -> str | None:
        if response.status_code == 200:
            return None
        self.log.error(
            "LLM ответил %s: %s", response.status_code, response.text[:300]
        )
        body = (response.text or "").lower()
        if response.status_code == 402 or (
            response.status_code == 429
            and (
                "no credits" in body
                or "insufficient_quota" in body
                or "billing" in body
            )
        ):
            return (
                "На счету API-сервиса закончились средства, сэр. "
                "Пополните баланс в личном кабинете, и я снова смогу думать."
            )
        if response.status_code == 429:
            return "Слишком много запросов, сэр. Попробуйте через минуту."
        if response.status_code in (401, 403):
            if "unsupported_country" in body or "region" in body:
                return (
                    "Сервис блокирует запросы из вашего региона, сэр. "
                    "Включите VPN и попробуйте снова."
                )
            return "Ключ API отклонён, сэр. Проверьте его в config.json."
        return "Не удалось связаться с мозгом, сэр. Проверьте ключ и интернет."

    def _ask_llm(self, text: str) -> str:
        cfg = self.cfg.get("llm", {})
        if not cfg.get("enabled", False):
            return "Мозг отключён в настройках, сэр. Я пока умею только команды."
        key = (cfg.get("api_key") or "").strip()
        if not key:
            if not self._llm_warned:
                self._llm_warned = True
                return (
                    "Для ответов на вопросы нужен API-ключ. "
                    "Добавьте его в config.json в поле llm.api_key, сэр."
                )
            return "Мне нужен API-ключ в настройках, сэр."

        base_prompt = cfg.get("system_prompt", "")
        use_tools = bool(cfg.get("computer_control", True)) and not self._tools_unsupported
        system_prompt = (
            f"{base_prompt}\n\n{pc_tools.SYSTEM_HINT}" if use_tools else base_prompt
        )
        messages = [{"role": "system", "content": system_prompt}]
        messages += self.history[-(int(cfg.get("history_messages", 6)) * 2):]
        messages.append({"role": "user", "content": text})

        filler = (cfg.get("thinking_filler") or "").strip()
        if filler:
            self.speaker.say(filler, block=False)

        url = (
            cfg.get("base_url", "https://api.openai.com/v1").rstrip("/")
            + "/chat/completions"
        )
        model = cfg.get("model", "gpt-4o-mini")
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        timeout = float(cfg.get("timeout", 40))
        rounds = max(1, int(cfg.get("tool_rounds", 3)))
        tools = pc_tools.specs() if use_tools else None
        self.log.info(
            "Запрос к LLM: %s (инструменты: %s)", model, "да" if tools else "нет"
        )

        try:
            for round_index in range(rounds + 1):
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": float(cfg.get("temperature", 0.6)),
                    "max_tokens": int(cfg.get("max_tokens", 400)),
                }
                if tools and round_index < rounds:
                    payload["tools"] = tools
                    payload["tool_choice"] = "auto"

                response = requests.post(
                    url, headers=headers, data=json.dumps(payload), timeout=timeout
                )
                if (
                    tools
                    and response.status_code == 400
                    and "tool" in (response.text or "").lower()
                ):
                    self.log.warning(
                        "LLM не поддерживает инструменты — отключаю управление компьютером"
                    )
                    self._tools_unsupported = True
                    tools = None
                    messages[0]["content"] = base_prompt
                    payload.pop("tools", None)
                    payload.pop("tool_choice", None)
                    response = requests.post(
                        url,
                        headers=headers,
                        data=json.dumps(payload),
                        timeout=timeout,
                    )

                error = self._llm_error(response)
                if error:
                    return error
                data = response.json()
                choices = data.get("choices") or []
                if not choices:
                    return "Мозг вернул пустой ответ, сэр."
                message = choices[0].get("message") or {}
                calls = message.get("tool_calls") or []
                if not calls:
                    answer = (message.get("content") or "").strip()
                    if not answer:
                        answer = "Готово, сэр."
                    self.history.append({"role": "user", "content": text})
                    self.history.append({"role": "assistant", "content": answer})
                    keep = int(cfg.get("history_messages", 6)) * 2
                    self.history = self.history[-keep:]
                    return answer

                messages.append(
                    {
                        "role": "assistant",
                        "content": message.get("content") or "",
                        "tool_calls": calls,
                    }
                )
                for call in calls:
                    function = call.get("function") or {}
                    name = function.get("name") or ""
                    raw_args = function.get("arguments") or "{}"
                    try:
                        args = (
                            json.loads(raw_args)
                            if isinstance(raw_args, str)
                            else (raw_args or {})
                        )
                    except Exception:  # noqa: BLE001
                        args = {}
                    self.log.info("LLM-инструмент: %s %s", name, args)
                    result = pc_tools.execute(name, args, self)
                    self.log.info(
                        "LLM-инструмент %s -> %s", name, str(result)[:200]
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id") or name,
                            "name": name,
                            "content": str(result),
                        }
                    )

            return "Готово, сэр."
        except Exception as exc:  # noqa: BLE001
            self.log.error("Ошибка LLM: %s", exc)
            return "Мозг недоступен, сэр. Похоже, нет связи с интернетом."
