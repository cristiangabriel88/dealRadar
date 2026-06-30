@echo off
REM ===========================================================================
REM  dealRadar - everyday start. Run first_run.bat once before using this.
REM  Double-click it, or from a terminal run:  run.bat
REM ===========================================================================

cd /d "%~dp0"

echo Starting the app at http://127.0.0.1:5000  (press Ctrl+C to stop)...
python app.py
