@echo off
setlocal
cd /d "%~dp0"
title Social Media Finder
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" bootstrap.py %*
    goto finished
)
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if not errorlevel 1 (
    py -3 bootstrap.py %*
    goto finished
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if not errorlevel 1 (
    python bootstrap.py %*
    goto finished
)
echo Python 3.11 or newer was not found.
echo Install Python from https://www.python.org/downloads/windows/
echo Enable "Add python.exe to PATH" during installation, then double-click run.bat again.
pause
exit /b 1
:finished
if errorlevel 1 (
    echo.
    echo Startup failed. Read the error above. See README.md for help.
    pause
    exit /b 1
)
endlocal
