"""Инструменты, которые LLM может вызывать для управления компьютером."""
from __future__ import annotations

from . import actions, services
from .calc import evaluate, format_result
from .memory import parse_reminder

SYSTEM_HINT = (
    "Ты подключён к компьютеру пользователя и можешь выполнять действия "
    "через инструменты: открывать программы, сайты и папки, управлять браузером, "
    "вкладками, окнами, громкостью, медиа, буфером обмена, печатать текст, "
    "делать скриншоты, ставить заметки и напоминания, узнавать состояние системы. "
    "Вызывай инструмент только когда пользователь явно просит выполнить действие. "
    "Не выдумывай результат: дождись ответа инструмента. "
    "Никогда не выключай и не перезагружай компьютер без прямой команды."
)

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Открыть или запустить программу на компьютере.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Название программы, например блокнот, калькулятор, телеграм.",
                    }
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Открыть сайт или ссылку в браузере.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Адрес сайта или ссылка."},
                    "browser": {
                        "type": "string",
                        "description": "Необязательно: chrome, msedge, firefox, opera, yandex.",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Найти информацию в интернете и открыть результаты поиска.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Поисковый запрос."},
                    "engine": {
                        "type": "string",
                        "description": "Необязательно: yandex, google, bing, duckduckgo.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "play_youtube",
            "description": "Найти и включить первое видео на YouTube по запросу.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Что включить."}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_control",
            "description": "Управление браузером: вкладки, навигация, масштаб, полноэкранный режим.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "new_tab",
                            "close_tab",
                            "next_tab",
                            "prev_tab",
                            "reopen_tab",
                            "switch_tab",
                            "refresh",
                            "back",
                            "forward",
                            "zoom_in",
                            "zoom_out",
                            "zoom_reset",
                            "fullscreen",
                            "video_fullscreen",
                            "exit_fullscreen",
                            "private",
                            "new_window",
                            "home",
                            "scroll_down",
                            "scroll_up",
                            "top",
                            "bottom",
                            "find",
                            "seek",
                            "video_toggle",
                            "video_next",
                            "video_previous",
                        ],
                    },
                    "value": {
                        "description": "Номер вкладки, текст для поиска или секунды для перемотки.",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "volume",
            "description": "Управление громкостью компьютера.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["up", "down", "mute", "set"],
                    },
                    "value": {
                        "type": "integer",
                        "description": "Громкость в процентах для action=set.",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "media_control",
            "description": "Управление воспроизведением музыки или видео.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["play_pause", "next", "prev"],
                    }
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "window_control",
            "description": "Управление окнами Windows.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "show_desktop",
                            "switch",
                            "close_active",
                            "maximize",
                            "minimize",
                            "snap_left",
                            "snap_right",
                            "active",
                            "list",
                            "focus",
                            "close",
                        ],
                    },
                    "title": {
                        "type": "string",
                        "description": "Часть заголовка окна для focus или close.",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Напечатать текст в активном окне.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Текст для ввода."}
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard",
            "description": "Прочитать или записать текст в буфер обмена.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["read", "write"]},
                    "text": {
                        "type": "string",
                        "description": "Текст для записи при action=write.",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "screenshot",
            "description": "Сделать скриншот экрана.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lock_pc",
            "description": "Заблокировать компьютер.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sleep_pc",
            "description": "Перевести компьютер в спящий режим.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "system_info",
            "description": "Узнать состояние компьютера.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": [
                            "battery",
                            "cpu",
                            "memory",
                            "disk",
                            "ip",
                            "internet",
                            "os",
                            "hostname",
                            "top_processes",
                        ],
                    }
                },
                "required": ["kind"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_folder",
            "description": "Открыть папку: загрузки, документы, рабочий стол, музыка и другие.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Название или путь папки."}
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "note_add",
            "description": "Добавить заметку.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Текст заметки."}
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reminder_add",
            "description": "Поставить напоминание.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Что напомнить."},
                    "when": {
                        "type": "string",
                        "description": "Когда: например 'через 10 минут' или 'в 18:30'.",
                    },
                },
                "required": ["text", "when"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calc",
            "description": "Посчитать арифметическое выражение.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Выражение, например 2+2 или 15 процентов.",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "brightness",
            "description": "Управление яркостью экрана.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["up", "down", "set"]},
                    "value": {
                        "type": "integer",
                        "description": "Яркость в процентах для action=set.",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "close_app",
            "description": "Закрыть программу по названию.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Название программы."}
                },
                "required": ["name"],
            },
        },
    },
]


