"""Действия в системе Windows: программы, громкость, питание, скриншоты."""
from __future__ import annotations

import ctypes
import difflib
import json
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import threading
import time
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger("jarvis.actions")

CREATE_NO_WINDOW = 0x08000000
VK = {
    "play_pause": 0xB3,
    "next": 0xB0,
    "prev": 0xB1,
    "vol_up": 0xAF,
    "vol_down": 0xAE,
    "mute": 0xAD,
}

# Русские названия -> канонические ключи
ALIASES = {
    "браузер": "browser",
    "хром": "chrome",
    "chrome": "chrome",
    "гугл хром": "chrome",
    "опера": "opera",
    "firefox": "firefox",
    "фаерфокс": "firefox",
    "яндекс браузер": "yandex",
    "edge": "msedge",
    "эдж": "msedge",
    "блокнот": "notepad",
    "notepad": "notepad",
    "калькулятор": "calc",
    "проводник": "explorer",
    "настройки": "settings",
    "параметры": "settings",
    "терминал": "wt",
    "консоль": "cmd",
    "командную строку": "cmd",
    "диспетчер задач": "taskmgr",
    "телеграм": "telegram",
    "телеграмм": "telegram",
    "телега": "telegram",
    "тг": "telegram",
    "telegram": "telegram",
    "дискорд": "discord",
    "дискор": "discord",
    "discord": "discord",
    "стим": "steam",
    "steam": "steam",
    "спотифай": "spotify",
    "spotify": "spotify",
    "код": "code",
    "vs code": "code",
    "вс код": "code",
    "ворд": "winword",
    "word": "winword",
    "эксель": "excel",
    "excel": "excel",
    "паинт": "mspaint",
    "paint": "mspaint",
    "камера": "camera",
    "камеру": "camera",
    "почта": "outlook",
    "почту": "outlook",
    "панель управления": "control",
    "ватсап": "whatsapp",
    "вотсап": "whatsapp",
    "whatsapp": "whatsapp",
    "зум": "zoom",
    "zoom": "zoom",
    "скайп": "skype",
    "skype": "skype",
    "тимс": "teams",
    "teams": "teams",
    "microsoft teams": "teams",
    "пауэрпоинт": "powerpnt",
    "powerpoint": "powerpnt",
    "презентация": "powerpnt",
    "фотошоп": "photoshop",
    "photoshop": "photoshop",
    "обс": "obs64",
    "obs": "obs64",
    "эпик геймс": "epicgameslauncher",
    "epic games": "epicgameslauncher",
    "opencode": "opencode",
    "open code": "opencode",
    "open-cod": "opencode",
    "open cod": "opencode",
    "опен код": "opencode",
    "опенкод": "opencode",
    "о пэн код": "opencode",
    "опэн код": "opencode",
    "openkod": "opencode",
    "клауд": "claude",
    "клод": "claude",
    "claude": "claude",
    "хапп": "happ",
    "хэпп": "happ",
    "хап": "happ",
    "happ": "happ",
    "впн": "happ",
    "vpn": "happ",
    "7zip": "7zip",
    "7 зип": "7zip",
    "семь зип": "7zip",
    "7-zip": "7zip",
    "питон": "python",
    "python": "python",
    "блокнота": "notepad",
    "калькулятора": "calc",
    "телеграма": "telegram",
    "стима": "steam",
    "дискорда": "discord",
    "зума": "zoom",
    "зуму": "zoom",
    "клауда": "claude",
    "ворда": "winword",
    "экселя": "excel",
    "паинта": "mspaint",
    "хрома": "chrome",
    "хрому": "chrome",
    "оперы": "opera",
    "оперу": "opera",
    "скайпа": "skype",
    "тимса": "teams",
    "фотошопа": "photoshop",
    "обса": "obs64",
    "проводника": "explorer",
    "опен кода": "opencode",
    "опенкода": "opencode",
}

# Канонические ключи -> вероятные пути (с учётом переменных окружения)
KNOWN_PATHS = {
    "chrome": [
        r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe",
        r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe",
        r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
    ],
    "msedge": [
        r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe",
        r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe",
    ],
    "firefox": [
        r"%PROGRAMFILES%\Mozilla Firefox\firefox.exe",
        r"%PROGRAMFILES(X86)%\Mozilla Firefox\firefox.exe",
    ],
    "opera": [
        r"%APPDATA%\Programs\Opera\opera.exe",
        r"%LOCALAPPDATA%\Programs\Opera\opera.exe",
    ],
    "yandex": [
        r"%LOCALAPPDATA%\Yandex\YandexBrowser\Application\browser.exe",
        r"%PROGRAMFILES%\Yandex\YandexBrowser\Application\browser.exe",
    ],
    "telegram": [
        r"%APPDATA%\Telegram Desktop\Telegram.exe",
        r"%LOCALAPPDATA%\Telegram Desktop\Telegram.exe",
        r"%PROGRAMFILES%\Telegram Desktop\Telegram.exe",
    ],
    "discord": [
        r"%LOCALAPPDATA%\Discord\app-*\Discord.exe",
    ],
    "steam": [
        r"%PROGRAMFILES(X86)%\Steam\steam.exe",
        r"%PROGRAMFILES%\Steam\steam.exe",
    ],
    "spotify": [
        r"%APPDATA%\Spotify\Spotify.exe",
        r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe",
    ],
    "code": [
        r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
        r"%PROGRAMFILES%\Microsoft VS Code\Code.exe",
    ],
    "notepad": ["notepad.exe"],
    "calc": ["calc.exe"],
    "explorer": ["explorer.exe"],
    "cmd": ["cmd.exe"],
    "wt": ["wt.exe"],
    "taskmgr": ["taskmgr.exe"],
    "mspaint": ["mspaint.exe"],
    "control": ["control.exe"],
    "winword": ["winword.exe"],
    "excel": ["excel.exe"],
    "outlook": ["outlook.exe"],
    "powerpnt": ["powerpnt.exe"],
    "whatsapp": [
        r"%LOCALAPPDATA%\WhatsApp\WhatsApp.exe",
        r"%PROGRAMFILES%\WhatsApp\WhatsApp.exe",
    ],
    "zoom": [
        r"%APPDATA%\Zoom\bin\Zoom.exe",
        r"%PROGRAMFILES%\Zoom\bin\Zoom.exe",
        r"%PROGRAMFILES(X86)%\Zoom\bin\Zoom.exe",
    ],
    "skype": [
        r"%PROGRAMFILES%\Microsoft Skype\Phone\Skype.exe",
        r"%PROGRAMFILES(X86)%\Microsoft Skype\Phone\Skype.exe",
    ],
    "teams": [
        r"%LOCALAPPDATA%\Microsoft\WindowsApps\ms-teams.exe",
        r"%LOCALAPPDATA%\Microsoft\Teams\current\Teams.exe",
    ],
    "photoshop": [
        r"%PROGRAMFILES%\Adobe\Adobe Photoshop *\Photoshop.exe",
    ],
    "obs64": [
        r"%PROGRAMFILES%\obs-studio\bin\64bit\obs64.exe",
    ],
    "epicgameslauncher": [
        r"%PROGRAMFILES(X86)%\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
    ],
    "7zip": [
        r"%PROGRAMFILES%\7-Zip\7zFM.exe",
        r"%PROGRAMFILES(X86)%\7-Zip\7zFM.exe",
    ],
}

PROTOCOLS = {
    "settings": "ms-settings:",
    "camera": "microsoft.windows.camera:",
}

SHORTCUT_DIRS = [
    Path(os.environ.get("ProgramData", r"C:\ProgramData"))
    / "Microsoft/Windows/Start Menu/Programs",
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
]

