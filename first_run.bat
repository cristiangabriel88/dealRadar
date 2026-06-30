@echo off
REM ===========================================================================
REM  dealRadar - first-time setup, then start the app.
REM  Run this once on a fresh machine (or after the Facebook session expires).
REM  Double-click it, or from a terminal run:  first_run.bat
REM  Each step waits for the previous one to finish.
REM ===========================================================================

cd /d "%~dp0"

echo [1/4] Installing Python dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [2/4] Installing the Playwright Chromium browser...
python -m playwright install chromium
if errorlevel 1 goto :error

echo [3/4] Importing your Facebook session from Chrome...
echo       Follow the on-screen steps to paste the c_user and xs cookie values
echo       from Chrome's DevTools (this avoids Facebook's new-device 2FA).
python -m olx_finder.fb_import_cookies
if errorlevel 1 goto :error

echo [4/4] Starting the app at http://127.0.0.1:5000  (press Ctrl+C to stop)...
python app.py
goto :eof

:error
echo.
echo Setup failed on the step above. Fix the error and run first_run.bat again.
pause