def specs() -> list[dict]:
    return TOOL_SPECS


def _browser_control(action: str, value) -> str:
    action = (action or "").strip().lower()
    simple = {
        "new_tab": (actions.new_browser_tab, "Открыл новую вкладку."),
        "close_tab": (actions.close_browser_tab, "Закрыл вкладку."),
        "next_tab": (actions.next_browser_tab, "Переключил на следующую вкладку."),
        "prev_tab": (actions.previous_browser_tab, "Переключил на предыдущую вкладку."),
        "reopen_tab": (actions.reopen_browser_tab, "Восстановил вкладку."),
        "refresh": (actions.browser_refresh, "Обновил страницу."),
        "back": (actions.browser_back, "Вернулся назад."),
        "forward": (actions.browser_forward, "Перешёл вперёд."),
        "zoom_in": (actions.browser_zoom_in, "Увеличил масштаб."),
        "zoom_out": (actions.browser_zoom_out, "Уменьшил масштаб."),
        "zoom_reset": (actions.browser_zoom_reset, "Сбросил масштаб."),
        "fullscreen": (actions.browser_fullscreen, "Переключил полный экран."),
        "video_fullscreen": (
            actions.browser_video_fullscreen,
            "Включил видео на весь экран.",
        ),
        "exit_fullscreen": (
            actions.browser_exit_fullscreen,
            "Вышел из полного экрана.",
        ),
        "private": (actions.browser_private, "Открыл приватное окно."),
        "new_window": (actions.browser_new_window, "Открыл новое окно браузера."),
        "home": (actions.browser_home, "Открыл домашнюю страницу."),
        "scroll_down": (lambda: actions.browser_scroll("вниз"), "Прокрутил вниз."),
        "scroll_up": (lambda: actions.browser_scroll("вверх"), "Прокрутил вверх."),
        "top": (actions.browser_scroll_top, "Перешёл в начало страницы."),
        "bottom": (actions.browser_scroll_bottom, "Перешёл в конец страницы."),
        "video_toggle": (actions.browser_video_toggle, "Переключил видео."),
        "video_next": (actions.browser_video_next, "Включил следующее видео."),
        "video_previous": (actions.browser_video_previous, "Включил предыдущее видео."),
    }
    if action in simple:
        func, message = simple[action]
        return message if func() else f"Не удалось: {action}."
    if action == "switch_tab":
        try:
            number = int(value)
        except Exception:  # noqa: BLE001
            return "Не указан номер вкладки."
        return (
            f"Переключил на вкладку {number}."
            if actions.switch_browser_tab(number)
            else "Не удалось переключить вкладку."
        )
    if action == "find":
        text = str(value or "").strip()
        if not text:
            return "Не указан текст для поиска."
        return (
            f"Ищу на странице «{text}»."
            if actions.browser_find(text)
            else "Не удалось выполнить поиск по странице."
        )
    if action == "seek":
        try:
            seconds = int(value)
        except Exception:  # noqa: BLE001
            seconds = 10
        return (
            f"Перемотал на {abs(seconds)} секунд."
            if actions.browser_seek(seconds)
            else "Не вижу видео на YouTube."
        )
    return f"Неизвестное действие браузера: {action}."