SHORTCUT_HINTS = {
    "telegram": ["telegram"],
    "discord": ["discord"],
    "steam": ["steam"],
    "spotify": ["spotify"],
    "code": ["visual studio code", "vs code"],
    "opera": ["opera"],
    "yandex": ["яндекс", "yandex"],
    "outlook": ["outlook"],
    "whatsapp": ["whatsapp", "ватсап"],
    "zoom": ["zoom"],
    "skype": ["skype", "скайп"],
    "teams": ["teams", "тимс"],
    "powerpnt": ["powerpoint", "пауэрпоинт"],
    "photoshop": ["photoshop", "фотошоп"],
    "obs64": ["obs studio", "obs"],
    "epicgameslauncher": ["epic games", "эпик геймс"],
}

EXE_ESCAPE = {
    "calc": "calculatorapp",
    "settings": "systemsettings",
    "camera": "windowscamera",
    "wt": "windowsterminal",
    "explorer": "explorer",
    "yandex": "browser",
    "7zip": "7zFM",
}


# ----------------------------------------------------------------------
def _expand(path: str) -> Path:
    return Path(os.path.expandvars(path))


def _exe_name(target: str) -> str:
    return Path(target).stem.lower()


def _is_running(name: str) -> bool:
    try:
        import psutil  # noqa: PLC0415

        name = name.lower().replace(".exe", "")
        for proc in psutil.process_iter(["name"]):
            proc_name = (proc.info.get("name") or "").lower().replace(".exe", "")
            if proc_name == name:
                return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _launch(path: Path) -> bool:
    """Запускает exe и убеждается, что процесс действительно появился."""
    try:
        exe = _exe_name(str(path))
        before = _is_running(exe)
        log.info("Запуск %s (уже работал: %s)", path, before)
        if before:
            title = focus_process_window(exe)
            if title:
                log.info("Уже работает, переключил окно %r", title)
                return True
            log.info("Окно %s не найдено, запускаю заново", exe)
        os.startfile(str(path))  # noqa: S606
        if before:
            return True
        for _ in range(16):  # до ~4 секунд
            time.sleep(0.25)
            if _is_running(exe):
                log.info("Процесс %s появился", exe)
                return True
        log.warning("Процесс %s не появился за 4 с", exe)
        return False
    except Exception as exc:  # noqa: BLE001
        log.error("Не удалось запустить %s: %s", path, exc)
        return False


def find_shortcut(name: str) -> str | None:
    keys = SHORTCUT_HINTS.get(name, [name])
    for base in SHORTCUT_DIRS:
        if not base.exists():
            continue
        try:
            for lnk in base.rglob("*.lnk"):
                stem = lnk.stem.lower()
                if any(key in stem for key in keys) and "uninstall" not in stem and "деинстал" not in stem:
                    return str(lnk)
        except Exception:  # noqa: BLE001
            continue
    return None


# --- гибкий поиск приложений -------------------------------------------
APP_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "apps_cache.json"
APP_CACHE_TTL = 6 * 3600
APP_MATCH_THRESHOLD = 0.76
_APP_SKIP_WORDS = (
    "uninstall", "unins", "деинстал", "удал", "update", "обновлен", "helper",
    "runtime", "redistributable", "documentation", "документац", "manual",
    "readme", "help", "справк", "support", "website", "setup", "installer",
    "crash", "report", "benchmark", "лаунчер обновлен",
)
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}
_APP_MODIFIERS = re.compile(
    r"^(?:программу|программа|приложение|приложения|утилиту|утилита|"
    r"мне|пожалуйста|сэр|побыстрее|срочно)\s+"
)
_app_items_cache: tuple[float, list[dict]] | None = None


def _skip_app_name(name: str) -> bool:
    low = (name or "").lower()
    return any(word in low for word in _APP_SKIP_WORDS)


def _app_variants(text: str) -> list[str]:
    """Варианты названия: транслит и латиница из смешанной кириллицы/латиницы."""
    text = (text or "").lower().replace("ё", "е")
    for _ in range(2):
        text = _APP_MODIFIERS.sub("", text).strip()
    text = re.sub(
        r"\s+(?:пожалуйста|пожалуйста\s+сэр|сэр|побыстрее|срочно)$", "", text
    ).strip()
    cleaned = re.sub(r"[^0-9a-zа-я]+", "", text)
    if not cleaned:
        return []
    translit = "".join(_TRANSLIT.get(ch, ch) for ch in cleaned)
    variants = {translit}
    if re.search(r"[а-я]", cleaned) and re.search(r"[a-z]", cleaned):
        latin_only = re.sub(r"[а-я]+", "", cleaned)
        if len(latin_only) >= 2:
            variants.add(latin_only)
    return [item for item in variants if item]


def normalize_app_name(text: str) -> str:
    variants = _app_variants(text)
    return max(variants, key=len) if variants else ""


def _score_name(query: str, candidate: str) -> float:
    if not query or not candidate:
        return 0.0
    if query == candidate:
        return 1.0
    if len(query) >= 3 and (
        candidate.startswith(query) or query.startswith(candidate)
    ):
        return max(0.8, 0.94 - 0.01 * abs(len(candidate) - len(query)))
    if len(query) >= 3 and (query in candidate or candidate in query):
        return 0.9
    return difflib.SequenceMatcher(None, query, candidate).ratio()


def app_name_score(query: str, candidate: str) -> float:
    """Сходство названий с учётом транслита и смешанных алфавитов."""
    query_variants = _app_variants(query)
    candidate_variants = _app_variants(candidate)
    best = 0.0
    for left in query_variants:
        for right in candidate_variants:
            best = max(best, _score_name(left, right))
    return best


def _icon_exe(icon: str) -> str | None:
    icon = (icon or "").strip()
    if not icon or icon.startswith("@"):
        return None
    icon = icon.split(",")[0].strip().strip('"')
    path = Path(os.path.expandvars(icon))
    if path.suffix.lower() not in {".exe", ".bat", ".cmd", ".lnk"}:
        return None
    if path.exists() and not _skip_app_name(path.stem):
        return str(path)
    return None


def _best_exe_in_folder(folder: Path, hint: str) -> Path | None:
    if not folder.exists() or not folder.is_dir():
        return None
    found: list[Path] = []
    try:
        for pattern in ("*.exe", "*/*.exe"):
            for exe in folder.glob(pattern):
                if _skip_app_name(exe.stem):
                    continue
                try:
                    if exe.stat().st_size < 20_000:
                        continue
                except OSError:
                    continue
                found.append(exe)
    except OSError:
        return None
    if not found:
        return None
    hint_norm = normalize_app_name(hint)

    def sort_key(exe: Path) -> tuple[float, int]:
        stem = normalize_app_name(exe.stem)
        ratio = difflib.SequenceMatcher(None, hint_norm, stem).ratio()
        if stem == hint_norm:
            ratio += 0.5
        elif hint_norm and (hint_norm in stem or stem in hint_norm):
            ratio += 0.25
        return ratio, -len(str(exe))

    return max(found, key=sort_key)


