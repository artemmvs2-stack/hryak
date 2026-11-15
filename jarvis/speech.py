"""Слух: постоянное распознавание речи через Vosk + детектор wake-word."""
from __future__ import annotations

import collections
import difflib
import json
import queue
import re
import threading
import time
import wave
from pathlib import Path

from .config import ROOT

DEFAULT_WAKE_WORDS = ["джарвис", "джарвиз", "жарвис", "jarvis"]


def build_wake_re(words) -> re.Pattern:
    """Собирает regex из списка wake-word: допускает падежные окончания."""
    parts: list[str] = []
    for word in words or []:
        word = str(word).strip().lower()
        if word:
            parts.append(re.escape(word) + r"\w*")
    if not parts:
        parts = [re.escape(word) + r"\w*" for word in DEFAULT_WAKE_WORDS]
    return re.compile("|".join(parts), re.IGNORECASE)


WAKE_RE = build_wake_re(DEFAULT_WAKE_WORDS)

STOP_COMMAND_RE = re.compile(
    r"\b(?:стоп|замолчи|тихо|хватит|отбой|отключись|выключись|пока)\b",
    re.IGNORECASE,
)


def is_stop_command(text: str) -> bool:
    """Короткая команда, которая завершает режим диалога."""
    return bool(STOP_COMMAND_RE.search(text or "")) and len((text or "").split()) <= 4

DOMAIN_RE = re.compile(
    r"(?:https?://)?(?:[a-zа-я0-9](?:[a-zа-я0-9-]*[a-zа-я0-9])?\.)+"
    r"(?:ru|рф|com|org|net|info|io|dev|me|tv|co|uk|de|fr|it|es|eu|ai|"
    r"app|site|online|store|tech|xyz)"
    r"(?:/[^\s,;!?)]*)?",
    re.IGNORECASE,
)
SPOKEN_TLDS = {
    "ру": "ru",
    "ком": "com",
    "орг": "org",
    "нет": "net",
    "инфо": "info",
}


def strip_wake(
    text: str,
    wake_re: re.Pattern = WAKE_RE,
    keep_punctuation: bool = False,
) -> str:
    """Убирает wake-word и всё, что было до него.

    keep_punctuation сохраняет знаки в конце фразы: они нужны, чтобы
    надиктованное сообщение получило «?», «!» и запятые. Для проверки
    «осталась ли команда» знаки по-прежнему отбрасываются.
    """
    match = wake_re.search(text)
    if not match:
        return text.strip()
    tail = text[match.end():]
    if keep_punctuation:
        return tail.lstrip(" \t\r\n,;:.!?—–-")
    return tail.strip(" ,.!?")


def strip_wake_loose(
    text: str, wake_re: re.Pattern, wake_words, keep_punctuation: bool = False
) -> str:
    """Убирает wake-word, допуская искажения первого слова.

    GigaAM обычно слышит «хряк» правильно, но иногда выдаёт «хрек», «хряг»
    или «сряк». Если регулярное выражение не сработало, сравниваем первое
    слово с настроенными wake-word по похожести.
    """
    clean = (text or "").strip()
    stripped = strip_wake(clean, wake_re, keep_punctuation=keep_punctuation)
    if stripped != clean:
        return stripped
    tokens = clean.split()
    if not tokens:
        return ""
    first = re.sub(r"[^\w\-]", "", tokens[0].lower().replace("ё", "е"))
    tail = " ".join(tokens[1:])
    for word in wake_words or []:
        target = str(word).lower().replace("ё", "е").strip()
        if target and difflib.SequenceMatcher(None, first, target).ratio() >= 0.72:
            if keep_punctuation:
                return tail.lstrip(" \t\r\n,;:.!?—–-")
            return tail.strip(" ,.!?")
    return clean


