"""Telegram Desktop: открытие чатов и отправка сообщений через UI Automation.

Работает с уже установленным Telegram Desktop: находит окно, ищет чат по имени,
проверяет заголовок открытого чата и отправляет текст в поле «Сообщение».
Никаких API-ключей и входа в аккаунт не требуется.
"""
from __future__ import annotations

import difflib
import re
import time
from dataclasses import dataclass, field

import psutil
import win32api
import win32con
import win32gui
from pywinauto import Desktop
from pywinauto.keyboard import send_keys

from . import actions

TG_PROCESS = "telegram.exe"
SAVED_NAMES = {"избранное", "избранные", "saved messages", "себе", "себя"}
TYPE_PREFIXES = ("группа, ", "канал, ", "бот, ")
MIN_MATCH = 0.92
SEND_MIN_MATCH = 0.92
STRONG_MATCH = 0.92
ACTIVE_CHAT_MIN = 0.95
SEARCH_TIMEOUT = 1.6

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
    "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "i",
    "ь": "", "э": "e", "ю": "u", "я": "a",
}

_ALIASES: dict[str, str] = {}


def set_aliases(aliases: dict | None) -> None:
    """Задаёт псевдонимы контактов: «третий контакт» -> «Анна Петрова»."""
    _ALIASES.clear()
    for canonical, variants in (aliases or {}).items():
        for variant in [canonical, *(variants or [])]:
            norm = _norm(variant)
            if norm:
                _ALIASES[norm] = canonical


def _canonical(name: str) -> str:
    return _ALIASES.get(_norm(name), name)


def canonical_name(name: str) -> str:
    """Публичная нормализация имени по таблице псевдонимов."""
    return _canonical(name)


def is_known_name(name: str) -> bool:
    """True, если строка — известное имя контакта или его вариант."""
    return _norm(name) in _ALIASES


def split_known_name(text: str) -> tuple[str, str] | None:
    """Отделяет самое длинное известное имя в начале текста.

    «Мария Иванова привет» -> («Мария Иванова», «привет»).
    «алекс смит» -> («Алекс Смит», «»).
    """
    words = (text or "").split()
    for size in range(len(words), 0, -1):
        candidate = " ".join(words[:size])
        if is_known_name(candidate):
            return _canonical(candidate), " ".join(words[size:]).strip()
    return None


@dataclass
class TelegramResult:
    ok: bool
    chat: str = ""
    error: str = ""
    detail: str = ""
    score: float = 0.0
    query: str = ""
    candidates: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class SearchMatch:
    element: object | None = None
    title: str = ""
    score: float = 0.0
    query: str = ""
    seen: list[str] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------
