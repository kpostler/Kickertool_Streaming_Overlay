@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_BOOTSTRAP="

where python >nul 2>nul
if not errorlevel 1 (
  python -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PYTHON_BOOTSTRAP=python"
)

if not defined PYTHON_BOOTSTRAP (
  where python3 >nul 2>nul
  if not errorlevel 1 (
    python3 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_BOOTSTRAP=python3"
  )
)

if not defined PYTHON_BOOTSTRAP (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_BOOTSTRAP=py -3"
  )
)

if not defined PYTHON_BOOTSTRAP (
  echo Kein funktionsfaehiger Python-Interpreter gefunden.
  echo Geprueft wurden: python, python3, py -3
  pause
  exit /b 1
)

if not exist "requirements.txt" (
  echo requirements.txt wurde nicht gefunden.
  pause
  exit /b 1
)

if exist ".venv" if not exist ".venv\Scripts\python.exe" (
  echo Vorhandene .venv ist unvollstaendig oder defekt.
  echo Bitte loesche den Ordner .venv und starte das Skript erneut.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Erstelle virtuelle Umgebung in .venv...
  %PYTHON_BOOTSTRAP% -m venv .venv
  if errorlevel 1 (
    echo Venv konnte nicht erstellt werden.
    echo Verwendeter Interpreter: %PYTHON_BOOTSTRAP%
    pause
    exit /b 1
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo Venv wurde nicht korrekt erstellt.
  pause
  exit /b 1
)

echo Installiere oder aktualisiere Abhaengigkeiten...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
  echo Pip konnte nicht aktualisiert werden.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Requirements konnten nicht installiert werden.
  pause
  exit /b 1
)

echo Starte Proxy...
start "Overlay Proxy" /D "%~dp0" cmd /k "".venv\Scripts\python.exe" proxy.py"

timeout /t 2 /nobreak >nul

echo Starte lokalen Webserver ohne Browser-Cache...
start "Overlay Webserver" /D "%~dp0" cmd /k "".venv\Scripts\python.exe" static_server.py"

timeout /t 2 /nobreak >nul

echo Oeffne Steuerseite...
start "" "http://127.0.0.1:8000/control.html?ts=%RANDOM%"

echo.
echo Jetzt kannst du in OBS diese Browser-Quellen verwenden:
echo   http://127.0.0.1:8000/Overlay.html
echo   http://127.0.0.1:8000/standings_full.html
echo   http://127.0.0.1:8000/standings_mini.html
echo   http://127.0.0.1:8000/bracket_mini.html
echo.
pause
