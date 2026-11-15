"""Microsoft Word через COM: документы, текст, заголовки, таблицы, PDF.

Модуль не требует установленного python-docx: работает с настоящим Word,
поэтому подходит и для сложных шаблонов. Если Word не установлен, все функции
возвращают None/False, а Jarvis честно говорит об этом.
"""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime
from pathlib import Path

WD_ALERTS_NONE = 0
WD_SAVE_CHANGES = -1
WD_DO_NOT_SAVE = 0
WD_STAT_WORDS = 0
WD_STAT_PAGES = 2
WD_FORMAT_PDF = 17
WD_REPLACE_ALL = 2
WD_HEADING_STYLES = {1: -2, 2: -3, 3: -4}


class WordError(RuntimeError):
    """Ошибка работы с Word (нет программы, занят документ и т.п.)."""


_lock = threading.Lock()
_apps: dict[int, object] = {}


# ----------------------------------------------------------------------
def available() -> bool:
    """True, если Word установлен и с ним можно работать через COM."""
    try:
        import win32com.client  # noqa: F401, PLC0415
    except Exception:  # noqa: BLE001
        return False
    return _word_exe() is not None or _registered()


def _registered() -> bool:
    try:
        import winreg  # noqa: PLC0415

        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for flag in (0, winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
                try:
                    key = winreg.OpenKey(
                        root,
                        r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\winword.exe",
                        0,
                        winreg.KEY_READ | flag,
                    )
                except OSError:
                    continue
                try:
                    winreg.QueryValueEx(key, "")
                    return True
                except OSError:
                    continue
                finally:
                    winreg.CloseKey(key)
    except Exception:  # noqa: BLE001
        pass
    return False


def _word_exe() -> Path | None:
    candidates = (
        r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE",
        r"C:\Program Files\Microsoft Office\Office16\WINWORD.EXE",
        r"C:\Program Files (x86)\Microsoft Office\Office16\WINWORD.EXE",
        r"C:\Program Files\Microsoft Office\Office15\WINWORD.EXE",
    )
    for raw in candidates:
        path = Path(raw)
        if path.is_file():
            return path
    try:
        import winreg  # noqa: PLC0415

        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for flag in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY, 0):
                try:
                    key = winreg.OpenKey(
                        root,
                        r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\winword.exe",
                        0,
                        winreg.KEY_READ | flag,
                    )
                except OSError:
                    continue
                try:
                    value = str(winreg.QueryValueEx(key, "")[0]).strip('"')
                except OSError:
                    continue
                finally:
                    winreg.CloseKey(key)
                path = Path(value)
                # WPS Office регистрирует свой wps.exe под тем же ключом.
                if path.is_file() and path.name.lower() == "winword.exe":
                    return path
    except Exception:  # noqa: BLE001
        pass
    return None