def _start_app_items() -> list[dict]:
    script = (
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
        "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(  # noqa: S603
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8-sig",
            errors="replace",
            timeout=25,
            creationflags=CREATE_NO_WINDOW,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        data = json.loads(result.stdout)
    except Exception as exc:  # noqa: BLE001
        log.warning("Не удалось получить список приложений Пуска: %s", exc)
        return []
    if isinstance(data, dict):
        data = [data]
    items: list[dict] = []
    for entry in data or []:
        name = str(entry.get("Name") or "").strip()
        appid = str(entry.get("AppID") or "").strip()
        if not name or not appid or _skip_app_name(name):
            continue
        if re.match(r"^[A-Za-z]:[\\/]", appid) or appid.startswith("%"):
            kind = "path"
        elif appid.lower().startswith(
            ("http://", "https://", "steam://", "microsoft.")
        ):
            kind = "url"
        else:
            kind = "appid"
        items.append(
            {
                "name": name,
                "kind": kind,
                "target": appid,
                "source": "start",
                "priority": 0,
            }
        )
    return items


def _start_menu_items() -> list[dict]:
    items: list[dict] = []
    for base in SHORTCUT_DIRS:
        if not base.exists():
            continue
        try:
            for lnk in base.rglob("*.lnk"):
                if _skip_app_name(lnk.stem):
                    continue
                items.append(
                    {
                        "name": lnk.stem,
                        "kind": "shortcut",
                        "target": str(lnk),
                        "source": "shortcut",
                        "priority": 1,
                    }
                )
        except OSError:
            continue
    return items


def _registry_app_items() -> list[dict]:
    try:
        import winreg  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return []
    roots = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ),
    )
    items: list[dict] = []
    for hive, path in roots:
        try:
            root = winreg.OpenKey(hive, path)
        except OSError:
            continue
        try:
            count = winreg.QueryInfoKey(root)[0]
            for index in range(count):
                try:
                    sub_name = winreg.EnumKey(root, index)
                    with winreg.OpenKey(root, sub_name) as subkey:
                        def value(field: str):
                            try:
                                return winreg.QueryValueEx(subkey, field)[0]
                            except OSError:
                                return None

                        display = str(value("DisplayName") or "").strip()
                        if not display or _skip_app_name(display):
                            continue
                        target = _icon_exe(str(value("DisplayIcon") or ""))
                        if not target:
                            location = str(value("InstallLocation") or "").strip()
                            if location:
                                folder = Path(os.path.expandvars(location))
                                exe = _best_exe_in_folder(folder, display)
                                target = str(exe) if exe else None
                        if target:
                            items.append(
                                {
                                    "name": display,
                                    "kind": "path",
                                    "target": target,
                                    "source": "registry",
                                    "priority": 2,
                                }
                            )
                except OSError:
                    continue
        finally:
            winreg.CloseKey(root)
    return items


def _folder_app_items() -> list[dict]:
    roots = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
        Path(os.environ.get("PROGRAMFILES", "")),
        Path(os.environ.get("PROGRAMFILES(X86)", "")),
    ]
    skip_dirs = {
        "windows", "common files", "microsoft", "microsoft office",
        "windowsapps", "modifiablewindowsapps", "internet explorer", "dotnet",
        "reference assemblies", "msbuild", "windows kits", "windows defender",
        "windows nt", "temp", "package cache", "crashdumps", "d3d",
        "google", "mozilla", "apple", "adobe", "steam", "epic games",
    }
    items: list[dict] = []
    seen: set[str] = set()
    for root in roots:
        if not root or not root.exists():
            continue
        try:
            children = [item for item in root.iterdir() if item.is_dir()]
        except OSError:
            continue
        for child in children:
            name = child.name
            if name.lower() in skip_dirs or _skip_app_name(name):
                continue
            exe = _best_exe_in_folder(child, name)
            if not exe:
                continue
            key = str(exe).lower()
            if key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "name": name,
                    "kind": "path",
                    "target": str(exe),
                    "source": "folder",
                    "priority": 3,
                }
            )
    return items


def _load_app_cache() -> list[dict] | None:
    try:
        data = json.loads(APP_CACHE_PATH.read_text(encoding="utf-8"))
        if time.time() - float(data.get("time") or 0) < APP_CACHE_TTL:
            items = data.get("items")
            if isinstance(items, list) and items:
                return items
    except Exception:  # noqa: BLE001
        pass
    return None