COMMAND_VERBS_RE = re.compile(
    r"\b(открой|напиши|ответь|отправь|покажи|найди|переключись)\b",
    re.IGNORECASE,
)
TELEGRAM_WORDS_RE = re.compile(
    r"\b(?:чат|чатик|телеграм|телеграме|телеге|тг)\b", re.IGNORECASE
)
LEADING_NOISE_RE = re.compile(
    r"^(?!не\b|ни\b)[а-яё]{1,4}\s+"
    r"(?=(?:открой|откройте|откчат|напиши|ответь|отправь|покажи|найди|переключись)\b)",
    re.IGNORECASE,
)


def choose_transcript(gigaam_text: str, vosk_text: str) -> str:
    """Выбирает между текстами GigaAM и Vosk, не рискуя смыслом команды.

    GigaAM точнее, поэтому по умолчанию используется она. Единственное
    исключение: GigaAM потеряла слово «чат», а Vosk с тем же глаголом его
    сохранила («открой с жинке» против «открой чат с женьке»). Если глаголы
    разные, доверяем GigaAM — иначе можно открыть чат вместо отправки.
    """
    giga = LEADING_NOISE_RE.sub("", (gigaam_text or "").strip(), count=1)
    vosk = (vosk_text or "").strip()
    if not giga:
        return vosk
    if not vosk:
        return giga
    giga_verb = COMMAND_VERBS_RE.search(giga.lower())
    vosk_verb = COMMAND_VERBS_RE.search(vosk.lower())
    if (
        giga_verb
        and vosk_verb
        and giga_verb.group(1).lower() == vosk_verb.group(1).lower()
        and giga_verb.group(1).lower() in {"открой", "покажи", "переключись"}
        and TELEGRAM_WORDS_RE.search(vosk)
        and not TELEGRAM_WORDS_RE.search(giga)
    ):
        return vosk
    return giga


def merge_words(*parts: str) -> str:
    """Склеивает куски фразы, убирая повтор слов на стыке.

    Vosk выдаёт команду несколькими кусками: «открой чат» + «с Аней».
    Если куски перекрываются, повтор не добавляем.
    """
    result = ""
    for part in parts:
        part = (part or "").strip()
        if not part:
            continue
        if not result:
            result = part
            continue
        a, b = result.split(), part.split()
        overlap = 0
        for size in range(min(len(a), len(b)), 0, -1):
            if a[-size:] == b[:size]:
                overlap = size
                break
        if overlap:
            result = " ".join(a + b[overlap:])
        else:
            result = result + " " + part
    return result