def _window_control(action: str, title: str) -> str:
    action = (action or "").strip().lower()
    if action == "show_desktop":
        actions.show_desktop()
        return "Свернул все окна."
    if action == "switch":
        actions.switch_window()
        return "Переключил окно."
    if action == "close_active":
        actions.close_active_window()
        return "Закрыл активное окно."
    if action == "maximize":
        actions.maximize_active_window()
        return "Развернул окно."
    if action == "minimize":
        actions.minimize_active_window()
        return "Свернул окно."
    if action == "snap_left":
        actions.snap_window_left()
        return "Прикрепил окно влево."
    if action == "snap_right":
        actions.snap_window_right()
        return "Прикрепил окно вправо."
    if action == "active":
        info = actions.active_window()
        return (
            f"Активно окно «{info['title']}»."
            if info
            else "Не вижу активного окна."
        )
    if action == "list":
        titles = actions.list_windows(10)
        return (
            "Открыты: " + "; ".join(titles) + "."
            if titles
            else "Не вижу открытых окон."
        )
    if action == "focus":
        found = actions.focus_window_by_title(title or "")
        return (
            f"Переключился на окно «{found}»."
            if found
            else f"Не нашёл окно «{title}»."
        )
    if action == "close":
        found = actions.close_window_by_title(title or "")
        return (
            f"Закрыл окно «{found}»."
            if found
            else f"Не нашёл окно «{title}»."
        )
    return f"Неизвестное действие с окнами: {action}."


def _system_info(kind: str) -> str:
    kind = (kind or "").strip().lower()
    if kind == "battery":
        bat = actions.battery_status()
        if bat is None:
            return "Батарея не обнаружена."
        state = "заряжается" if bat["plugged"] else "работает от батареи"
        return f"Заряд {bat['percent']} процентов, {state}."
    if kind == "cpu":
        info = actions.system_info()
        return f"Процессор загружен на {round(info['cpu'])} процентов."
    if kind == "memory":
        info = actions.system_info()
        return f"Память занята на {round(info['ram'])} процентов."
    if kind == "disk":
        info = actions.disk_info()
        return (
            f"На диске {info['drive']} свободно {info['free']:.1f} гигабайт "
            f"из {info['total']:.1f}."
        )
    if kind == "ip":
        ip = actions.local_ip()
        return f"Локальный IP: {ip}." if ip else "Не удалось определить IP."
    if kind == "internet":
        return (
            "Интернет работает."
            if actions.internet_available()
            else "Интернет недоступен."
        )
    if kind == "os":
        return f"Установлена {actions.system_details()['os']}."
    if kind == "hostname":
        return f"Компьютер называется {actions.system_details()['hostname']}."
    if kind == "top_processes":
        items = actions.top_processes(5)
        if not items:
            return "Не удалось получить список процессов."
        return "Больше всего памяти занимают: " + ", ".join(
            f"{name} — {mb} мегабайт" for name, mb in items
        ) + "."
    return f"Неизвестный показатель: {kind}."