def _norm(text: str) -> str:
    text = (text or "").lower().replace("ё", "е")
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _phon(text: str) -> str:
    """Грубая фонетическая запись: «алекс смит» и «Alex Smith» -> одно и то же."""
    text = _norm(text)
    out: list[str] = []
    for ch in text:
        if ch in _TRANSLIT:
            out.append(_TRANSLIT[ch])
        elif ch.isalnum():
            out.append(ch)
        else:
            out.append(" ")
    value = "".join(out)
    value = value.replace("ph", "f").replace("ck", "k").replace("x", "ks")
    value = re.sub(r"(.)\1+", r"\1", value)
    value = value.replace("y", "i")
    value = re.sub(r"[^a-z0-9 ]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _token_score(a: str, b: str) -> float:
    qa, tb = a.split(), b.split()
    if not qa or not tb:
        return 0.0
    total = 0.0
    for word in qa:
        best = 0.0
        best_index = 0
        for index, target in enumerate(tb):
            # Короткие слова («три», «мам») сравниваем только точно, иначе
            # «три» слишком легко превращается в «Trip Info».
            if len(word) <= 3 and len(target) > 3:
                ratio = 1.0 if word == target else 0.0
            else:
                ratio = difflib.SequenceMatcher(None, word, target).ratio()
            if ratio > best:
                best = ratio
                best_index = index
        if best > 0 and best_index > 0:
            # Совпадение не с первого слова названия («Настся мама Ильи»)
            # слабее, чем «Мамаша».
            best *= 0.8
        total += best
    score = total / len(qa)
    if qa[0] == tb[0]:
        # Имя совпало с первым словом названия чата («Мария» -> «Мария Иванова»).
        score = max(score, 0.9)
    elif tb[0].startswith(qa[0]) or qa[0].startswith(tb[0]):
        # «Мама» -> «Мамаша» чуть вероятнее, чем «Настся мама Ильи».
        score = min(1.0, score + 0.05)
    return score


def _similarity(a: str, b: str) -> float:
    """Насколько похожи имена: 1.0 — совпадение, 0.0 — ничего общего.

    Сравнивает и обычное написание, и фонетическое, чтобы «алекс смит»
    находило «Alex Smith», но «алекс» не считалось совпадением с «Александра».
    """
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0

    pa, pb = _phon(na), _phon(nb)
    scores = [_token_score(na, nb), _token_score(pa, pb)]
    flat_a, flat_b = pa.replace(" ", ""), pb.replace(" ", "")
    if len(flat_a) >= 4 and len(flat_b) >= 4:
        scores.append(difflib.SequenceMatcher(None, flat_a, flat_b).ratio())

    if nb.startswith(na + " ") or na.startswith(nb + " "):
        scores.append(0.92)
    return max(scores)


def _name_variants(name: str) -> list[str]:
    """Варианты имени для поиска: «Ане» -> «аня», «алине» -> «алин», «маме» -> «мам»."""
    base = (name or "").strip().lower().replace("ё", "е")
    if not base:
        return []
    variants: list[str] = [base]
    stems: list[str] = []
    specials: list[str] = []

    endings = (
        "ами", "ями", "ой", "ей", "ею", "ою", "ам", "ям", "ах", "ях",
        "ом", "ем", "ым", "им", "у", "ю", "е", "и", "ы", "а", "я",
    )
    for end in endings:
        if len(base) > len(end) + 2 and base.endswith(end):
            stems.append(base[: -len(end)])

    if base.endswith("е") and len(base) >= 3:
        stem = base[:-1]
        specials.extend([stem + "я", stem + "а"])
    if base.endswith("и") and len(base) >= 3:
        stem = base[:-1]
        specials.extend([stem + "я", stem + "а"])
    if base.endswith("ю") and len(base) >= 3:
        specials.extend([base[:-1] + "й", base[:-1] + "я"])
    if base.endswith("ы") and len(base) >= 3:
        specials.append(base[:-1] + "а")

    # Сначала именительные формы («алина», «мама»), потом усечённые основы.
    variants.extend(specials)
    variants.extend(stems)

    seen: set[str] = set()
    result: list[str] = []
    for word in variants:
        word = word.strip()
        if len(word) >= 3 and word not in seen:
            seen.add(word)
            result.append(word)
    return result


def _best_name_score(name: str, title: str) -> float:
    """Лучшее совпадение с учётом падежных вариантов имени."""
    variants = _name_variants(name) or [name]
    return max((_similarity(variant, title) for variant in variants), default=0.0)


def _confident_name(name: str, title: str, threshold: float = MIN_MATCH) -> bool:
    """Достаточно ли надёжно имя соответствует названию чата.

    Точное совпадение и явный псевдоним из config.json считаются надёжными
    всегда. Для остальных имён требуем высокого фонетического сходства:
    похожие имена могут принадлежать разным людям.
    """
    na, nb = _norm(name), _norm(title)
    if not na or not nb:
        return False
    if na == nb:
        return True
    canon = _canonical(name)
    if _norm(canon) != na and _norm(canon) == nb:
        return True
    return _best_name_score(name, title) >= threshold


def _exact_name_match(name: str, title: str) -> bool:
    """Совпадает ли имя с чатом точно или через настроенный псевдоним.

    Это более строгая проверка, чем _confident_name: она не пропускает
    чисто фонетические совпадения вроде «женьке» -> «Zhenke». Такие случаи
    требуют явного подтверждения, чтобы не отправить сообщение не тому.
    """
    na, nb = _norm(name), _norm(title)
    if not na or not nb:
        return False
    if na == nb:
        return True
    canon = _canonical(name)
    if _norm(canon) != na and _norm(canon) == nb:
        return True

    title_words = nb.split()
    for variant in _name_variants(name):
        vn = _norm(variant)
        if vn == nb:
            return True
        # «Мария Иванова» и «Маша Петрова»: имя стоит первым словом.
        if title_words and vn == title_words[0]:
            return True
    return False


def _search_queries(name: str) -> list[str]:
    """Запросы для поиска: имя, падежные варианты, отдельные слова, транслит."""
    candidates = _name_variants(name)
    words = _norm(name).split()
    if len(words) > 1:
        # «три зи монстр»: ищем по самому длинному слову («монстр»).
        for word in sorted(words, key=len, reverse=True):
            if len(word) >= 4:
                candidates.append(word)
    phon = _phon(name)
    if phon and phon != _norm(name):
        candidates.append(phon)

    seen: set[str] = set()
    result: list[str] = []
    for query in candidates:
        query = query.strip()
        if len(query) >= 3 and query not in seen:
            seen.add(query)
            result.append(query)
    return result[:6]


# ----------------------------------------------------------------------
def _telegram_pid() -> int | None:
    for proc in psutil.process_iter(["name", "pid"]):
        if (proc.info.get("name") or "").lower() == TG_PROCESS:
            return int(proc.info["pid"])
    return None


def _find_window(log=None):
    pid = _telegram_pid()
    if pid is None:
        return None
    try:
        wins = Desktop(backend="uia").windows(process=pid)
    except Exception as exc:  # noqa: BLE001
        if log:
            log.debug("Telegram: не удалось получить окно: %s", exc)
        return None
    candidates = []
    for win in wins:
        try:
            if not win.is_visible():
                continue
            rect = win.rectangle()
            area = (rect.right - rect.left) * (rect.bottom - rect.top)
            if area < 200 * 200:
                continue
            if not win.window_text():
                continue
            candidates.append((area, win))
        except Exception:  # noqa: BLE001
            continue
    if not candidates:
        return None
    # Главное окно Telegram всегда крупнее служебных попапов.
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _force_foreground(dlg) -> bool:
    try:
        handle = dlg.handle
        if win32gui.GetForegroundWindow() == handle:
            return True
        win32gui.ShowWindow(handle, win32con.SW_RESTORE)
        try:
            dlg.set_focus()
        except Exception:  # noqa: BLE001
            pass
        if win32gui.GetForegroundWindow() != handle:
            # Нажатие Alt снимает запрет Windows на смену фокуса.
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            win32gui.SetForegroundWindow(handle)
        time.sleep(0.2)
        return win32gui.GetForegroundWindow() == handle
    except Exception:  # noqa: BLE001
        return False


def _ensure_window(log=None):
    dlg = _find_window(log)
    if dlg is None:
        if log:
            log.info("Telegram не запущен, запускаю")
        actions.open_app("telegram")
        deadline = time.time() + 15
        while time.time() < deadline:
            time.sleep(0.5)
            dlg = _find_window(log)
            if dlg is not None:
                break
    if dlg is None:
        return None
    _force_foreground(dlg)
    return dlg


def _descendants(dlg, control_type: str):
    try:
        return dlg.descendants(control_type=control_type)
    except Exception:  # noqa: BLE001
        return [e for e in dlg.descendants() if e.element_info.control_type == control_type]


def _find_edit(dlg, kind: str):
    """kind: 'search' — поиск в списке чатов, 'message' — поле сообщения."""
    marker = "Dialogs::Widget" if kind == "search" else "HistoryView::ChatWidget"
    for e in _descendants(dlg, "Edit"):
        aid = e.element_info.automation_id or ""
        if marker in aid and "InputField::Inner" in aid:
            return e
    return None


def _set_text(edit, text: str) -> bool:
    try:
        edit.set_edit_text(text)
        time.sleep(0.15)
        return (edit.get_value() or "") == text
    except Exception:  # noqa: BLE001
        return False


def _left_pane_right(dlg) -> int:
    search = _find_edit(dlg, "search")
    if search is not None:
        return search.rectangle().right + 40
    return 450


def _clean_name(text: str) -> str:
    for mark in ("\u200e", "\u200f", "\u2068", "\u2069", "\u202a", "\u202c"):
        text = text.replace(mark, "")
    return text.replace("\n", " ").strip()


def _item_title(name: str) -> str:
    name = _clean_name(name)
    low = name.lower()
    for prefix in TYPE_PREFIXES:
        if low.startswith(prefix):
            name = name[len(prefix):]
            break
    return name.split(",", 1)[0].strip()


def _item_kind(name: str) -> str:
    low = _clean_name(name).lower()
    if low.startswith("канал, "):
        return "channel"
    if low.startswith("группа, "):
        return "group"
    if low.startswith("бот, "):
        return "bot"
    return "chat"


def _dialog_items(dlg):
    """Элементы левой панели: (top, name, element), сверху вниз."""
    boundary = _left_pane_right(dlg)
    result = []
    for e in _descendants(dlg, "ListItem"):
        try:
            rect = e.rectangle()
        except Exception:  # noqa: BLE001
            continue
        if not (60 <= rect.left < boundary):
            continue
        name = _clean_name(e.window_text() or "")
        if not name:
            continue
        low = name.lower()
        if re.match(r"^(?:все чаты|люди|группки|папка)\b", low):
            continue
        result.append((rect.top, name, e))
    result.sort(key=lambda item: item[0])
    return result


def _active_chat(dlg) -> str:
    title = _clean_name(dlg.window_text() or "")
    match = re.match(r"^(.*)\s+[–-]\s+\(\d+\)$", title)
    if match:
        title = match.group(1).strip()
    else:
        match = re.match(r"^(.*)\s+\(\d+\)$", title)
        if match:
            title = match.group(1).strip()
    if title.lower() in {"telegram", "телеграм"}:
        return ""
    return title


def _wait_results(dlg, timeout: float = SEARCH_TIMEOUT):
    """Ждёт, пока результаты поиска появятся и перестанут меняться."""
    deadline = time.time() + timeout
    items = []
    last_key = None
    stable_since = 0.0
    while time.time() < deadline:
        current = _dialog_items(dlg)
        key = tuple(name for _, name, _elem in current[:12])
        if current:
            if key == last_key:
                if time.time() - stable_since >= 0.25:
                    return current
            else:
                last_key = key
                stable_since = time.time()
                items = current
        time.sleep(0.15)
    return items or _dialog_items(dlg)


def _wait_active_chat(dlg, expected: str, timeout: float = 2.5) -> str:
    deadline = time.time() + timeout
    chat = _active_chat(dlg)
    while time.time() < deadline:
        chat = _active_chat(dlg)
        if chat and _similarity(expected, chat) >= 0.5:
            return chat
        time.sleep(0.2)
    return _active_chat(dlg)


def _clear_search(dlg) -> None:
    search = _find_edit(dlg, "search")
    if search is None:
        return
    try:
        if (search.get_value() or "").strip():
            search.set_edit_text("")
            time.sleep(0.2)
    except Exception:  # noqa: BLE001
        pass


def _is_saved_name(name: str) -> bool:
    norm = _norm(name)
    return norm in SAVED_NAMES or norm.startswith("избранн")


def _choose_match(
    name: str,
    scores: dict[str, tuple[float, object, str, str]],
    seen_titles: list[str],
) -> SearchMatch:
    """Выбирает лучший чат и отмечает неоднозначные совпадения."""
    if not scores:
        return SearchMatch(seen=list(seen_titles))

    best_title = max(scores, key=lambda title: scores[title][0])
    best_score, best_elem, best_query, _best_kind = scores[best_title]

    # Если несколько личных чатов/групп совпадают с именем точно
    # («Алекс» и «Алекс Смит»), выбрать за пользователя нельзя.
    exact = [
        title
        for title, (score, _elem, _query, kind) in scores.items()
        if kind in {"chat", "group"}
        and score >= MIN_MATCH
        and _exact_name_match(name, title)
    ]

    return SearchMatch(
        element=best_elem,
        title=best_title,
        score=best_score,
        query=best_query,
        seen=list(seen_titles),
        ambiguous=exact if len(exact) >= 2 else [],
    )


def _search_and_score(dlg, name: str) -> SearchMatch | None:
    """Ищет чат и возвращает лучший вариант, не открывая его.

    Возвращает SearchMatch или None при сбое UI. Если под имя подходят
    несколько разных личных чатов/групп, заполняет ambiguous — в таком
    случае отправлять нельзя, нужно уточнение.
    """
    name = _canonical(name)
    search = _find_edit(dlg, "search")
    if search is None:
        return None

    variants = _name_variants(name) or [name]
    # title -> (score, element, query, kind)
    scores: dict[str, tuple[float, object, str, str]] = {}
    seen_titles: list[str] = []

    for query in _search_queries(name):
        if not _force_foreground(dlg):
            return None
        if not _set_text(search, query):
            continue
        items = _wait_results(dlg)
        for _top, item_name, elem in items[:15]:
            title = _item_title(item_name)
            if not title:
                continue
            kind = _item_kind(item_name)
            score = max(_similarity(variant, title) for variant in variants)
            if kind == "channel":
                # Канал нельзя перепутать с чатом: для отправки он не подходит.
                score *= 0.35
            elif kind == "bot":
                # Бот с именем «Алекс» не должен перебивать живого человека.
                score *= 0.5
            if title not in seen_titles:
                seen_titles.append(title)
            current = scores.get(title)
            if current is None or score > current[0]:
                scores[title] = (score, elem, query, kind)

        # Если уже есть точное однозначное совпадение, дальше искать незачем:
        # иначе поле поиска перебирает все падежные варианты на глазах.
        match = _choose_match(name, scores, seen_titles)
        if match.ambiguous:
            break
        if (
            match.element is not None
            and match.score >= 0.97
            and _exact_name_match(name, match.title)
        ):
            break

    return _choose_match(name, scores, seen_titles)


def _find_item_by_title(dlg, title: str):
    """Свежий UIA-элемент списка чатов по точному заголовку."""
    wanted = _norm(title)
    for _top, name, elem in _dialog_items(dlg):
        if _norm(_item_title(name)) == wanted:
            return elem
    return None


def _open_element(dlg, elem, title: str) -> str:
    """Открывает найденный элемент списка и ждёт нужный заголовок.

    После перерисовки списка UIA-элемент может устареть: invoke() теряет
    pattern, а click_input() падает с COMError. Поэтому перед каждой
    попыткой заново находим элемент по заголовку.
    """
    target = elem
    for _attempt in range(3):
        try:
            target.invoke()
            time.sleep(0.5)
            chat = _wait_active_chat(dlg, title, timeout=1.2)
            if chat and _similarity(title, chat) >= 0.6:
                return chat
        except Exception:  # noqa: BLE001
            pass

        fresh = None
        try:
            fresh = _find_item_by_title(dlg, title)
        except Exception:  # noqa: BLE001
            pass
        if fresh is not None:
            target = fresh
        try:
            target.click_input()
            time.sleep(0.5)
            chat = _wait_active_chat(dlg, title, timeout=1.2)
            if chat and _similarity(title, chat) >= 0.6:
                return chat
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.25)
    return _wait_active_chat(dlg, title)


