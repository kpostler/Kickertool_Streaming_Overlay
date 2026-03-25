@echo off
setlocal

cd /d "%~dp0"

echo Starte Proxy...
start "Overlay Proxy" cmd /k python proxy.py

timeout /t 2 /nobreak >nul

echo Starte lokalen Webserver...
start "Overlay Webserver" cmd /k python -m http.server 8000

timeout /t 2 /nobreak >nul

echo Oeffne Steuerseite...
start "" http://127.0.0.1:8000/control.html

echo.
echo Jetzt kannst du in OBS diese Browser-Quellen verwenden:
echo   http://127.0.0.1:8000/Overlay.html
echo   http://127.0.0.1:8000/standings_full.html
echo   http://127.0.0.1:8000/standings_mini.html
echo   http://127.0.0.1:8000/bracket_mini.html
echo.
pause
