@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Запуск Jarvis...
"%~dp0venv\Scripts\python.exe" "%~dp0jarvis.py" %*
echo.
echo Jarvis завершён.
pause
