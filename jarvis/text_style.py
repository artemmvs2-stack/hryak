"""Оформление надиктованного текста: регистр, точки, вопросы и запятые.

GigaAM возвращает текст с пунктуацией и заглавными буквами, но команда
разбирается по нормализованной строке, где всё это уже потеряно. Модуль
находит исходный хвост фразы в сыром тексте распознавания и переносит
оформление в сообщение. Если сырого текста нет (Vosk, ручной вызов),
включаются осторожные эвристики.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

_END_CHARS = ".!?…"
_END_RE = re.compile(r"[.!?…]$")
_TRAILING_SOFT_RE = re.compile(r"[,;:]$")

_QUESTION_WORDS = {
    "кто", "что", "где", "когда", "куда", "откуда", "почему", "зачем",
    "как", "какой", "какая", "какое", "какие", "каком", "какую", "каких",
    "сколько", "чей", "чья", "чье", "чьи", "разве", "неужели", "правда",
    "можно", "стоит",
}

_QUESTION_PHRASE_RE = re.compile(
    r"\b(?:как\s+(?:дела|ты|вы|сам|сама|жизнь|настроение|прошло|"
    r"здоровье|день|выходные)|"
    r"что\s+(?:делаешь|делаете|нового|такое|происходит|случилось|"
    r"думаешь|хочешь)|"
    r"чем\s+(?:занят|занята|занимаешься)|"
    r"где\s+(?:ты|вы|находишься)|"
    r"куда\s+(?:идешь|едешь)|"
    r"(?:ты|вы)\s+(?:где|дома|готов|готова|готовы|будешь|можешь|"
    r"хочешь|знаешь|помнишь|слышишь|видишь|любишь|думаешь))"
)
_SECOND_PERSON_RE = re.compile(
    r"\b(?:ты|вы)\s+\w+(?:ешь|ишь|ешься|ишься|дешь)\b"
)

_EXCLAIM_WORDS = {
    "привет", "здравствуй", "здравствуйте", "пока", "спасибо",
    "благодарю", "поздравляю", "молодец", "ура", "вау", "ого",
    "отлично", "супер", "класс", "браво", "стоп", "осторожно",
    "быстрее", "давай", "хватит", "извини", "прости", "жаль",
    "пожалуйста",
}

_GREETING_CORES = {
    "привет", "здравствуй", "здравствуйте", "приветствую",
}
_GREETING_PHRASES = [
    ("доброе", "утро"),
    ("добрый", "день"),
    ("добрый", "вечер"),
]

_INTRO_CORES = {
    "кстати", "конечно", "наверное", "пожалуй", "итак", "например",
    "кажется", "по-моему", "во-первых", "во-вторых", "в-третьих",
    "наконец", "впрочем", "разумеется", "действительно",
}
_INTRO_PHRASES = [
    ("к", "сожалению"),
    ("к", "счастью"),
    ("честно", "говоря"),
    ("в", "общем"),
    ("в", "целом"),
    ("между", "прочим"),
]

_COMMA_BEFORE = {
    "но", "однако", "зато", "чтобы", "если", "хотя",
    "который", "которая", "которое", "которые", "которых",
    "которым", "которой", "которого",
    "когда", "пока", "где", "куда", "откуда", "почему", "зачем",
}
_SPEECH_VERBS = {
    "думаю", "думал", "думала", "знаю", "знал", "знала", "говорю",
    "говорил", "говорила", "сказал", "сказала", "надеюсь", "надеялся",
    "надеялась", "кажется", "понял", "поняла", "вижу", "слышал",
    "слышала", "чувствую", "уверен", "уверена", "жаль", "странно",
    "важно", "хорошо", "плохо",
}

_CODE_RE = re.compile(
    r"(?:https?://|ftp://|www\.|[A-Za-zА-Яа-я0-9_.-]+\.(?:com|ru|org|net|"
    r"io|dev|me|tv|info|edu|gov)\b|[\w.-]+@[\w.-]+|[A-Za-z]:\\|"
    r"<[^>]+>|```|^\s*[#{\[<~`])"
)
_URL_TOKEN_RE = re.compile(
    r"(?:https?://|ftp://|www\.)\S+|"
    r"\b[\w.-]+\.(?:com|ru|org|net|io|dev|me|tv|info|edu|gov)(?:/\S*)?",
    re.IGNORECASE,
)


def _core(token: str) -> str:
    """Слово без регистра и внешней пунктуации — для сравнения."""
    token = (token or "").lower().replace("ё", "е")
    return re.sub(r"^[^\w]+|[^\w]+$", "", token, flags=re.UNICODE)


def _tokens(text: str) -> list[str]:
    """Делит текст на слова, приклеивая отдельно стоящие знаки к слову."""
    result: list[str] = []
    for token in (text or "").split():
        if result and not re.search(r"\w", token, flags=re.UNICODE):
            result[-1] += token
        else:
            result.append(token)
    return result


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()


def match_raw_tail(text: str, raw: str | None) -> str | None:
    """Находит в сырой фразе хвост, соответствующий нормализованному тексту.

    Возвращает исходные слова с регистром и пунктуацией или None, если
    совпадение неуверенное.
    """
    payload = _tokens(text)
    source = _tokens(raw or "")
    if not payload or not source:
        return None

    def score_at(start: int) -> float:
        window = source[start:start + len(payload)]
        if len(window) != len(payload):
            return 0.0
        total = sum(
            _similarity(_core(word), _core(original))
            for word, original in zip(payload, window)
        )
        return total / len(payload)

    best_start = -1
    best_score = 0.0
    # Сначала проверяем самый вероятный вариант — конец фразы.
    for start in range(len(source) - len(payload), -1, -1):
        score = score_at(start)
        if score > best_score + 1e-9:
            best_score = score
            best_start = start
        if start == len(source) - len(payload) and score >= 0.99:
            break

    if best_start < 0 or best_score < 0.80:
        return None
    return " ".join(source[best_start:best_start + len(payload)])


def _looks_like_code(text: str) -> bool:
    return bool(_CODE_RE.search((text or "").strip()))


def _starts_with_code(text: str) -> bool:
    parts = (text or "").strip().split()
    return bool(parts) and _looks_like_code(parts[0])


def _capitalize_sentences(text: str) -> str:
    """Поднимает регистр в начале фраз, не ломая домены и пути."""
    result: list[str] = []
    capitalize_next = True
    after_end = False
    for char in text:
        if capitalize_next and char.isalpha():
            result.append(char.upper() if char.islower() else char)
            capitalize_next = False
            after_end = False
            continue
        result.append(char)
        if char in _END_CHARS:
            after_end = True
        elif char.isspace():
            if after_end:
                capitalize_next = True
        else:
            capitalize_next = False
            after_end = False
    return "".join(result)


def _tidy(text: str) -> str:
    protected: list[str] = []

    def _protect_url(match: re.Match) -> str:
        protected.append(match.group(0))
        return f"\x00{len(protected) - 1}\x00"

    text = _URL_TOKEN_RE.sub(_protect_url, text)
    text = re.sub(r"\s+([,.;:!?…])", r"\1", text)
    text = re.sub(r"([,;!?…])(?=[^\s\d])", r"\1 ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for index, value in enumerate(protected):
        text = text.replace(f"\x00{index}\x00", value)
    return text


def _question_or_exclaim(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return "."
    last = re.split(r"[.!?…]+", stripped)[-1].strip()
    lowered = last.lower().replace("ё", "е")
    words = re.findall(r"[a-zа-я0-9-]+", lowered)
    if not words:
        return "."
    first = words[0]
    if first in _QUESTION_WORDS or re.search(r"\bли\b", lowered):
        return "?"
    if _QUESTION_PHRASE_RE.search(lowered):
        return "?"
    if _SECOND_PERSON_RE.search(lowered) and not re.search(r"\bи\b", lowered):
        return "?"
    if first in _EXCLAIM_WORDS:
        return "!"
    return "."


def _ensure_terminal(text: str) -> str:
    text = text.rstrip()
    if not text:
        return text
    if _looks_like_code(text) and " " not in text:
        return text
    if _END_RE.search(text):
        return text
    if _TRAILING_SOFT_RE.search(text):
        text = text[:-1].rstrip()
    return text + _question_or_exclaim(text)


def _add_comma_after_prefix(tokens: list[str]) -> list[str]:
    """Запятая после обращения/вводного слова в начале фразы."""
    if len(tokens) < 2:
        return tokens
    cores = [_core(token) for token in tokens]
    break_at = -1
    if cores[0] in _GREETING_CORES:
        break_at = 0
    elif cores[0] in _INTRO_CORES:
        break_at = 0
    else:
        for phrase in _GREETING_PHRASES + _INTRO_PHRASES:
            length = len(phrase)
            if tuple(cores[:length]) == phrase and len(tokens) > length:
                break_at = length - 1
                break

    if break_at < 0 or len(tokens) <= break_at + 1:
        return tokens
    token = tokens[break_at]
    if token.endswith((",", ";", ":", ".", "!", "?")):
        return tokens
    tokens = list(tokens)
    tokens[break_at] = token + ","
    return tokens


def _add_commas(text: str) -> str:
    tokens = _tokens(text)
    if not tokens:
        return text
    output: list[str] = []
    for index, token in enumerate(tokens):
        core = _core(token)
        need_comma = False
        if index > 0:
            previous = _core(output[-1])
            following = _core(tokens[index + 1]) if index + 1 < len(tokens) else ""
            if core in _COMMA_BEFORE and index + 1 < len(tokens):
                need_comma = True
            elif core == "потому" and following == "что":
                need_comma = True
            elif core == "так" and following == "что":
                need_comma = True
            elif core == "пожалуйста":
                need_comma = True
            elif core == "что" and previous in _SPEECH_VERBS:
                need_comma = True
        if need_comma and output and not output[-1].endswith(
            (",", ";", ":", ".", "!", "?")
        ):
            output[-1] += ","
        output.append(token)
    return " ".join(_add_comma_after_prefix(output))


def format_dictation(text: str, raw: str | None = None) -> str:
    """Возвращает надиктованный текст с заглавными буквами и пунктуацией."""
    text = (text or "").strip()
    if not text:
        return text

    aligned = match_raw_tail(text, raw)
    if aligned and _looks_like_code(text) and " " not in text:
        # Ссылку или команду не переписываем.
        return text

    base = aligned or text
    base = _tidy(base)
    if not base:
        return text

    base = _add_commas(base)
    if not _starts_with_code(base):
        base = _capitalize_sentences(base)
    base = _ensure_terminal(base)
    return base
