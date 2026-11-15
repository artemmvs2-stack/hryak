#!/usr/bin/env python
"""Сборка портативного приложения «Хряк» для Windows.

Что делает скрипт:
  1. скачивает официальный embeddable Python 3.12;
  2. создаёт чистое окружение и ставит зависимости (без torch);
  3. собирает папку build_portable/Hryak с кодом, Python и моделями;
  4. компилирует Hryak.exe (запуск без консоли, иконка);
  5. упаковывает всё в dist/Hryak-Windows-x64.zip.

Запуск:
    venv\\Scripts\\python.exe packaging\\build_portable.py
    venv\\Scripts\\python.exe packaging\\build_portable.py --skip-install
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"
BUILD = ROOT / "build_portable"
CACHE = BUILD / "cache"
DIST = BUILD / "Hryak"
VENV = BUILD / "venv_build"
OUT_DIR = ROOT / "dist"
ZIP_PATH = OUT_DIR / "Hryak-Windows-x64.zip"
PY_VERSION = "3.12.10"
PY_EMBED = CACHE / f"python-{PY_VERSION}-embed-amd64.zip"
PY_URL = (
    f"https://www.python.org/ftp/python/{PY_VERSION}/"
    f"python-{PY_VERSION}-embed-amd64.zip"
)

APP_FILES = (
    "jarvis.py",
    "gigaam_worker.py",
    "README.md",
    "config.example.json",
    "requirements.txt",
    "requirements-gigaam.txt",
    "requirements-silero.txt",
)
APP_DIRS = ("jarvis", "tools", "assets")
PIPER_FILES = ("ru_RU-denis-medium.onnx", "ru_RU-denis-medium.onnx.json")
MODEL_DIRS = (
    ("vosk-model-small-ru-0.22", "models/vosk-model-small-ru-0.22"),
    ("gigaam_e2e", "models/gigaam_e2e"),
)
IGNORE = shutil.ignore_patterns(
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".pytest_cache",
    "bench_astra*.py",
    "bench_luna.py",
    "bench_star*.py",
)
ONNX_SUFFIXES = {".onnx", ".pt", ".bin"}


def log(message: str) -> None:
    print(f"[build] {message}", flush=True)


def run(command: list[str], **kwargs) -> None:
    log(" ".join(str(part) for part in command))
    subprocess.check_call([str(part) for part in command], **kwargs)


def download_python() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    if (
        PY_EMBED.is_file()
        and PY_EMBED.stat().st_size > 5_000_000
        and zipfile.is_zipfile(PY_EMBED)
    ):
        log(f"Python уже скачан: {PY_EMBED.name}")
        return
    if PY_EMBED.exists():
        PY_EMBED.unlink()
    log(f"Скачиваю {PY_URL}")
    try:
        with urllib.request.urlopen(PY_URL, timeout=120) as response:
            PY_EMBED.write_bytes(response.read())
    except Exception as exc:  # noqa: BLE001
        log(f"urllib не смог скачать ({exc}), пробую curl.exe")
        run(["curl.exe", "-L", "--fail", "-o", str(PY_EMBED), PY_URL])


def prepare_runtime() -> None:
    if DIST.exists():
        log(f"Удаляю старую сборку {DIST}")
        shutil.rmtree(DIST)
    runtime = DIST / "python"
    runtime.mkdir(parents=True)
    log(f"Распаковываю {PY_EMBED.name}")
    with zipfile.ZipFile(PY_EMBED) as archive:
        archive.extractall(runtime)

    pth_files = list(runtime.glob("python*._pth"))
    if not pth_files:
        raise RuntimeError("В embeddable Python не найден файл _pth")
    pth = pth_files[0]
    pth.write_text(
        "python312.zip\n.\nLib\\site-packages\nimport site\n",
        encoding="utf-8",
    )


def install_dependencies() -> None:
    if not (VENV / "Scripts" / "python.exe").is_file():
        log("Создаю чистое окружение сборки")
        run([sys.executable, "-m", "venv", str(VENV)])
    python = VENV / "Scripts" / "python.exe"
    run(
        [
            python,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "-r",
            PACKAGING / "requirements-portable.txt",
        ]
    )


def copy_runtime_packages() -> None:
    source = VENV / "Lib" / "site-packages"
    target = DIST / "python" / "Lib" / "site-packages"
    target.mkdir(parents=True, exist_ok=True)
    log("Копирую зависимости в портативный Python (это может занять минуту)")
    shutil.copytree(source, target, dirs_exist_ok=True, ignore=IGNORE)


def copy_app() -> None:
    log("Копирую код приложения")
    for name in APP_FILES:
        source = ROOT / name
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copy2(source, DIST / name)
    for name in APP_DIRS:
        shutil.copytree(ROOT / name, DIST / name, ignore=IGNORE)
    shutil.copy2(PACKAGING / "config.portable.json", DIST / "config.portable.json")
    shutil.copy2(PACKAGING / "THIRD_PARTY_NOTICES.md", DIST / "THIRD_PARTY_NOTICES.md")


def copy_models() -> None:
    models = DIST / "models"
    models.mkdir(parents=True, exist_ok=True)
    for source_name, target_name in MODEL_DIRS:
        source = ROOT / "models" / source_name
        if not source.is_dir():
            raise FileNotFoundError(f"Нет модели: {source}")
        log(f"Копирую модель {source_name}")
        shutil.copytree(source, DIST / target_name, ignore=IGNORE)

    piper_source = ROOT / "models" / "piper"
    piper_target = models / "piper"
    piper_target.mkdir(parents=True)
    for name in PIPER_FILES:
        source = piper_source / name
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copy2(source, piper_target / name)


def find_csc() -> Path:
    windows = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates = (
        windows / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe",
        windows / "Microsoft.NET" / "Framework" / "v4.0.30319" / "csc.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("Не найден csc.exe из .NET Framework 4.x")


def build_launcher() -> None:
    icon = ROOT / "assets" / "jarvis.ico"
    source = PACKAGING / "launcher" / "Hryak.cs"
    output = DIST / "Hryak.exe"
    log("Компилирую Hryak.exe")
    run(
        [
            find_csc(),
            "/nologo",
            "/target:winexe",
            "/optimize+",
            "/codepage:65001",
            "/platform:anycpu",
            f"/win32icon:{icon}",
            "/r:System.dll",
            "/r:System.Windows.Forms.dll",
            "/r:System.Drawing.dll",
            f"/out:{output}",
            str(source),
        ]
    )


def make_zip() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    log(f"Упаковываю {ZIP_PATH.name} (может занять несколько минут)")
    files = 0
    with zipfile.ZipFile(ZIP_PATH, "w") as archive:
        for path in sorted(DIST.rglob("*")):
            if not path.is_file():
                continue
            arcname = path.relative_to(DIST).as_posix()
            if path.suffix.lower() in ONNX_SUFFIXES:
                archive.write(path, arcname, compress_type=zipfile.ZIP_STORED)
            else:
                archive.write(
                    path,
                    arcname,
                    compress_type=zipfile.ZIP_DEFLATED,
                    compresslevel=6,
                )
            files += 1
    size_mb = ZIP_PATH.stat().st_size / (1024 * 1024)
    log(f"Готово: {ZIP_PATH} ({size_mb:.1f} МБ, файлов: {files})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Сборка портативного «Хряка»")
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="не пересоздавать окружение и не ставить зависимости",
    )
    parser.add_argument(
        "--no-zip",
        action="store_true",
        help="собрать папку, но не упаковывать в zip",
    )
    args = parser.parse_args()

    download_python()
    prepare_runtime()
    if not args.skip_install:
        install_dependencies()
    copy_runtime_packages()
    copy_app()
    copy_models()
    build_launcher()
    if not args.no_zip:
        make_zip()
    log("Сборка завершена")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