def execute(name: str, args: dict, brain) -> str:
    """Выполняет инструмент и возвращает текстовый результат для LLM."""
    args = args or {}
    try:
        if name == "open_app":
            app = str(args.get("name") or "").strip()
            opened = actions.open_app(app)
            return (
                f"Открыл {app}."
                if opened
                else f"Не удалось найти программу «{app}»."
            )
        if name == "open_url":
            url = str(args.get("url") or "").strip()
            browser = str(args.get("browser") or "").strip() or None
            normalized = services.normalize_url(url) or url
            if not normalized:
                return "Не указан адрес."
            ok = (
                actions.open_url_in_browser(normalized, browser) is not None
                if browser
                else services.open_url(normalized)
            )
            return f"Открыл {normalized}." if ok else f"Не удалось открыть {normalized}."
        if name == "web_search":
            query = str(args.get("query") or "").strip()
            engine = str(args.get("engine") or "").strip() or brain._search_engine()
            if not query:
                return "Не указан поисковый запрос."
            ok = services.web_search(query, engine)
            return (
                f"Ищу в интернете: «{query}»."
                if ok
                else "Не удалось открыть поиск."
            )
        if name == "play_youtube":
            query = str(args.get("query") or "").strip()
            if not query:
                return "Не указан запрос."
            found = services.youtube_first(query, brain.log)
            if found:
                url, title = found
                if services.open_url(url):
                    return f"Включил видео «{title}»."
            services.video_search(query)
            return f"Открыл поиск YouTube по запросу «{query}»."
        if name == "browser_control":
            return _browser_control(
                str(args.get("action") or ""), args.get("value")
            )
        if name == "volume":
            action = str(args.get("action") or "").lower()
            if action == "up":
                actions.press_key(actions.VK["vol_up"], 6)
                return "Сделал громче."
            if action == "down":
                actions.press_key(actions.VK["vol_down"], 6)
                return "Сделал тише."
            if action == "mute":
                actions.mute_toggle()
                return "Переключил звук."
            if action == "set":
                try:
                    value = int(args.get("value"))
                except Exception:  # noqa: BLE001
                    return "Не указана громкость."
                value = max(0, min(100, value))
                return (
                    f"Громкость {value} процентов."
                    if actions.set_volume_percent(value)
                    else "Не удалось изменить громкость."
                )
            return f"Неизвестное действие со звуком: {action}."
        if name == "media_control":
            action = str(args.get("action") or "").lower()
            key = {"play_pause": "play_pause", "next": "next", "prev": "prev"}.get(
                action
            )
            if not key:
                return f"Неизвестное действие медиа: {action}."
            actions.press_key(actions.VK[key])
            return "Готово."
        if name == "window_control":
            return _window_control(
                str(args.get("action") or ""), str(args.get("title") or "")
            )
        if name == "type_text":
            text = str(args.get("text") or "")
            return (
                "Напечатал текст."
                if actions.type_text(text)
                else "Не удалось напечатать текст."
            )
        if name == "clipboard":
            action = str(args.get("action") or "").lower()
            if action == "read":
                value = actions.get_clipboard_text()
                if value is None:
                    return "Не удалось прочитать буфер обмена."
                return "Буфер пуст." if not value.strip() else f"В буфере: {value[:500]}"
            if action == "write":
                text = str(args.get("text") or "")
                return (
                    "Записал текст в буфер обмена."
                    if actions.copy_text(text)
                    else "Не удалось записать в буфер."
                )
            return f"Неизвестное действие с буфером: {action}."
        if name == "screenshot":
            return f"Скриншот сохранён: {actions.screenshot()}"
        if name == "lock_pc":
            actions.lock_pc()
            return "Заблокировал компьютер."
        if name == "sleep_pc":
            actions.sleep_pc()
            return "Перевожу компьютер в сон."
        if name == "system_info":
            return _system_info(str(args.get("kind") or ""))
        if name == "open_folder":
            folder = str(args.get("name") or "").strip()
            target = actions.open_folder(folder)
            return (
                f"Открыл папку «{folder}»."
                if target
                else f"Не нашёл папку «{folder}»."
            )
        if name == "note_add":
            text = str(args.get("text") or "").strip()
            if not text:
                return "Не указан текст заметки."
            brain.notes.add(text)
            return "Записал заметку."
        if name == "reminder_add":
            text = str(args.get("text") or "").strip()
            when = str(args.get("when") or "").strip()
            if not text or not when:
                return "Не указано, что и когда напомнить."
            parsed = parse_reminder(f"{when} {text}")
            if parsed is None:
                return "Не понял время напоминания."
            due, what = parsed
            brain.reminders.add(due, what)
            return f"Напомню {due.strftime('%d.%m в %H:%M')}: {what}."
        if name == "calc":
            expression = str(args.get("expression") or "").strip()
            value = evaluate(expression)
            if value is None:
                return "Не удалось посчитать выражение."
            return f"Получится {format_result(value)}."
        if name == "brightness":
            action = str(args.get("action") or "").lower()
            if action == "set":
                try:
                    value = int(args.get("value"))
                except Exception:  # noqa: BLE001
                    return "Не указана яркость."
                value = max(0, min(100, value))
                return (
                    f"Яркость {value} процентов."
                    if actions.set_brightness(value)
                    else "Не удалось изменить яркость."
                )
            if action in {"up", "down"}:
                value = actions.change_brightness(10 if action == "up" else -10)
                return (
                    f"Яркость {value} процентов."
                    if value is not None
                    else "Не удалось изменить яркость."
                )
            return f"Неизвестное действие с яркостью: {action}."
        if name == "close_app":
            app = str(args.get("name") or "").strip()
            return (
                f"Закрыл {app}."
                if actions.close_app(app)
                else f"Не удалось закрыть {app}."
            )
    except Exception as exc:  # noqa: BLE001
        brain.log.exception("Инструмент %s: %s", name, exc)
        return f"Ошибка при выполнении {name}: {exc}"
    return f"Неизвестный инструмент: {name}."