def _save_app_cache(items: list[dict]) -> None:
    try:
        APP_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        APP_CACHE_PATH.write_text(
            json.dumps(
                {"time": time.time(), "items": items},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Не удалось сохранить кэш приложений: %s", exc)


def app_items(refresh: bool = False) -> list[dict]:
    global _app_items_cache
    now = time.time()
    if not refresh:
        if _app_items_cache and now - _app_items_cache[0] < APP_CACHE_TTL:
            return _app_items_cache[1]
        cached = _load_app_cache()
        if cached:
            _app_items_cache = (now, cached)
            return cached
    items: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for source in (
        _start_app_items(),
        _start_menu_items(),
        _registry_app_items(),
        _folder_app_items(),
    ):
        for item in source:
            key = (str(item.get("kind")), str(item.get("target")).lower())
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
    _app_items_cache = (now, items)
    _save_app_cache(items)
    log.info("Кэш приложений: %s штук", len(items))
    return items


def warm_app_cache() -> None:
    try:
        app_items()
    except Exception as exc:  # noqa: BLE001
        log.warning("Не удалось прогреть кэш приложений: %s", exc)


def resolve_app(query: str) -> dict | None:
    """Ищет установленное приложение по свободному названию."""
    raw = (query or "").strip()
    canonical = ALIASES.get(raw.lower(), raw)
    queries = [canonical] if canonical == raw else [canonical, raw]
    query_norm = normalize_app_name(canonical)
    if len(query_norm) < 2:
        return None
    scored: list[tuple[float, dict]] = []
    for item in app_items():
        name = str(item.get("name") or "")
        if not name:
            continue
        score = max(app_name_score(item_query, name) for item_query in queries)
        if score >= APP_MATCH_THRESHOLD:
            scored.append((score, item))
    if not scored:
        return None
    scored.sort(key=lambda pair: (-pair[0], pair[1].get("priority", 9)))
    best_score, best = scored[0]
    if len(scored) > 1 and scored[1][0] >= best_score - 0.02 and best_score < 0.95:
        log.info(
            "open_app: неоднозначно %r: %r (%.2f) или %r (%.2f)",
            query,
            best.get("name"),
            best_score,
            scored[1][1].get("name"),
            scored[1][0],
        )
    return {**best, "score": best_score}


def _launch_appid(appid: str) -> bool:
    if not appid:
        return False
    if appid.lower().startswith(("http://", "https://", "steam://", "microsoft.")):
        return open_target(appid)
    if re.match(r"^[A-Za-z]:[\\/]", appid) or appid.startswith("%"):
        path = _expand(appid)
        if not path.exists():
            return False
        if path.suffix.lower() == ".exe":
            return _launch(path)
        return open_target(str(path))
    try:
        subprocess.Popen(  # noqa: S603
            ["explorer.exe", f"shell:AppsFolder\\{appid}"],
            creationflags=CREATE_NO_WINDOW,
        )
        time.sleep(0.8)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Не удалось запустить AppID %s: %s", appid, exc)
        return False


def _launch_app_item(item: dict) -> bool:
    kind = str(item.get("kind") or "")
    target = str(item.get("target") or "")
    if kind == "appid":
        return _launch_appid(target)
    if kind == "path":
        path = _expand(target)
        if not path.exists():
            return False
        if path.suffix.lower() == ".exe":
            return _launch(path)
        return open_target(str(path))
    if kind == "shortcut":
        try:
            os.startfile(target)  # noqa: S606
            time.sleep(1.0)
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("Не удалось открыть ярлык %s: %s", target, exc)
            return False
    if kind == "url":
        return open_target(target)
    return False


def _find_running_process(query: str) -> str | None:
    query_norm = normalize_app_name(query)
    if len(query_norm) < 2:
        return None
    try:
        import psutil  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    scored: list[tuple[float, str]] = []
    seen: set[str] = set()
    try:
        for proc in psutil.process_iter(["name"]):
            name = str(proc.info.get("name") or "")
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            stem = normalize_app_name(Path(name).stem)
            if not stem:
                continue
            score = app_name_score(query, stem)
            if score >= 0.82:
                scored.append((score, name))
    except Exception:  # noqa: BLE001
        return None
    if not scored:
        return None
    scored.sort(reverse=True)
    return scored[0][1]


def open_target(target: str) -> bool:
    """Открывает путь, URL или ms-протокол."""
    if not target:
        return False
    if target.startswith(
        ("http://", "https://", "ms-", "microsoft.", "steam://")
    ):
        try:
            os.startfile(target)  # noqa: S606
            return True
        except Exception:
            return False
    path = _expand(target)
    if path.exists():
        return _launch(path)
    return False


BROWSER_KEYS = {"chrome", "msedge", "firefox", "opera", "yandex"}
BROWSER_PROCESSES = {
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "opera.exe",
    "browser.exe",
    "brave.exe",
    "vivaldi.exe",
}
BROWSER_PROCESS_BY_KEY = {
    "chrome": "chrome.exe",
    "msedge": "msedge.exe",
    "firefox": "firefox.exe",
    "opera": "opera.exe",
    "yandex": "browser.exe",
}


def open_url_in_browser(url: str, browser: str | None = None) -> str | None:
    """Открывает URL в текущей вкладке активного браузера."""
    if not url:
        return None
    key = (browser or "").lower().strip()
    key = ALIASES.get(key, key)
    if navigate_browser(url, key if key in BROWSER_KEYS else ""):
        return key or "default"
    if key in BROWSER_KEYS:
        for raw in KNOWN_PATHS.get(key, []):
            path = _expand(raw)
            if not path.exists():
                continue
            try:
                subprocess.Popen(  # noqa: S603
                    [str(path), url],
                    creationflags=CREATE_NO_WINDOW,
                )
                return key
            except Exception as exc:  # noqa: BLE001
                log.warning("Не удалось открыть %s в %s: %s", url, key, exc)
                break
    try:
        os.startfile(url)  # noqa: S606
        return "default"
    except Exception as exc:  # noqa: BLE001
        log.error("Не удалось открыть URL %s: %s", url, exc)
        return None


def _browser_window():
    try:
        import psutil  # noqa: PLC0415
        from pywinauto import Desktop  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    try:
        windows = Desktop(backend="uia").windows()
    except Exception:  # noqa: BLE001
        return None

    def is_browser(win) -> bool:
        try:
            if not win.is_visible():
                return False
            name = (psutil.Process(win.process_id()).name() or "").lower()
            return name in BROWSER_PROCESSES
        except Exception:  # noqa: BLE001
            return False

    # Активное окно браузера важнее: команда должна действовать там,
    # где пользователь сейчас работает.
    try:
        import win32gui  # noqa: PLC0415

        foreground = win32gui.GetForegroundWindow()
    except Exception:  # noqa: BLE001
        foreground = 0
    if foreground:
        for win in windows:
            try:
                if win.handle == foreground and is_browser(win):
                    return win
            except Exception:  # noqa: BLE001
                continue

    candidates = []
    for win in windows:
        if not is_browser(win):
            continue
        try:
            rect = win.rectangle()
            area = (rect.right - rect.left) * (rect.bottom - rect.top)
            candidates.append((area, win))
        except Exception:  # noqa: BLE001
            continue
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _focus_window(win) -> bool:
    try:
        win.set_focus()
        time.sleep(0.15)
        return True
    except Exception:  # noqa: BLE001
        pass
    try:
        import win32con  # noqa: PLC0415
        import win32gui  # noqa: PLC0415

        handle = win.handle
        win32gui.ShowWindow(handle, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(handle)
        time.sleep(0.15)
        return True
    except Exception:  # noqa: BLE001
        return False


def _browser_window_for(key: str = ""):
    """Окно нужного браузера: активное, иначе самое большое."""
    win = _browser_window()
    if win is None:
        return None
    wanted = BROWSER_PROCESS_BY_KEY.get((key or "").lower())
    if not wanted:
        return win
    try:
        import psutil  # noqa: PLC0415

        name = (psutil.Process(win.process_id()).name() or "").lower()
    except Exception:  # noqa: BLE001
        name = ""
    if name == wanted:
        return win
    try:
        import psutil  # noqa: PLC0415
        from pywinauto import Desktop  # noqa: PLC0415

        for candidate in Desktop(backend="uia").windows():
            try:
                if not candidate.is_visible():
                    continue
                candidate_name = (
                    psutil.Process(candidate.process_id()).name() or ""
                ).lower()
                if candidate_name == wanted:
                    return candidate
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    return None


def navigate_browser(url: str, browser: str = "") -> bool:
    """Открывает URL в текущей вкладке браузера, без нового окна."""
    win = _browser_window_for(browser)
    if win is None:
        return False
    if not _focus_window(win):
        return False
    try:
        from pywinauto.keyboard import send_keys  # noqa: PLC0415

        send_keys("^l")
        time.sleep(0.2)
        if not type_text(url):
            return False
        time.sleep(0.15)
        send_keys("{ENTER}")
        time.sleep(0.4)
        log.info("Браузер: открыл в текущей вкладке %s", url)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Не удалось открыть %s в текущей вкладке: %s", url, exc)
        return False


def browser_hotkey(keys: str) -> bool:
    """Отправляет горячую клавишу активному окну браузера."""
    win = _browser_window()
    if win is not None and _focus_window(win):
        try:
            from pywinauto.keyboard import send_keys  # noqa: PLC0415

            send_keys(keys)
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("Не удалось отправить %r браузеру: %s", keys, exc)
    return False


def new_browser_tab(browser: str | None = None) -> bool:
    """Открывает новую вкладку в активном браузере."""
    if browser:
        return open_url_in_browser("about:blank", browser) is not None
    if browser_hotkey("^t"):
        return True
    try:
        os.startfile("about:blank")  # noqa: S606
        return True
    except Exception:  # noqa: BLE001
        return False


def close_browser_tab() -> bool:
    """Закрывает текущую вкладку браузера."""
    return browser_hotkey("^w")


def next_browser_tab() -> bool:
    """Переключает на следующую вкладку."""
    return browser_hotkey("^{TAB}")


def previous_browser_tab() -> bool:
    """Переключает на предыдущую вкладку."""
    return browser_hotkey("^+{TAB}")


def reopen_browser_tab() -> bool:
    """Восстанавливает последнюю закрытую вкладку."""
    return browser_hotkey("^+t")


def switch_browser_tab(number: int) -> bool:
    """Переключает на вкладку по номеру (1–9)."""
    if not 1 <= number <= 9:
        return False
    return browser_hotkey(f"^{number}")


def send_hotkey(keys: str) -> bool:
    """Отправляет клавиши активному окну."""
    try:
        from pywinauto.keyboard import send_keys  # noqa: PLC0415

        send_keys(keys)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Не удалось отправить %r активному окну: %s", keys, exc)
        return False


def browser_refresh() -> bool:
    return browser_hotkey("{F5}")


def browser_back() -> bool:
    return browser_hotkey("%{LEFT}")


def browser_forward() -> bool:
    return browser_hotkey("%{RIGHT}")


def browser_zoom_in() -> bool:
    return browser_hotkey("^{ADD}")


def browser_zoom_out() -> bool:
    return browser_hotkey("^{SUBTRACT}")


def browser_zoom_reset() -> bool:
    return browser_hotkey("^0")


VIDEO_SITE_WORDS = ("youtube", "youtu.be", "rutube", "vk video", "vkvideo")
VIDEO_URL_MARKERS = (
    "youtube.com/watch",
    "youtube.com/shorts/",
    "youtu.be/",
    "rutube.ru/video",
    "vk.com/video",
    "vkvideo.ru/video",
)


def is_video_url(url: str) -> bool:
    low = (url or "").lower()
    return any(marker in low for marker in VIDEO_URL_MARKERS)


def browser_page_url() -> str:
    """Текущий адрес активной вкладки браузера через UIA."""
    win = _browser_window()
    if win is None:
        return ""
    try:
        for child in win.descendants(control_type="Edit"):
            try:
                text = (child.window_text() or "").strip()
            except Exception:  # noqa: BLE001
                continue
            if re.match(r"^https?://", text, re.IGNORECASE):
                return text
    except Exception:  # noqa: BLE001
        return ""
    return ""


def browser_available() -> bool:
    """Есть ли открытое окно браузера."""
    return _browser_window() is not None


def _page_link_controls(win, limit: int = 30) -> list[tuple[str, object]]:
    """Ссылки на странице активной вкладки в порядке сверху вниз.

    Сначала берутся ссылки внутри элементов списков — на страницах поиска
    это результаты, а не меню и шапка сайта. Если списков нет, остаются
    все видимые ссылки страницы.
    """
    try:
        roots = win.descendants(control_type="Document") or []
    except Exception:  # noqa: BLE001
        roots = []
    if not roots:
        roots = [win]

    def _visible(control) -> tuple[int, int] | None:
        try:
            rect = control.rectangle()
        except Exception:  # noqa: BLE001
            return None
        if rect.top < -300 or rect.right <= rect.left:
            return None
        return rect.top, rect.left

    def _name(control) -> str:
        try:
            return " ".join((control.window_text() or "").split())
        except Exception:  # noqa: BLE001
            return ""

    listed: list[tuple[int, int, str, object]] = []
    others: list[tuple[int, int, str, object]] = []
    for root in roots:
        try:
            items = root.descendants(control_type="ListItem")
        except Exception:  # noqa: BLE001
            items = []
        for item in items:
            place = _visible(item)
            if place is None:
                continue
            try:
                children = item.descendants(control_type="Hyperlink")
            except Exception:  # noqa: BLE001
                continue
            for child in children:
                name = _name(child)
                if name:
                    listed.append((place[0], place[1], name, child))
        try:
            children = root.descendants(control_type="Hyperlink")
        except Exception:  # noqa: BLE001
            continue
        for child in children:
            place = _visible(child)
            if place is None:
                continue
            name = _name(child)
            if name:
                others.append((place[0], place[1], name, child))

    ordered = listed or others
    ordered.sort(key=lambda entry: (entry[0], entry[1]))
    found: list[tuple[str, object]] = []
    seen: set[str] = set()
    for _top, _left, name, control in ordered:
        if name in seen:
            continue
        seen.add(name)
        found.append((name, control))
        if len(found) >= limit:
            break
    return found


def browser_link_titles(limit: int = 10) -> list[str]:
    """Названия первых ссылок на открытой странице."""
    win = _browser_window()
    if win is None:
        return []
    return [name for name, _ in _page_link_controls(win, limit)]


def browser_open_link(number: int) -> str:
    """Открывает ссылку № number на текущей странице. Возвращает её название."""
    if number < 1:
        return ""
    win = _browser_window()
    if win is None:
        return ""
    links = _page_link_controls(win, max(number, 20))
    if number > len(links):
        return ""
    name, control = links[number - 1]
    try:
        control.invoke()
        log.info("Браузер: открыл ссылку №%s «%s»", number, name)
        return name
    except Exception:  # noqa: BLE001
        pass
    try:
        control.click_input()
        log.info("Браузер: кликнул ссылку №%s «%s»", number, name)
        return name
    except Exception as exc:  # noqa: BLE001
        log.warning("Не удалось открыть ссылку №%s: %s", number, exc)
        return ""


def _is_video_page() -> bool:
    url = browser_page_url()
    if url:
        return is_video_url(url)
    win = _browser_window()
    if win is None:
        return False
    try:
        title = (win.window_text() or "").lower()
    except Exception:  # noqa: BLE001
        return False
    return any(word in title for word in VIDEO_SITE_WORDS)


def _window_covers_screen(win) -> bool:
    try:
        rect = win.rectangle()
        width = ctypes.windll.user32.GetSystemMetrics(0)
        height = ctypes.windll.user32.GetSystemMetrics(1)
        return (
            (rect.right - rect.left) >= width - 2
            and (rect.bottom - rect.top) >= height - 2
        )
    except Exception:  # noqa: BLE001
        return False


def browser_video_fullscreen() -> bool:
    """Полноэкранный режим самого видеоплеера (YouTube, Rutube)."""
    if not _is_video_page():
        return False
    return browser_hotkey("f")


def browser_fullscreen() -> bool:
    """На видео включает плеер, в остальных случаях — полный экран браузера."""
    if _is_video_page():
        return browser_hotkey("f")
    return browser_hotkey("{F11}")


def browser_exit_fullscreen() -> bool:
    """Выходит из полноэкранного видео, при необходимости — из F11."""
    win = _browser_window()
    if win is None:
        return False
    if _is_video_page():
        browser_hotkey("{ESC}")
        time.sleep(0.35)
        current = _browser_window()
        if current is not None and _window_covers_screen(current):
            return browser_hotkey("{F11}")
        return True
    return browser_hotkey("{F11}")


def browser_maximize() -> bool:
    """Разворачивает окно браузера на весь экран (без F11)."""
    win = _browser_window()
    if win is None:
        return False
    try:
        win.maximize()
        _focus_window(win)
        return True
    except Exception:  # noqa: BLE001
        try:
            import win32con  # noqa: PLC0415
            import win32gui  # noqa: PLC0415

            win32gui.ShowWindow(win.handle, win32con.SW_MAXIMIZE)
            return True
        except Exception:  # noqa: BLE001
            return False


def browser_home() -> bool:
    return browser_hotkey("%{HOME}")


def browser_new_window() -> bool:
    return browser_hotkey("^n")


def browser_private() -> bool:
    """Открывает приватное окно в активном браузере."""
    win = _browser_window()
    name = ""
    if win is not None:
        try:
            import psutil  # noqa: PLC0415

            name = (psutil.Process(win.process_id()).name() or "").lower()
        except Exception:  # noqa: BLE001
            name = ""
    return browser_hotkey("^+p" if "firefox" in name else "^+n")


def browser_find(query: str) -> bool:
    """Открывает поиск по странице и вводит запрос."""
    query = (query or "").strip()
    if not query:
        return False
    if not browser_hotkey("^f"):
        return False
    time.sleep(0.25)
    if not type_text(query):
        return False
    time.sleep(0.2)
    return send_hotkey("{ENTER}")


def browser_scroll(direction: str) -> bool:
    if direction in {"вниз", "ниже", "down"}:
        return browser_hotkey("{PGDN}")
    if direction in {"вверх", "выше", "up"}:
        return browser_hotkey("{PGUP}")
    return False


def browser_scroll_top() -> bool:
    return browser_hotkey("^{HOME}")


def browser_scroll_bottom() -> bool:
    return browser_hotkey("^{END}")


def browser_seek(seconds: int) -> bool:
    """Перематывает видео на YouTube стрелками (шаг 5 секунд)."""
    win = _browser_window()
    if win is None:
        return False
    try:
        title = win.window_text().lower()
    except Exception:  # noqa: BLE001
        return False
    if "youtube" not in title:
        return False
    key = "{RIGHT}" if seconds >= 0 else "{LEFT}"
    steps = max(1, round(abs(seconds) / 5))
    for _ in range(steps):
        if not browser_hotkey(key):
            return False
        time.sleep(0.1)
    return True


def browser_video_toggle() -> bool:
    """Ставит видео на паузу или продолжает его на YouTube."""
    win = _browser_window()
    if win is None:
        return False
    try:
        if "youtube" not in win.window_text().lower():
            return False
    except Exception:  # noqa: BLE001
        return False
    return browser_hotkey("k")


def browser_video_next() -> bool:
    return browser_hotkey("+n")


def browser_video_previous() -> bool:
    return browser_hotkey("+p")


def copy_text(text: str) -> bool:
    """Копирует текст в буфер обмена Windows."""
    if text is None:
        return False
    try:
        import win32clipboard  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return False
    for _ in range(3):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(
                    text, win32clipboard.CF_UNICODETEXT
                )
            finally:
                win32clipboard.CloseClipboard()
            return True
        except Exception:  # noqa: BLE001
            time.sleep(0.1)
    return False


def get_clipboard_text() -> str | None:
    """Читает текст из буфера обмена. None — не удалось прочитать."""
    try:
        import win32clipboard  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    for _ in range(3):
        try:
            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(
                    win32clipboard.CF_UNICODETEXT
                ):
                    return str(
                        win32clipboard.GetClipboardData(
                            win32clipboard.CF_UNICODETEXT
                        )
                    )
                return ""
            finally:
                win32clipboard.CloseClipboard()
        except Exception:  # noqa: BLE001
            time.sleep(0.1)
    return None


def type_text(text: str) -> bool:
    """Печатает текст в активном окне через буфер обмена (поддерживает кириллицу)."""
    text = text or ""
    if not text:
        return False
    old = get_clipboard_text()
    if not copy_text(text):
        return False
    ok = send_hotkey("^v")
    if old is not None:
        def _restore() -> None:
            time.sleep(1.0)
            copy_text(old)

        threading.Thread(target=_restore, daemon=True).start()
    return ok


# --- окна ---------------------------------------------------------------
VK_LWIN = 0x5B
VK_ALT = 0x12
VK_TAB = 0x09
VK_F4 = 0x73
VK_UP = 0x26
VK_DOWN = 0x28
VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_D = 0x44


def _combo(*vks: int) -> None:
    for vk in vks:
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    for vk in reversed(vks):
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)


def show_desktop() -> bool:
    _combo(VK_LWIN, VK_D)
    return True


def switch_window() -> bool:
    _combo(VK_ALT, VK_TAB)
    return True


def close_active_window() -> bool:
    _combo(VK_ALT, VK_F4)
    return True


def maximize_active_window() -> bool:
    _combo(VK_LWIN, VK_UP)
    return True


def minimize_active_window() -> bool:
    _combo(VK_LWIN, VK_DOWN)
    return True


def snap_window_left() -> bool:
    _combo(VK_LWIN, VK_LEFT)
    return True


def snap_window_right() -> bool:
    _combo(VK_LWIN, VK_RIGHT)
    return True


def _visible_windows() -> list[tuple[int, str]]:
    try:
        import win32gui  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return []
    items: list[tuple[int, str]] = []

    def callback(hwnd, _extra) -> bool:
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            if win32gui.GetWindowTextLength(hwnd) == 0:
                return True
            title = win32gui.GetWindowText(hwnd).strip()
            if not title:
                return True
            items.append((int(hwnd), title))
        except Exception:  # noqa: BLE001
            pass
        return True

    try:
        win32gui.EnumWindows(callback, None)
    except Exception:  # noqa: BLE001
        return []
    skip = {
        "program manager",
        "windows input experience",
        "microsoft text input application",
        "default ime",
    }
    return [(hwnd, title) for hwnd, title in items if title.lower() not in skip]


def active_window() -> dict | None:
    try:
        import psutil  # noqa: PLC0415
        import win32gui  # noqa: PLC0415
        import win32process  # noqa: PLC0415

        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None
        title = win32gui.GetWindowText(hwnd).strip()
        if not title:
            return None
        _thread, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            name = psutil.Process(pid).name()
        except Exception:  # noqa: BLE001
            name = ""
        return {"handle": hwnd, "title": title, "pid": pid, "process": name}
    except Exception:  # noqa: BLE001
        return None


def list_windows(limit: int = 10) -> list[str]:
    """Заголовки видимых окон, без дублей."""
    own = os.getpid()
    try:
        import psutil  # noqa: PLC0415
        import win32process  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        psutil = None  # type: ignore[assignment]
        win32process = None  # type: ignore[assignment]

    result: list[str] = []
    seen: set[str] = set()
    for hwnd, title in _visible_windows():
        if title in seen:
            continue
        if psutil is not None and win32process is not None:
            try:
                _thread, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid == own:
                    continue
            except Exception:  # noqa: BLE001
                pass
        seen.add(title)
        result.append(title)
        if len(result) >= limit:
            break
    return result


def _find_window(query: str) -> tuple[int, str] | None:
    query = (query or "").lower().strip()
    if not query:
        return None
    best: tuple[int, str] | None = None
    best_score = 99
    for hwnd, title in _visible_windows():
        low = title.lower()
        if query not in low:
            continue
        if low == query:
            score = 0
        elif low.startswith(query):
            score = 1
        else:
            score = 2
        if score < best_score:
            best_score = score
            best = (hwnd, title)
            if score == 0:
                break
    return best


def _force_foreground(hwnd: int) -> bool:
    try:
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        if user32.GetForegroundWindow() == hwnd:
            return True
        foreground = user32.GetForegroundWindow()
        fg_thread = user32.GetWindowThreadProcessId(foreground, None)
        own_thread = ctypes.windll.kernel32.GetCurrentThreadId()
        attached = bool(user32.AttachThreadInput(own_thread, fg_thread, True))
        try:
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(own_thread, fg_thread, False)
        time.sleep(0.2)
        return user32.GetForegroundWindow() == hwnd
    except Exception:  # noqa: BLE001
        return False


def focus_process_window(exe_name: str) -> str | None:
    """Переключается на окно уже запущенного процесса."""
    target = Path(exe_name).stem.lower()
    try:
        import psutil  # noqa: PLC0415
        import win32process  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    for hwnd, title in _visible_windows():
        try:
            _thread, pid = win32process.GetWindowThreadProcessId(hwnd)
            name = (psutil.Process(pid).name() or "").lower()
        except Exception:  # noqa: BLE001
            continue
        if Path(name).stem.lower() == target:
            if _force_foreground(hwnd):
                return title
    return None


def focus_window_by_title(query: str) -> str | None:
    found = _find_window(query)
    if not found:
        return None
    hwnd, title = found
    if _force_foreground(hwnd):
        return title
    return None


def close_window_by_title(query: str) -> str | None:
    found = _find_window(query)
    if not found:
        return None
    hwnd, title = found
    try:
        import win32con  # noqa: PLC0415
        import win32gui  # noqa: PLC0415

        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        return title
    except Exception:  # noqa: BLE001
        return None


# --- папки и система ----------------------------------------------------
FOLDER_ALIASES = {
    "загрузки": Path.home() / "Downloads",
    "загрузка": Path.home() / "Downloads",
    "загрузок": Path.home() / "Downloads",
    "downloads": Path.home() / "Downloads",
    "документы": Path.home() / "Documents",
    "документ": Path.home() / "Documents",
    "документов": Path.home() / "Documents",
    "documents": Path.home() / "Documents",
    "рабочий стол": Path.home() / "Desktop",
    "рабочего стола": Path.home() / "Desktop",
    "desktop": Path.home() / "Desktop",
    "картинки": Path.home() / "Pictures",
    "картинок": Path.home() / "Pictures",
    "изображения": Path.home() / "Pictures",
    "фото": Path.home() / "Pictures",
    "pictures": Path.home() / "Pictures",
    "видео": Path.home() / "Videos",
    "видеофайлы": Path.home() / "Videos",
    "videos": Path.home() / "Videos",
    "музыка": Path.home() / "Music",
    "музыку": Path.home() / "Music",
    "музыки": Path.home() / "Music",
    "music": Path.home() / "Music",
    "домашняя папка": Path.home(),
    "домашнюю папку": Path.home(),
    "домашней папки": Path.home(),
    "профиль": Path.home(),
    "home": Path.home(),
}

SHELL_FOLDERS = {
    "корзина": "shell:RecycleBinFolder",
    "корзину": "shell:RecycleBinFolder",
    "recycle bin": "shell:RecycleBinFolder",
    "этот компьютер": "shell:MyComputerFolder",
    "мой компьютер": "shell:MyComputerFolder",
    "this pc": "shell:MyComputerFolder",
    "сеть": "shell:NetworkPlacesFolder",
    "network": "shell:NetworkPlacesFolder",
}


def resolve_folder(name: str) -> str | None:
    raw = (name or "").strip()
    if not raw:
        return None
    key = re.sub(r"\s+", " ", raw.lower())
    key = re.sub(r"^(?:папку|папка|папки)\s+", "", key)
    if key in FOLDER_ALIASES:
        return str(FOLDER_ALIASES[key])
    if key in SHELL_FOLDERS:
        return SHELL_FOLDERS[key]
    path = Path(os.path.expandvars(os.path.expanduser(raw)))
    if path.exists() and path.is_dir():
        return str(path)
    # Поиск папки по имени в профиле пользователя.
    try:
        home = Path.home()
        matches = [
            item
            for item in home.iterdir()
            if item.is_dir() and key in item.name.lower()
        ]
        if matches:
            matches.sort(key=lambda item: len(item.name))
            return str(matches[0])
    except Exception:  # noqa: BLE001
        pass
    return None


def open_folder(name: str) -> str | None:
    target = resolve_folder(name)
    if not target:
        return None
    try:
        os.startfile(target)  # noqa: S606
        return target
    except Exception:  # noqa: BLE001
        try:
            subprocess.Popen(  # noqa: S603
                ["explorer.exe", target], creationflags=CREATE_NO_WINDOW
            )
            return target
        except Exception:
            return None


def create_folder(name: str, parent: str = "desktop") -> tuple[str, bool] | None:
    """Создаёт папку. Возвращает (путь, создана_ли_сейчас)."""
    name = (name or "").strip().strip('"')
    if not name:
        return None
    bases = {
        "desktop": Path.home() / "Desktop",
        "documents": Path.home() / "Documents",
        "downloads": Path.home() / "Downloads",
        "home": Path.home(),
    }
    base = bases.get(parent, bases["desktop"])
    target = Path(os.path.expandvars(os.path.expanduser(name)))
    if not target.is_absolute():
        target = base / name
    existed = target.exists()
    try:
        target.mkdir(parents=True, exist_ok=True)
        return str(target), not existed
    except Exception:  # noqa: BLE001
        return None


def latest_downloads(limit: int = 5) -> list[Path]:
    folder = Path.home() / "Downloads"
    if not folder.exists():
        return []
    try:
        items = [item for item in folder.iterdir() if not item.name.startswith(".")]
        items.sort(key=lambda item: item.stat().st_mtime, reverse=True)
        return items[:limit]
    except Exception:  # noqa: BLE001
        return []


def open_latest_download() -> str | None:
    items = latest_downloads(1)
    if not items:
        return None
    target = items[0]
    try:
        os.startfile(str(target))  # noqa: S606
        return str(target)
    except Exception:  # noqa: BLE001
        return None


def top_processes(limit: int = 5) -> list[tuple[str, int]]:
    """Самые прожорливые по памяти процессы: (имя, мегабайты)."""
    try:
        import psutil  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return []
    items: list[tuple[str, int]] = []
    for proc in psutil.process_iter(["name", "memory_info"]):
        try:
            info = proc.info
            mem = info.get("memory_info")
            if mem is None:
                continue
            items.append((info.get("name") or "?", int(mem.rss / 1024**2)))
        except Exception:  # noqa: BLE001
            continue
    items.sort(key=lambda item: item[1], reverse=True)
    return items[:limit]


def local_ip() -> str | None:
    """Локальный IP, по возможности без VPN и виртуальных адаптеров."""
    try:
        import psutil  # noqa: PLC0415

        stats = psutil.net_if_stats()
        skip_words = (
            "vpn", "happ", "xray", "outline", "tap", "tun", "virtual",
            "vmware", "hyper", "vethernet", "bluetooth", "loopback",
            "wireguard", "wintun", "radmin",
        )
        candidates: list[str] = []
        for name, addrs in psutil.net_if_addrs().items():
            stat = stats.get(name)
            if stat is None or not stat.isup:
                continue
            low = name.lower()
            if any(word in low for word in skip_words):
                continue
            for addr in addrs:
                if addr.family != socket.AF_INET:
                    continue
                ip = (addr.address or "").strip()
                if not ip or ip.startswith(("127.", "169.254.")):
                    continue
                candidates.append(ip)

        def score(ip: str) -> int:
            if ip.startswith("192.168."):
                return 0
            if ip.startswith("10."):
                return 1
            if ip.startswith("172."):
                return 2
            return 3

        if candidates:
            candidates.sort(key=score)
            return candidates[0]
    except Exception:  # noqa: BLE001
        pass
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        finally:
            sock.close()
    except Exception:  # noqa: BLE001
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return None


def internet_available() -> bool:
    for host, port in (("1.1.1.1", 443), ("8.8.8.8", 53)):
        try:
            sock = socket.create_connection((host, port), timeout=2.5)
            sock.close()
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def monitor_off() -> bool:
    try:
        ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
        return True
    except Exception:  # noqa: BLE001
        return False


def sleep_pc() -> bool:
    try:
        ctypes.windll.powrprof.SetSuspendState(0, 1, 0)
        return True
    except Exception:  # noqa: BLE001
        return False


def _powershell(script: str) -> str:
    try:
        result = subprocess.run(  # noqa: S603
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            errors="ignore",
            timeout=12,
            creationflags=CREATE_NO_WINDOW,
        )
        return (result.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def get_brightness() -> int | None:
    out = _powershell(
        "(Get-CimInstance -Namespace root/WMI -ClassName "
        "WmiMonitorBrightness).CurrentBrightness"
    )
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            return max(0, min(100, int(line)))
    return None


def set_brightness(percent: int) -> bool:
    percent = max(0, min(100, int(percent)))
    out = _powershell(
        "$m = Get-CimInstance -Namespace root/WMI -ClassName "
        "WmiMonitorBrightnessMethods; "
        f"$m | ForEach-Object {{ $_.WmiSetBrightness(1, {percent}) }}; "
        "'ok'"
    )
    return "ok" in out.lower()


def change_brightness(delta: int) -> int | None:
    current = get_brightness()
    if current is None:
        return None
    target = max(0, min(100, current + int(delta)))
    return target if set_brightness(target) else None


def disk_info() -> dict:
    import psutil  # noqa: PLC0415

    drive = os.environ.get("SystemDrive", "C:") + "\\"
    usage = psutil.disk_usage(drive)
    return {
        "drive": drive,
        "total": usage.total / (1024**3),
        "free": usage.free / (1024**3),
        "percent": usage.percent,
    }


def system_details() -> dict:
    return {
        "hostname": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
        "version": platform.version(),
    }


def open_app(name: str) -> str | None:
    """Открывает программу по русскому/английскому названию. None — не удалось."""
    key = (name or "").lower().strip()
    if not key:
        return None

    canonical = ALIASES.get(key, key)

    # 1) браузер по умолчанию
    if canonical == "browser":
        for candidate in ("chrome", "msedge", "firefox", "opera", "yandex"):
            if open_app(candidate):
                return candidate
        try:
            os.startfile("https://ya.ru")  # noqa: S606
            return "браузер"
        except Exception:
            return None

    # 2) ms-протоколы
    if canonical in PROTOCOLS:
        try:
            os.startfile(PROTOCOLS[canonical])  # noqa: S606
            return name
        except Exception:
            return None

    # 3) известные пути (включая wildcard для Discord)
    for raw in KNOWN_PATHS.get(canonical, []):
        if "*" in raw:
            import glob  # noqa: PLC0415

            matches = sorted(glob.glob(os.path.expandvars(raw)), reverse=True)
            for match in matches:
                if _launch(Path(match)):
                    return canonical
            continue
        path = _expand(raw)
        if path.exists() and _launch(path):
            return canonical

    # 4) ярлык в меню Пуск
    shortcut = find_shortcut(canonical) or find_shortcut(key)
    if shortcut:
        try:
            os.startfile(shortcut)  # noqa: S606
            time.sleep(1.2)
            return canonical
        except Exception:
            pass

    # 5) программа в PATH
    found = shutil.which(key) or shutil.which(f"{key}.exe") or shutil.which(canonical)
    if found:
        if _launch(Path(found)):
            return canonical

    # 6) гибкий поиск среди установленных приложений
    resolved = resolve_app(canonical) or resolve_app(name)
    if resolved:
        display_name = str(resolved.get("name") or name)
        log.info(
            "open_app: %r -> %r (%s, %s, %.2f)",
            name,
            display_name,
            resolved.get("source"),
            resolved.get("kind"),
            resolved.get("score", 0),
        )
        if _launch_app_item(resolved):
            return display_name
        log.warning("open_app: найден %r, но запустить не удалось", display_name)

    return None


def close_app(name: str) -> bool:
    key = (name or "").lower().strip()
    canonical = ALIASES.get(key, key)
    proc = EXE_ESCAPE.get(canonical, canonical).replace(".exe", "")
    if not proc:
        return False
    result = subprocess.run(  # noqa: S603
        ["taskkill", "/IM", f"{proc}.exe", "/F"],
        capture_output=True,
        creationflags=CREATE_NO_WINDOW,
        text=True,
        errors="ignore",
    )
    if result.returncode == 0:
        return True
    fuzzy = _find_running_process(name)
    if fuzzy and fuzzy.lower() != f"{proc}.exe".lower():
        log.info("close_app: %r -> процесс %r", name, fuzzy)
        result = subprocess.run(  # noqa: S603
            ["taskkill", "/IM", fuzzy, "/F"],
            capture_output=True,
            creationflags=CREATE_NO_WINDOW,
            text=True,
            errors="ignore",
        )
        return result.returncode == 0
    return False


# ----------------------------------------------------------------------
def press_key(vk: int, times: int = 1) -> None:
    for _ in range(max(1, times)):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
        time.sleep(0.03)


def set_volume_percent(percent: int) -> bool:
    """Абсолютная громкость через pycaw, если он установлен."""
    percent = max(0, min(100, percent))
    try:
        from pycaw.pycaw import AudioUtilities  # noqa: PLC0415

        device = AudioUtilities.GetSpeakers()
        if hasattr(device, "volume_percent"):
            device.volume_percent = percent
            return True
        if hasattr(device, "volume"):
            device.volume = percent
            return True
        # старый API pycaw
        from ctypes import POINTER, cast  # noqa: PLC0415

        from comtypes import CLSCTX_ALL  # noqa: PLC0415
        from pycaw.pycaw import IAudioEndpointVolume  # noqa: PLC0415

        interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMasterVolumeLevelScalar(percent / 100.0, None)
        return True
    except Exception:
        return False


def mute_toggle() -> None:
    press_key(VK["mute"])


def lock_pc() -> None:
    ctypes.windll.user32.LockWorkStation()


def shutdown(delay: int = 15, restart: bool = False) -> None:
    flag = "/r" if restart else "/s"
    subprocess.run(  # noqa: S603
        ["shutdown", flag, "/t", str(delay)],
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )


def cancel_shutdown() -> None:
    subprocess.run(  # noqa: S603
        ["shutdown", "/a"], creationflags=CREATE_NO_WINDOW, check=False
    )


def screenshot() -> str:
    from PIL import ImageGrab  # noqa: PLC0415

    folder = Path.home() / "Pictures" / "Jarvis"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"screenshot_{datetime.now():%Y%m%d_%H%M%S}.png"
    ImageGrab.grab(all_screens=True).save(path)
    return str(path)


def battery_status() -> dict | None:
    try:
        import psutil  # noqa: PLC0415

        bat = psutil.sensors_battery()
        if bat is None:
            return None
        return {"percent": round(bat.percent), "plugged": bat.power_plugged}
    except Exception:
        return None


def system_info() -> dict:
    import psutil  # noqa: PLC0415

    return {
        "cpu": psutil.cpu_percent(interval=0.6),
        "ram": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage("C:\\").free / (1024**3),
    }


# --- время в часовых поясах, настройки, поиск файлов -------------------
def time_in_timezone(zone_id: str) -> tuple[int, int, date] | None:
    """Местное время в часовом поясе Windows: (часы, минуты, дата)."""
    zone = (zone_id or "").replace("'", "")
    if not zone:
        return None
    script = (
        "$tz=[System.TimeZoneInfo]::FindSystemTimeZoneById('" + zone + "'); "
        "$now=[System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId("
        "[DateTimeOffset]::UtcNow, $tz.Id); "
        "$now.ToString('HH:mm|yyyy-MM-dd')"
    )
    out = _powershell(script)
    for line in out.splitlines():
        line = line.strip()
        if re.fullmatch(r"\d{2}:\d{2}\|\d{4}-\d{2}-\d{2}", line):
            clock, day = line.split("|", 1)
            try:
                return (
                    int(clock[:2]),
                    int(clock[3:]),
                    datetime.strptime(day, "%Y-%m-%d").date(),
                )
            except ValueError:
                return None
    return None


def open_windows_settings(uri: str) -> bool:
    """Открывает страницу «Параметров Windows» по ms-settings-URI."""
    target = (uri or "").strip()
    if not target.startswith("ms-settings:"):
        return False
    try:
        os.startfile(target)  # noqa: S606
        return True
    except Exception:  # noqa: BLE001
        return False


FILE_SEARCH_FOLDERS = (
    "Desktop",
    "Documents",
    "Downloads",
    "Pictures",
    "Music",
    "Videos",
)
FILE_SEARCH_MAX_DEPTH = 4
FILE_SEARCH_MAX_FILES = 20_000
FILE_SEARCH_MAX_SECONDS = 2.5


def _file_tokens(text: str) -> list[str]:
    text = (text or "").lower().replace("ё", "е")
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return [token for token in text.split() if len(token) >= 2]


def _file_score(query_tokens: list[str], name: str) -> float:
    norm = " ".join(_file_tokens(name))
    if not norm:
        return 0.0
    if all(token in norm for token in query_tokens):
        return 10.0 + sum(len(token) for token in query_tokens) / 100.0
    hits = sum(1 for token in query_tokens if token in norm)
    if hits:
        return hits + sum(
            len(token) for token in query_tokens if token in norm
        ) / 100.0
    joined = " ".join(query_tokens)
    return difflib.SequenceMatcher(None, joined, norm).ratio()


def find_files(query: str, folder: str | None = None, limit: int = 5) -> list[Path]:
    """Ищет файлы по имени в личных папках пользователя."""
    tokens = _file_tokens(query)
    if not tokens:
        return []
    if folder:
        base_paths = [Path(os.path.expandvars(os.path.expanduser(folder)))]
    else:
        home = Path.home()
        base_paths = [home / name for name in FILE_SEARCH_FOLDERS]

    started = time.monotonic()
    seen = 0
    scored: list[tuple[float, float, Path]] = []
    for base in base_paths:
        if not base.exists():
            continue
        stack: list[tuple[Path, int]] = [(base, 0)]
        while stack:
            current, depth = stack.pop()
            if depth > FILE_SEARCH_MAX_DEPTH:
                continue
            try:
                entries = list(os.scandir(current))
            except Exception:  # noqa: BLE001
                continue
            for entry in entries:
                if entry.name.startswith((".", "~$")):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append((Path(entry.path), depth + 1))
                        continue
                except OSError:
                    continue
                seen += 1
                if seen > FILE_SEARCH_MAX_FILES:
                    break
                score = _file_score(tokens, entry.name)
                if score >= 0.8:
                    try:
                        mtime = entry.stat(follow_symlinks=False).st_mtime
                    except OSError:
                        mtime = 0.0
                    scored.append((score, mtime, Path(entry.path)))
            if (
                seen > FILE_SEARCH_MAX_FILES
                or time.monotonic() - started > FILE_SEARCH_MAX_SECONDS
            ):
                break
        if (
            seen > FILE_SEARCH_MAX_FILES
            or time.monotonic() - started > FILE_SEARCH_MAX_SECONDS
        ):
            break
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [path for _score, _mtime, path in scored[:limit]]


def open_file(path: str | Path) -> bool:
    """Открывает файл программой по умолчанию."""
    target = Path(path)
    if not target.exists():
        return False
    try:
        os.startfile(str(target))  # noqa: S606
        return True
    except Exception:  # noqa: BLE001
        return False
