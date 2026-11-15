@echo off
rem Сборка портативного приложения «Хряк» для Windows.
rem Результат: dist\Hryak-Windows-x64.zip
setlocal
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo Не найдено окружение venv. Сначала выполните:
    echo   python -m venv venv
    echo   venv\Scripts\pip install -r requirements.txt
    exit /b 1
)
"venv\Scripts\python.exe" packaging\build_portable.py %*
if errorlevel 1 exit /b 1
echo.
echo Готово: dist\Hryak-Windows-x64.zip