# ----------------------------------------------------------------------
def open_chat(name: str, log=None) -> TelegramResult:
    """Открывает чат по имени. Возвращает фактический заголовок открытого чата."""
    name = (name or "").strip(" ,.!?")
    if not name:
        return TelegramResult(False, error="empty")
    name = _canonical(name)
    if log:
        log.info("Telegram: открываю чат %r", name)

    dlg = _ensure_window(log)
    if dlg is None:
        return TelegramResult(False, error="telegram")

    try:
        # «Избранное» (Saved Messages) надёжнее открыть горячей клавишей.
        if _is_saved_name(name):
            _force_foreground(dlg)
            send_keys("^0")
            time.sleep(1.0)
            chat = _active_chat(dlg)
            return TelegramResult(
                bool(chat), chat=chat, error="" if chat else "ui", score=1.0 if chat else 0.0
            )

        active = _active_chat(dlg)
        if active and _confident_name(name, active, ACTIVE_CHAT_MIN):
            # Нельзя считать текущий чат совпадением только потому, что
            # названия похожи: тёзки и похожие имена — разные люди.
            return TelegramResult(
                True, chat=active, score=_best_name_score(name, active)
            )

        resolved = _search_and_score(dlg, name)
        if resolved is None:
            # Telegram иногда ещё не отрисовал поле поиска после выхода
            # на передний план. Даём окну секунду и пробуем снова.
            time.sleep(0.8)
            fresh_dlg = _ensure_window(log)
            if fresh_dlg is not None:
                dlg = fresh_dlg
            _force_foreground(dlg)
            resolved = _search_and_score(dlg, name)
        if resolved is None:
            return TelegramResult(False, error="ui")
        if resolved.ambiguous:
            _clear_search(dlg)
            if log:
                log.info(
                    "Telegram: несколько похожих чатов: %s",
                    ", ".join(resolved.ambiguous[:5]),
                )
            return TelegramResult(
                False,
                error="ambiguous",
                score=resolved.score,
                candidates=tuple(resolved.ambiguous[:5]),
            )

        if resolved.element is None or resolved.score < MIN_MATCH:
            _clear_search(dlg)
            return TelegramResult(
                False,
                error="not_found",
                detail=resolved.title,
                score=resolved.score,
                candidates=tuple(resolved.seen[:5]),
            )

        if log:
            log.info(
                "Telegram: найден чат %r (совпадение %.2f), открываю",
                resolved.title,
                resolved.score,
            )
        chat = _open_element(dlg, resolved.element, resolved.title)
        _clear_search(dlg)

        if not chat:
            return TelegramResult(False, error="ui", candidates=tuple(resolved.seen[:5]))
        if _similarity(resolved.title, chat) < 0.6:
            return TelegramResult(
                False,
                chat=chat,
                error="wrong_chat",
                detail=resolved.title,
                score=resolved.score,
                candidates=tuple(resolved.seen[:5]),
            )
        return TelegramResult(
            True, chat=chat, score=resolved.score, query=resolved.query
        )
    except Exception as exc:  # noqa: BLE001
        if log:
            log.exception("Telegram: сбой открытия чата: %s", exc)
        return TelegramResult(False, error="ui")