def normalize(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = text.replace("телеграмм", "телеграм")

    # GigaAM иногда смешивает кириллицу и латиницу: «Юouтube».
    text = re.sub(
        r"\b(?:ю\s*ou\s*тube|ю\s*youtube|you\s*тube|youtub|"
        r"ютьюб|ютюб|юутуб|ютуб|you\s*tube|youtube|ю\s*туб)\b",
        "youtube",
        text,
    )

    # «example точка com» -> example.com, «ya точка ру» -> ya.ru.
    text = re.sub(
        r"\b([a-zа-я0-9-]+)\s+(?:точка|дот)\s+([a-zа-я]{2,})\b",
        r"\1.\2",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\.(ру|ком|орг|нет|инфо)\b",
        lambda match: "." + SPOKEN_TLDS[match.group(1)],
        text,
    )

    # Домены и ссылки защищаем от удаления точек и слэшей.
    protected: list[str] = []

    def _protect(match: re.Match) -> str:
        protected.append(match.group(0))
        return f" __url{len(protected) - 1}__ "

    text = DOMAIN_RE.sub(_protect, text)
    text = re.sub(r"[^\w\s\-:]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # «Откройте» -> «открой» до склейки слов.
    text = re.sub(r"^откройте\b", "открой", text)

    # GigaAM иногда склеивает команду и «чат»: «откройтатшенки».
    text = re.sub(
        r"^(открой|покажи|переключись(?:\s+на)?)"
        r"(тат|шат|чат|час|чад)(?=[а-яё]|$)",
        r"\1 чат ",
        text,
    )
    # «откчат» — склейка «открой чат» в e2e-модели.
    text = re.sub(r"^откчат\b", "открой чат", text)
    # И просто склеенный глагол: «откройшенки» -> «открой шенки».
    text = re.sub(
        r"^(открой|покажи|напиши|ответь|отправь|найди)(?=[а-яё])",
        r"\1 ",
        text,
    )

    # Vosk часто слышит «чат» как «час»/«чад».
    text = re.sub(
        r"^(открой|закрой|покажи|напиши|ответь|отправь|переключись(?:\s+на)?)\s+(час|чад)\b",
        r"\1 чат",
        text,
    )
    text = re.sub(
        r"\b(напиши|ответь|отправь|открой|покажи)\s+в\s+(час|чад)\b",
        r"\1 в чат",
        text,
    )

    # «Откройте» вместо «открой», «ответил/ответила» вместо «ответь».
    text = re.sub(r"^откройте\b", "открой", text)
    text = re.sub(r"^ответил(?:а|о|и)?\b", "ответь", text)

    # «открой отца Аню» / «открой от Аней» — Vosk теряет слово «чат».
    text = re.sub(
        r"^(открой|покажи)\s+(?:отца|от|отсель|отсеять)\b",
        r"\1 чат",
        text,
    )

    # «и напиши...», «ну открой...» — убираем вводные слова.
    text = re.sub(r"^(?:(?:и|а|ну|так|пожалуйста|давай)\s+)+", "", text)
    text = re.sub(r"\s+(?:пожалуйста|будь добр|будьте добры)$", "", text)
    for index, url in enumerate(protected):
        text = text.replace(f"__url{index}__", url)
    return text.strip()


class Listener:
    """Слушает микрофон, ждёт wake-word, затем распознаёт команду."""

    def __init__(self, cfg: dict, speaker, on_command, log, on_followup=None):
        self.cfg = cfg
        self.speaker = speaker
        self.on_command = on_command
        self.on_followup = on_followup
        self.log = log
        words = cfg.get("wake_words") or DEFAULT_WAKE_WORDS
        self.wake_words = [str(word) for word in words]
        self.wake_re = build_wake_re(words)
        self.wake_name = str(words[0]).capitalize() if words else "Джарвис"
        self.model = None
        self._audio_q: "queue.Queue[bytes]" = queue.Queue()
        self._running = False
        self._manual = threading.Event()
        self._thread = None
        self._device_error = None
        self._busy = threading.Event()
        self._gigaam_cfg = cfg.get("gigaam") or {}
        self.gigaam = None
        if str(cfg.get("stt_engine", "vosk")).lower() == "gigaam":
            try:
                from .stt_gigaam import GigaAMRecognizer  # noqa: PLC0415

                self.gigaam = GigaAMRecognizer(cfg, log)
            except Exception as exc:  # noqa: BLE001
                log.error("GigaAM недоступна, остаюсь на Vosk: %s", exc)

    # ------------------------------------------------------------------
    def load_model(self) -> bool:
        from vosk import Model, SetLogLevel  # noqa: PLC0415

        SetLogLevel(-1)
        model_path = ROOT / self.cfg.get("model_dir", "models/vosk-model-small-ru-0.22")
        if not Path(model_path).exists():
            self.log.error("Модель Vosk не найдена: %s", model_path)
            return False
        started = time.time()
        self.model = Model(str(model_path))
        self.log.info("Модель Vosk загружена за %.1f с", time.time() - started)
        return True

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        if self.gigaam is not None:
            self.gigaam.start()
        self._thread = threading.Thread(target=self._run, daemon=True, name="listener")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self.gigaam is not None:
            self.gigaam.close()

    def trigger_manual(self) -> None:
        """Ручной запуск прослушивания (пункт меню / горячая клавиша)."""
        self._manual.set()

    # ------------------------------------------------------------------
    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        if status:
            self.log.debug("audio status: %s", status)
        self._audio_q.put(bytes(indata))

    def _beep(self) -> None:
        if not self.cfg.get("beep", True):
            return
        try:
            import winsound  # noqa: PLC0415

            winsound.Beep(980, 80)
            winsound.Beep(1320, 110)
        except Exception:  # noqa: BLE001
            pass

    def _drain(self) -> None:
        while not self._audio_q.empty():
            try:
                self._audio_q.get_nowait()
            except queue.Empty:
                break

    def _run(self) -> None:
        import sounddevice as sd  # noqa: PLC0415
        from vosk import KaldiRecognizer  # noqa: PLC0415

        if self.model is None and not self.load_model():
            return

        sr = int(self.cfg.get("sample_rate", 16000))
        silence_timeout = float(self.cfg.get("silence_timeout", 1.8))
        max_seconds = float(self.cfg.get("max_command_seconds", 12))
        pre_roll = float(self._gigaam_cfg.get("pre_roll_seconds", 3.0))
        followup_seconds = float(self.cfg.get("followup_seconds", 30))
        rec = KaldiRecognizer(self.model, sr)
        rec.SetWords(True)

        attempt = 0
        while self._running:
            try:
                with sd.RawInputStream(
                    samplerate=sr,
                    blocksize=4000,
                    dtype="int16",
                    channels=1,
                    callback=self._callback,
                ):
                    self.log.info("Микрофон открыт, жду '%s'", self.wake_name)
                    self._listen_loop(
                        rec,
                        sr,
                        silence_timeout,
                        max_seconds,
                        pre_roll,
                        followup_seconds,
                    )
            except Exception as exc:  # noqa: BLE001
                attempt += 1
                self.log.error("Ошибка аудиопотока (%s): %s", attempt, exc)
                time.sleep(min(5 * attempt, 30))

    def _listen_loop(
        self,
        rec,
        sr,
        silence_timeout,
        max_seconds,
        pre_roll_seconds=0.0,
        followup_seconds=0.0,
    ) -> None:  # noqa: ANN001
        self._drain()
        rec.Reset()
        state = "idle"
        parts: list[str] = []
        chunk = ""
        last_partial = ""
        last_activity = 0.0
        listen_start = 0.0
        speech_guard = 0.0
        pre_roll: "collections.deque[bytes]" = collections.deque()
        pre_roll_bytes = 0
        pre_roll_limit = max(0, int(pre_roll_seconds * sr * 2))
        audio_parts: list[bytes] = []
        followup_until = 0.0
        followup_utterance = False
        addressed_utterance = True

        while self._running:
            try:
                data = self._audio_q.get(timeout=0.25)
            except queue.Empty:
                data = None

            if self.speaker.is_speaking:
                self._drain()
                rec.Reset()
                state, parts, chunk, last_partial = "idle", [], "", ""
                pre_roll.clear()
                pre_roll_bytes = 0
                audio_parts = []
                if followup_seconds > 0 and followup_until:
                    # Пока ассистент говорит, окно диалога не должно истекать.
                    followup_until = time.time() + followup_seconds
                speech_guard = time.time() + 0.7
                continue

            if time.time() < speech_guard:
                # не слушаем сразу после собственной речи, чтобы не услышать себя
                self._drain()
                rec.Reset()
                pre_roll.clear()
                pre_roll_bytes = 0
                audio_parts = []
                continue

            if state == "idle" and self._busy.is_set():
                # Предыдущая команда ещё выполняется: не принимаем новую.
                self._drain()
                rec.Reset()
                pre_roll.clear()
                pre_roll_bytes = 0
                if followup_seconds > 0 and followup_until:
                    followup_until = time.time() + followup_seconds
                continue

            # Копим звук для GigaAM: в idle — кольцевой буфер до wake-word,
            # в listen — всю команду целиком.
            if data:
                if state == "idle" and pre_roll_limit > 0:
                    pre_roll.append(data)
                    pre_roll_bytes += len(data)
                    while pre_roll and pre_roll_bytes > pre_roll_limit:
                        pre_roll_bytes -= len(pre_roll.popleft())
                elif state == "listen":
                    audio_parts.append(data)

            final_text = ""
            final_conf = 0.0
            partial = ""
            if data:
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    final_text = result.get("text", "").strip()
                    words = result.get("result") or []
                    if words:
                        final_conf = sum(
                            float(word.get("conf", 0.0)) for word in words
                        ) / len(words)
                else:
                    partial = json.loads(rec.PartialResult()).get("partial", "").strip()

            now = time.time()

            if state == "idle":
                if self._manual.is_set():
                    self._manual.clear()
                    rec.Reset()
                    self._drain()
                    state, parts, chunk, last_partial = (
                        "listen", [], "", ""
                    )
                    audio_parts = list(pre_roll)
                    pre_roll.clear()
                    pre_roll_bytes = 0
                    listen_start = last_activity = now
                    followup_utterance = False
                    addressed_utterance = True
                    self._beep()
                    continue

                # Wake-word может прийти и в partial, и сразу в final.
                heard = partial or final_text
                if heard and self.wake_re.search(heard):
                    # ВАЖНО: не сбрасываем распознаватель. Vosk копит всю
                    # фразу в partial, и сброс терял бы её половину.
                    state, parts, chunk, last_partial = "listen", [], "", ""
                    audio_parts = list(pre_roll)
                    pre_roll.clear()
                    pre_roll_bytes = 0
                    start = strip_wake(heard, self.wake_re)
                    if start:
                        if final_text:
                            # Vosk уже завершил сегмент: сохраняем его текст.
                            parts.append(start)
                        else:
                            # Команда уже видна в partial: не потеряем её,
                            # если новых partial больше не будет.
                            chunk = start
                            last_partial = start
                    listen_start = last_activity = now
                    followup_utterance = False
                    addressed_utterance = True
                    self.log.info("Wake-word услышан")
                    self._beep()
                    continue

                if followup_seconds > 0:
                    if followup_until and now >= followup_until:
                        followup_until = 0.0
                        self.log.info(
                            "Режим диалога завершён, снова жду '%s'",
                            self.wake_name,
                        )
                    elif heard and followup_until:
                        # Продолжение диалога: wake-word не нужен.
                        state, parts, chunk, last_partial = (
                            "listen", [], "", ""
                        )
                        audio_parts = list(pre_roll)
                        pre_roll.clear()
                        pre_roll_bytes = 0
                        text = heard.strip()
                        if final_text:
                            parts.append(text)
                        else:
                            chunk = text
                            last_partial = text
                        listen_start = last_activity = now
                        followup_utterance = True
                        addressed_utterance = False
                        self.log.info("Продолжение диалога без wake-word")
                continue

            # ---- состояние listen ----
            if final_text:
                text = (
                    strip_wake(final_text, self.wake_re)
                    if self.wake_re.search(final_text)
                    else final_text
                )
                if self.wake_re.search(final_text):
                    addressed_utterance = True
                if text:
                    parts.append(text)
                chunk = ""
                last_partial = ""
                # Vosk завершил сегмент: даём короткое окно, чтобы человек
                # мог продолжить фразу после паузы, и только потом выполняем.
                last_activity = now - silence_timeout + min(1.0, silence_timeout)
            elif partial:
                text = (
                    strip_wake(partial, self.wake_re)
                    if self.wake_re.search(partial)
                    else partial
                )
                if self.wake_re.search(partial):
                    addressed_utterance = True
                chunk = text
                # Vosk может повторять один и тот же partial в тишине:
                # продлеваем ожидание, только когда текст реально меняется.
                if text != last_partial:
                    last_partial = text
                    last_activity = now

            command = merge_words(" ".join(parts), chunk).strip()
            silent_for = now - last_activity
            too_long = now - listen_start > max_seconds

            done = bool(command) and silent_for >= silence_timeout
            if not done and too_long:
                done = True

            if done:
                self.log.info(
                    "Распознано: %r (уверенность %.2f, тишина %.1f с)",
                    command,
                    final_conf,
                    silent_for,
                )
                wav_path = None
                if self.gigaam is not None and audio_parts:
                    wav_path = self._save_command_wav(
                        b"".join(audio_parts), sr
                    )
                state, parts, chunk, last_partial = "idle", [], "", ""
                pre_roll.clear()
                pre_roll_bytes = 0
                audio_parts = []
                rec.Reset()
                self._drain()
                if command.strip():
                    if followup_seconds > 0:
                        if is_stop_command(command):
                            followup_until = 0.0
                            self.log.info(
                                "Режим диалога закрыт командой %r", command
                            )
                        else:
                            # Каждая команда продлевает окно диалога.
                            followup_until = now + followup_seconds
                    threading.Thread(
                        target=self._recognize_and_handle,
                        args=(command, wav_path, addressed_utterance),
                        daemon=True,
                    ).start()
                elif too_long:
                    if followup_utterance:
                        followup_until = 0.0
                        self.log.info("Режим диалога завершён: тишина")
                    else:
                        self.speaker.say("Я вас не расслышал, сэр.")
                followup_utterance = False
                addressed_utterance = True

    def _save_command_wav(self, pcm: bytes, sr: int):
        """Сохраняет команду в WAV для GigaAM и хранит последние 40 файлов."""
        try:
            folder = ROOT / "data" / "stt"
            folder.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            path = folder / (
                f"command_{stamp}_{int(time.time() * 1000) % 1000:03d}.wav"
            )
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(sr)
                wav.writeframes(pcm)
            for old in sorted(folder.glob("command_*.wav"))[:-40]:
                try:
                    old.unlink()
                except OSError:
                    pass
            return path
        except Exception as exc:  # noqa: BLE001
            self.log.error("Не удалось сохранить аудио команды: %s", exc)
            return None

    def _recognize_and_handle(
        self, vosk_text: str, wav_path, addressed: bool = True
    ) -> None:  # noqa: ANN001
        """Уточняет команду через GigaAM; при сбое остаётся текст Vosk."""
        self._busy.set()
        text = vosk_text
        try:
            if self.gigaam is not None and wav_path is not None:
                started = time.time()
                recognized = self.gigaam.transcribe(wav_path)
                if recognized:
                    cleaned = strip_wake_loose(
                        recognized,
                        self.wake_re,
                        self.wake_words,
                        keep_punctuation=True,
                    )
                    if cleaned:
                        chosen = choose_transcript(cleaned, vosk_text)
                        if chosen != cleaned:
                            self.log.info(
                                "Vosk дополнил GigaAM: %r (GigaAM: %r)",
                                chosen,
                                cleaned,
                            )
                        text = chosen
                        self.log.info(
                            "GigaAM: %r (Vosk: %r, %.1f с)",
                            text,
                            vosk_text,
                            time.time() - started,
                        )
                    else:
                        self.log.warning(
                            "GigaAM услышала только wake-word: %r", recognized
                        )
                else:
                    self.log.warning(
                        "GigaAM недоступна, использую Vosk: %r", vosk_text
                    )
            self._safe_handle(text, addressed)
        finally:
            self._busy.clear()

    def _safe_handle(self, command: str, addressed: bool = True) -> None:
        try:
            handler = self.on_command
            if not addressed and self.on_followup is not None:
                handler = self.on_followup
            handler(command)
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Ошибка обработки команды: %s", exc)
