@echo off
REM Avvio del cervello Gaia (gira sul PC, NON nel container VPS).
REM Usato sia per l'avvio manuale sia dal Task Scheduler (ONLOGON).
REM pythonw = nessuna finestra console; i log vanno in brain\gaia_brain.log
set PYTHONUTF8=1
cd /d "%~dp0"
start "" /b ".venv\Scripts\pythonw.exe" "%~dp0runner.py"