def send_message(contact: str, text: str, log=None) -> TelegramResult:
    """Открывает чат (если указан контакт) и отправляет текст."""
    text = (text or "").strip()
    if not text:
        return TelegramResult(False, error="empty")

    dlg = _ensure_window(log)
    if dlg is None:
        return TelegramResult(False, error="telegram")

    try:
        contact = _canonical(contact) if contact else ""
        if contact:
            opened = open_chat(contact, log)
            # Если совпадение слабое, возможно, часть имени распозналась
            # как начало сообщения: «алекс» + «смит привет».
            if not opened.ok or opened.score < SEND_MIN_MATCH:
                words = text.split()
                best = None
                ambiguous_match = None
                # Сначала пробуем самое длинное продолжение имени:
                # «алекс» + «смит» -> Алекс Смит, остаток «привет».
                for count in sorted(
                    range(1, min(3, len(words)) + 1), reverse=True
                ):
                    candidate = _canonical(
                        (contact + " " + " ".join(words[:count])).strip()
                    )
                    remainder = " ".join(words[count:]).strip()
                    if not remainder or _is_saved_name(candidate):
                        continue
                    resolved = _search_and_score(dlg, candidate)
                    if resolved is None:
                        break
                    if resolved.ambiguous:
                        ambiguous_match = resolved
                        continue
                    if resolved.score >= STRONG_MATCH and (
                        best is None or resolved.score > best[2]
                    ):
                        best = (candidate, remainder, resolved.score)
                if best is None and ambiguous_match is not None:
                    return TelegramResult(
                        False,
                        error="ambiguous",
                        score=ambiguous_match.score,
                        candidates=tuple(ambiguous_match.ambiguous[:5]),
                    )
                if best is not None:
                    candidate, remainder, score = best
                    if log:
                        log.info(
                            "Telegram: контакт уточнён как %r (совпадение %.2f)",
                            candidate,
                            score,
                        )
                    reopened = open_chat(candidate, log)
                    if not reopened.ok:
                        return reopened
                    contact, text, opened = candidate, remainder, reopened

            if not opened.ok:
                return opened
            chat = opened.chat
            if not _is_saved_name(contact):
                score = max(opened.score, _best_name_score(contact, chat))
                if not _exact_name_match(contact, chat):
                    if log:
                        log.info(
                            "Telegram: не отправляю без подтверждения, "
                            "%r и %r похожи, но не совпадают точно "
                            "(совпадение %.2f)",
                            contact,
                            chat,
                            score,
                        )
                    return TelegramResult(
                        False,
                        chat=chat,
                        error="unsure",
                        detail=contact,
                        score=score,
                    )
        else:
            chat = _active_chat(dlg)
            if not chat:
                return TelegramResult(False, error="no_chat")

        if not _force_foreground(dlg):
            return TelegramResult(False, chat=chat, error="focus")

        inp = _find_edit(dlg, "message")
        if inp is None:
            time.sleep(0.5)
            _force_foreground(dlg)
            inp = _find_edit(dlg, "message")
        if inp is None:
            return TelegramResult(False, chat=chat, error="no_input")

        if not _set_text(inp, text):
            return TelegramResult(False, chat=chat, error="ui")

        inp.set_focus()
        time.sleep(0.15)
        if not _force_foreground(dlg):
            return TelegramResult(False, chat=chat, error="focus")
        send_keys("{ENTER}")
        time.sleep(0.7)

        try:
            left = (inp.get_value() or "").strip()
        except Exception:  # noqa: BLE001
            left = ""
        if left:
            return TelegramResult(False, chat=chat, error="not_sent")

        if log:
            log.info("Telegram: сообщение отправлено в %r", chat)
        return TelegramResult(True, chat=chat)
    except Exception as exc:  # noqa: BLE001
        if log:
            log.exception("Telegram: сбой отправки: %s", exc)
        return TelegramResult(False, error="ui")
