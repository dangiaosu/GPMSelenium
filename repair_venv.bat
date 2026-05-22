@echo off
setlocal
cd /d "%~dp0"

echo Rebuilding virtual environment for this folder...

if exist ".venv" (
  rmdir /s /q ".venv"
)

where py >nul 2>nul
if not errorlevel 1 (
  py -3.12 -m venv .venv
  if errorlevel 1 py -3.11 -m venv .venv
  if errorlevel 1 py -3 -m venv .venv
) else (
  python -m venv .venv
)

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo Failed to create .venv. Install Python 3.11 or newer, then run this file again.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
  echo.
  echo Failed to upgrade pip.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 (
  echo.
  echo Failed to install GPMSelenium dependencies.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -c "import PySide6; import sys; sys.path.insert(0, 'src'); import gpm_selenium.gui"
if errorlevel 1 (
  echo.
  echo Install finished but GPMSelenium import check failed.
  pause
  exit /b 1
)

echo.
echo Virtual environment rebuilt successfully for this folder.
pause