def _provider(app) -> str:
    """Имя COM-сервера: 'Microsoft Word', 'WPS Office' или пустая строка."""
    try:
        return str(app.Name or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _is_real_word(app) -> bool:
    return "microsoft word" in _provider(app).lower()


def _launch_word(exe: Path) -> None:
    """Запускает Microsoft Word в режиме автоматизации (не WPS)."""
    import subprocess  # noqa: PLC0415

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(  # noqa: S603
        [str(exe), "/Automation"],
        close_fds=True,
        creationflags=flags,
    )


def _app(visible: bool = True, launch: bool = True):
    """Возвращает Word.Application для текущего потока (COM-апартамента).

    Сначала ищет уже запущенный Microsoft Word. Ключ Word.Application в
    реестре может быть перехвачен WPS Office, поэтому при необходимости
    Word запускается напрямую через WINWORD.EXE /Automation.
    launch=False — только подключиться к уже открытому Word.
    """
    try:
        import pythoncom  # noqa: PLC0415
        import win32com.client  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        raise WordError("pywin32 не установлен") from exc

    pythoncom.CoInitialize()
    key = threading.get_ident()
    with _lock:
        app = _apps.get(key)
        # Кэш мог устареть: пользователь закрыл Word вручную.
        if app is not None and not _is_real_word(app):
            _apps.pop(key, None)
            app = None
        if app is None:
            app = _attach_app(win32com.client, visible, launch)
            _apps[key] = app
    try:
        if visible:
            app.Visible = True
    except Exception:  # noqa: BLE001
        pass
    try:
        app.DisplayAlerts = WD_ALERTS_NONE
    except Exception:  # noqa: BLE001
        pass
    return app


def _attached_app():
    """Только уже запущенный Word; None, если его нет."""
    try:
        return _app(False, launch=False)
    except WordError:
        return None


def _quit_if_idle(app) -> None:
    """Закрывает невидимый Word, если в нём не осталось документов."""
    if app is None:
        return
    try:
        if int(app.Documents.Count) == 0 and not bool(app.Visible):
            app.Quit(WD_DO_NOT_SAVE)
            _apps.pop(threading.get_ident(), None)
    except Exception:  # noqa: BLE001
        pass


def _attach_app(win32com_client, visible: bool, launch: bool = True):
    # 1) уже запущенный Word
    try:
        app = win32com_client.GetActiveObject("Word.Application")
        if _is_real_word(app):
            return app
    except Exception:  # noqa: BLE001
        pass

    if not launch:
        raise WordError("Microsoft Word не запущен")

    # 2) запускаем Microsoft Word напрямую и подключаемся к нему
    exe = _word_exe()
    if exe is not None:
        _launch_word(exe)
        for _ in range(40):  # до ~20 секунд
            time.sleep(0.5)
            try:
                app = win32com_client.GetActiveObject("Word.Application")
            except Exception:  # noqa: BLE001
                continue
            if _is_real_word(app):
                return app
        # Word мог подняться, но не отдать ROT — пробуем Dispatch
        try:
            app = win32com_client.Dispatch("Word.Application")
            if _is_real_word(app):
                return app
        except Exception as exc:  # noqa: BLE001
            raise WordError(f"Microsoft Word не запускается: {exc}") from exc

    # 3) запасной вариант — любой COM-сервер Word.Application (например WPS)
    try:
        return win32com_client.Dispatch("Word.Application")
    except Exception as exc:  # noqa: BLE001
        raise WordError(f"Word не запускается: {exc}") from exc


def _active_document(app):
    try:
        if int(app.Documents.Count) > 0:
            return app.ActiveDocument
    except Exception:  # noqa: BLE001
        pass
    return None


def _document_name(doc) -> str:
    try:
        name = str(doc.Name)
    except Exception:  # noqa: BLE001
        return "Документ"
    return name.rsplit(".", 1)[0] if name else "Документ"


def _append(doc, text: str) -> None:
    payload = (text or "").strip()
    if not payload:
        return
    end = int(doc.Content.End) - 1
    rng = doc.Range(end, end)
    rng.InsertAfter(payload + "\r")


def _documents_dir() -> Path:
    folder = Path.home() / "Documents"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _default_path(stem: str, suffix: str = ".docx") -> Path:
    folder = _documents_dir()
    safe = "".join(ch for ch in stem if ch not in '\\/:*?"<>|').strip() or "Хряк"
    stamp = datetime.now().strftime("%d.%m %H-%M")
    path = folder / f"{safe} {stamp}{suffix}"
    counter = 2
    while path.exists():
        path = folder / f"{safe} {stamp} ({counter}){suffix}"
        counter += 1
    return path


def _resolve_document(name: str) -> Path | None:
    """Ищет документ по имени: путь, имя с расширением или часть названия."""
    raw = (name or "").strip().strip('"').strip()
    if not raw:
        return None
    direct = Path(raw)
    if direct.is_file():
        return direct
    folder = _documents_dir()
    for suffix in ("", ".docx", ".doc", ".rtf"):
        candidate = folder / f"{raw}{suffix}"
        if candidate.is_file():
            return candidate
    query = raw.lower()
    try:
        matches = [
            item
            for item in folder.glob("*.doc*")
            if query in item.stem.lower()
        ]
    except OSError:
        return None
    if not matches:
        return None
    matches.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return matches[0]


# ----------------------------------------------------------------------
def new_document(text: str = "") -> str:
    """Создаёт документ Word и при необходимости пишет в него текст."""
    app = _app(True)
    doc = app.Documents.Add()
    if (text or "").strip():
        _append(doc, text)
    return _document_name(doc)


def open_document(name: str) -> str | None:
    """Открывает существующий документ. None — не найден."""
    path = _resolve_document(name)
    if path is None:
        return None
    app = _app(True)
    doc = app.Documents.Open(str(path))
    try:
        app.Activate()
        doc.Activate()
    except Exception:  # noqa: BLE001
        pass
    return _document_name(doc)


def append_text(text: str) -> str | None:
    """Добавляет текст в конец активного документа (или создаёт новый)."""
    app = _app(True)
    doc = _active_document(app) or app.Documents.Add()
    _append(doc, text)
    return _document_name(doc)


def read_document(name: str = "", limit: int = 2000) -> str | None:
    """Читает текст документа. Без имени — активный документ."""
    if (name or "").strip():
        path = _resolve_document(name)
        if path is None:
            return None
        app = _app(False)
        doc = app.Documents.Open(str(path), ReadOnly=True, AddToRecentFiles=False)
        try:
            text = str(doc.Content.Text)
        finally:
            doc.Close(WD_DO_NOT_SAVE)
        _quit_if_idle(app)
    else:
        app = _attached_app()
        doc = _active_document(app) if app is not None else None
        if doc is None:
            return None
        text = str(doc.Content.Text)
    text = text.replace("\r", "\n").replace("\x07", " ").strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def word_count() -> int | None:
    app = _attached_app()
    doc = _active_document(app) if app is not None else None
    if doc is None:
        return None
    try:
        return int(doc.ComputeStatistics(WD_STAT_WORDS))
    except Exception:  # noqa: BLE001
        return None


def _safe_name(name: str, limit: int = 60) -> str:
    """Имя файла для голосовой команды: без путей и запрещённых символов."""
    cleaned = re.sub(r"[^\w\s.\-]+", " ", (name or ""), flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:limit].strip(" .")


def save_document(name: str = "") -> Path | None:
    """Сохраняет активный документ. Без имени — в «Документы»."""
    app = _attached_app()
    doc = _active_document(app) if app is not None else None
    if doc is None:
        return None
    target: Path | None = None
    raw_name = (name or "").strip().strip('"').strip()
    if raw_name:
        candidate = Path(raw_name)
        absolute = bool(candidate.drive) and candidate.parent.is_dir()
        if absolute:
            target = candidate
            if target.suffix.lower() not in {".docx", ".doc", ".rtf"}:
                target = target.with_suffix(".docx")
        else:
            stem = _safe_name(candidate.stem or candidate.name)
            if not stem:
                target = _default_path(_document_name(doc))
            else:
                target = _documents_dir() / f"{stem}.docx"
        if target.exists():
            target = _default_path(target.stem)
    else:
        try:
            if str(doc.Path or "").strip():
                doc.Save()
                return Path(str(doc.FullName))
        except Exception:  # noqa: BLE001
            pass
        target = _default_path(_document_name(doc))
    try:
        doc.SaveAs2(str(target))
    except Exception:  # noqa: BLE001
        doc.SaveAs(str(target))
    return target


def export_pdf(name: str = "") -> Path | None:
    """Сохраняет активный документ в PDF рядом с docx или в «Документы»."""
    app = _attached_app()
    doc = _active_document(app) if app is not None else None
    if doc is None:
        return None
    target: Path | None = None
    raw_name = (name or "").strip().strip('"').strip()
    if raw_name:
        candidate = Path(raw_name)
        if candidate.drive and candidate.parent.is_dir():
            target = candidate.with_suffix(".pdf")
        else:
            stem = _safe_name(candidate.stem or candidate.name) or _document_name(doc)
            target = _documents_dir() / f"{stem}.pdf"
        if target.exists():
            target = _default_path(target.stem, ".pdf")
    else:
        try:
            full = str(doc.FullName or "")
        except Exception:  # noqa: BLE001
            full = ""
        if full and Path(full).suffix.lower() in {".docx", ".doc", ".rtf"}:
            target = Path(full).with_suffix(".pdf")
        else:
            target = _default_path(_document_name(doc), ".pdf")
    try:
        doc.ExportAsFixedFormat(str(target), WD_FORMAT_PDF)
    except Exception:  # noqa: BLE001
        doc.SaveAs(str(target), FileFormat=WD_FORMAT_PDF)
    return target


def replace_all(old: str, new: str) -> bool:
    """Заменяет все вхождения текста в активном документе."""
    if not old:
        return False
    app = _attached_app()
    doc = _active_document(app) if app is not None else None
    if doc is None:
        return False
    find = doc.Content.Find
    find.ClearFormatting()
    find.Replacement.ClearFormatting()
    find.Execute(old, False, False, False, False, False, True, 1, False,
                 new, WD_REPLACE_ALL)
    return True


def add_heading(text: str, level: int = 1) -> bool:
    """Добавляет заголовок указанного уровня в конец документа."""
    app = _app(True)
    doc = _active_document(app) or app.Documents.Add()
    _append(doc, text)
    try:
        paragraph = doc.Paragraphs.Last
        paragraph.Style = WD_HEADING_STYLES.get(int(level), -2)
        return True
    except Exception:  # noqa: BLE001
        return False


def add_table(rows: int, cols: int) -> bool:
    rows, cols = max(1, int(rows)), max(1, int(cols))
    app = _app(True)
    doc = _active_document(app) or app.Documents.Add()
    try:
        end = int(doc.Content.End) - 1
        rng = doc.Range(end, end)
        doc.Tables.Add(rng, rows, cols)
        return True
    except Exception:  # noqa: BLE001
        return False


def page_break() -> bool:
    app = _app(True)
    doc = _active_document(app) or app.Documents.Add()
    try:
        end = int(doc.Content.End) - 1
        doc.Range(end, end).InsertBreak(7)
        return True
    except Exception:  # noqa: BLE001
        return False


def close_document(save: bool = True) -> str | None:
    """Закрывает активный документ. Возвращает его имя или None."""
    app = _attached_app()
    doc = _active_document(app) if app is not None else None
    if doc is None:
        return None
    name = _document_name(doc)
    doc.Close(WD_SAVE_CHANGES if save else WD_DO_NOT_SAVE)
    time.sleep(0.2)
    return name


def provider() -> str:
    """Название программы, через которую идёт работа (для ответа Jarvis)."""
    app = _attached_app()
    if app is None:
        return "Microsoft Word"
    return _provider(app) or "Microsoft Word"


def document_info() -> dict | None:
    app = _attached_app()
    doc = _active_document(app) if app is not None else None
    if doc is None:
        return None
    info = {"name": _document_name(doc), "path": "", "words": None, "pages": None}
    try:
        info["path"] = str(doc.FullName or "")
    except Exception:  # noqa: BLE001
        pass
    try:
        info["words"] = int(doc.ComputeStatistics(WD_STAT_WORDS))
    except Exception:  # noqa: BLE001
        pass
    try:
        info["pages"] = int(doc.ComputeStatistics(WD_STAT_PAGES))
    except Exception:  # noqa: BLE001
        pass
    return info
