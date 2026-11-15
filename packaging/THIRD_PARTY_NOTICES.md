# Сторонние компоненты портативной сборки «Хряк»

Портативная сборка включает следующие сторонние компоненты. Все права
принадлежат их авторам; компоненты распространяются по своим лицензиям.

| Компонент | Назначение | Лицензия | Источник |
|---|---|---|---|
| Python 3.12 | среда выполнения | PSF License | https://www.python.org |
| Vosk + vosk-model-small-ru-0.22 | wake-word и черновое распознавание | Apache-2.0 | https://alphacephei.com/vosk |
| GigaAM v3 E2E CTC (ai-sage) | точное распознавание команд | MIT | https://huggingface.co/ai-sage/GigaAM-v3 |
| ONNX-конвертация istupakov/gigaam-v3-onnx | модель GigaAM в ONNX | MIT | https://huggingface.co/istupakov/gigaam-v3-onnx |
| Piper (piper1-gpl) | офлайн-синтез речи | GPL-3.0-or-later | https://github.com/OHF-Voice/piper1-gpl |
| Голос ru_RU-denis-medium | модель голоса Piper | датасет CC0 | https://huggingface.co/rhasspy/piper-voices |
| onnx-asr | загрузка и запуск GigaAM | MIT | https://github.com/istupakov/onnx-asr |
| onnxruntime | инференс ONNX | MIT | https://github.com/microsoft/onnxruntime |
| edge-tts | онлайн-голос (резервный) | GPL-3.0 | https://github.com/rany2/edge-tts |
| pywin32 | доступ к Windows API | PSF-2.0 | https://github.com/mhammond/pywin32 |
| pywinauto | управление окнами | BSD-3-Clause | https://github.com/pywinauto/pywinauto |
| comtypes | COM-интерфейсы | MIT | https://github.com/enthought/comtypes |
| pycaw | громкость Windows | MIT | https://github.com/AndreMiras/pycaw |
| pygame | воспроизведение звука | LGPL-2.1-or-later | https://www.pygame.org |
| sounddevice | запись с микрофона | MIT | https://github.com/spatialaudio/python-sounddevice |
| pystray | иконка в трее | LGPL-3.0 | https://github.com/moses-palmer/pystray |
| Pillow | работа с иконками | MIT-CMU | https://python-pillow.org |
| pyttsx3 | запасной SAPI-голос | MPL-2.0 | https://github.com/nateshmbhat/pyttsx3 |
| yt-dlp | загрузка медиа | Unlicense | https://github.com/yt-dlp/yt-dlp |
| psutil | процессы и система | BSD-3-Clause | https://github.com/giampaolo/psutil |

Модели Vosk, GigaAM и Piper не являются частью исходного кода проекта и
включены в готовую сборку для удобства. Исходники самого «Хряка» открыты в
этом репозитории. При перераспространении сборки сохраните этот файл и
соблюдайте лицензии компонентов (для GPL-компонентов — предоставьте исходный
код и текст лицензии).
