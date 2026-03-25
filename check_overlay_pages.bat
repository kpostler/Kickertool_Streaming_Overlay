@echo off
setlocal

cd /d "%~dp0"

start "" http://127.0.0.1:5000/config
timeout /t 1 /nobreak >nul

start "" http://127.0.0.1:5000/display_match/1
timeout /t 1 /nobreak >nul

start "" http://127.0.0.1:8000/Overlay.html
timeout /t 1 /nobreak >nul

start "" http://127.0.0.1:8000/control.html
timeout /t 1 /nobreak >nul

start "" http://127.0.0.1:8000/standings_full.html
timeout /t 1 /nobreak >nul

start "" http://127.0.0.1:8000/standings_mini.html
timeout /t 1 /nobreak >nul

start "" http://127.0.0.1:8000/bracket_mini.html

echo Testseiten wurden geoeffnet.
pause
