"""Клиент GigaAM: отдельный процесс с моделью и обмен JSON-строками.

В исходной версии GigaAM живёт в venv_gigaam и не конфликтует с torch
основного venv; в портативной сборке используется встроенный Python.
При любой ошибке распознавания Listener остаётся на тексте Vosk.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path

from .config import ROOT

WORKER_LOG_LIMIT = 5_000_000


class GigaAMRecognizer:
    def __init__(self, cfg: dict, log) -> None:
        options = cfg.get("gigaam") or {}
        self.log = log
        self.enabled = bool(options.get("enabled", False))
        self.model = str(options.get("model") or "gigaam-v3-ctc")
        self.quantization = str(options.get("quantization") or "int8")
        self.timeout = float(options.get("timeout") or 30)
        self.restarts = max(0, int(options.get("restarts", 2)))
        self.threads = str(options.get("threads", 4))

        python = Path(str(options.get("python") or "venv_gigaam/Scripts/python.exe"))
        worker = Path(str(options.get("worker") or "gigaam_worker.py"))
        model_dir = Path(str(options.get("download_root") or "models/gigaam"))
        self.python = python if python.is_absolute() else ROOT / python
        self.worker = worker if worker.is_absolute() else ROOT / worker
        self.download_root = model_dir if model_dir.is_absolute() else ROOT / model_dir

        self._proc: subprocess.Popen | None = None
        self._worker_pid = 0
        self._ready = threading.Event()
        self._closed = threading.Event()
        self._responses: "queue.Queue[dict]" = queue.Queue()
        self._request_id = 0
        self._request_lock = threading.Lock()
        self._supervisor: threading.Thread | None = None
        self._stderr = None

    # ------------------------------------------------------------------
    def available(self) -> bool:
        return self.python.is_file() and self.worker.is_file()

    def start(self) -> bool:
        if not self.enabled:
            self.log.info("GigaAM выключена в настройках, слушаю через Vosk")
            return False
        if not self.available():
            self.log.warning(
                "GigaAM включена, но не найдена: %s или %s. Остаюсь на Vosk",
                self.python,
                self.worker,
            )
            return False
        if self._supervisor is not None and self._supervisor.is_alive():
            return True
        self._supervisor = threading.Thread(
            target=self._supervise, daemon=True, name="gigaam"
        )
        self._supervisor.start()
        return True

    def close(self) -> None:
        self._closed.set()
        self._ready.clear()
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                if proc.stdin is not None:
                    proc.stdin.close()
            except Exception:  # noqa: BLE001
                pass
            try:
                proc.wait(timeout=2)
            except Exception:  # noqa: BLE001
                self._kill_pid(proc.pid)
        self._kill_worker()
        self._close_stderr()

    # ------------------------------------------------------------------
    def transcribe(self, wav_path) -> str | None:
        """Распознаёт WAV. None — GigaAM недоступна, нужен fallback на Vosk."""
        if not self.enabled or not self._ready.is_set():
            return None
        proc = self._proc
        if proc is None or proc.poll() is not None or proc.stdin is None:
            return None

        with self._request_lock:
            if not self._ready.is_set():
                return None
            self._request_id += 1
            request_id = self._request_id
            payload = json.dumps(
                {"id": request_id, "wav": str(wav_path)}, ensure_ascii=False
            )
            try:
                proc.stdin.write(payload + "\n")
                proc.stdin.flush()
            except Exception as exc:  # noqa: BLE001
                self.log.error("GigaAM: не удалось отправить запрос: %s", exc)
                self._kill()
                return None

            deadline = time.monotonic() + self.timeout
            while True:
                if self._closed.is_set():
                    return None
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.log.error(
                        "GigaAM: таймаут распознавания (%.0f с), перезапускаю worker",
                        self.timeout,
                    )
                    self._kill()
                    return None
                try:
                    message = self._responses.get(timeout=min(0.25, remaining))
                except queue.Empty:
                    continue
                if message.get("id") != request_id:
                    continue
                if message.get("ok"):
                    text = str(message.get("text") or "").strip()
                    self.log.info(
                        "GigaAM распознала за %.2f с: %r",
                        float(message.get("seconds") or 0.0),
                        text,
                    )
                    return text or None
                self.log.warning(
                    "GigaAM: ошибка распознавания: %s", message.get("error")
                )
                return None

    # ------------------------------------------------------------------
    def _supervise(self) -> None:
        failures = 0
        while not self._closed.is_set() and failures <= self.restarts:
            if failures:
                delay = min(10 * failures, 30)
                self.log.info("GigaAM: перезапуск worker через %s с", delay)
                if self._closed.wait(delay):
                    return
            try:
                self._spawn()
            except Exception as exc:  # noqa: BLE001
                self.log.error("GigaAM: не удалось запустить worker: %s", exc)
                failures += 1
                continue

            self._read_loop()
            if self._closed.is_set():
                return
            failures += 1
            self.log.warning(
                "GigaAM: worker завершился (попытка %s из %s)",
                failures,
                self.restarts,
            )

        if not self._closed.is_set():
            self.log.error("GigaAM отключена до перезапуска Jarvis: worker не запускается")

    def _spawn(self) -> None:
        self._worker_pid = 0
        log_dir = ROOT / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "gigaam_worker.log"
        try:
            if log_path.exists() and log_path.stat().st_size > WORKER_LOG_LIMIT:
                log_path.unlink()
        except OSError:
            pass
        self._stderr = open(log_path, "a", encoding="utf-8", buffering=1)

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        env["OMP_NUM_THREADS"] = self.threads
        env["MKL_NUM_THREADS"] = self.threads
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        self._proc = subprocess.Popen(
            [
                str(self.python),
                str(self.worker),
                self.model,
                str(self.download_root),
                self.quantization,
            ],
            cwd=str(ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=flags,
            env=env,
        )
        self.log.info(
            "GigaAM: worker запущен (PID %s), модель %s, каталог %s",
            self._proc.pid,
            self.model,
            self.download_root,
        )

    def _read_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        self._ready.clear()
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    self.log.debug("GigaAM worker: %s", line[:300])
                    continue
                if message.get("ready"):
                    self._ready.set()
                    worker_pid = int(message.get("pid") or 0)
                    if worker_pid:
                        self._worker_pid = worker_pid
                    self.log.info(
                        "GigaAM готова к работе (загрузка %.1f с)",
                        float(message.get("load_seconds") or 0.0),
                    )
                elif "ready" in message:
                    self.log.error(
                        "GigaAM: модель не загрузилась: %s", message.get("error")
                    )
                else:
                    self._responses.put(message)
        except Exception as exc:  # noqa: BLE001
            self.log.debug("GigaAM: чтение stdout прервано: %s", exc)
        finally:
            self._ready.clear()
            try:
                proc.wait(timeout=3)
            except Exception:  # noqa: BLE001
                pass
            self._kill_worker()
            self._close_stderr()

    def _kill(self) -> None:
        self._ready.clear()
        proc = self._proc
        if proc is not None and proc.poll() is None:
            self._kill_pid(proc.pid)
        self._kill_worker()

    def _kill_worker(self) -> None:
        pid, self._worker_pid = self._worker_pid, 0
        if pid:
            self._kill_pid(pid)

    @staticmethod
    def _kill_pid(pid: int) -> None:
        """Убивает процесс и всех его потомков (venv-питон запускает дочерний)."""
        if not pid:
            return
        try:
            import psutil  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            GigaAMRecognizer._fallback_kill(pid)
            return
        try:
            process = psutil.Process(pid)
        except Exception:  # noqa: BLE001
            return
        try:
            children = process.children(recursive=True)
        except Exception:  # noqa: BLE001
            children = []
        for child in children:
            try:
                child.kill()
            except Exception:  # noqa: BLE001
                pass
        try:
            process.kill()
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _fallback_kill(pid: int) -> None:
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception:  # noqa: BLE001
                pass
        else:
            try:
                os.kill(pid, 9)
            except Exception:  # noqa: BLE001
                pass

    def _close_stderr(self) -> None:
        handle, self._stderr = self._stderr, None
        if handle is not None:
            try:
                handle.close()
            except Exception:  # noqa: BLE001
                pass
