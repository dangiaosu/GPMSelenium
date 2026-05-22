@echo off
setlocal
cd /d "%~dp0"

set "VENV_PY=%CD%\.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
  echo Missing .venv for this folder.
  echo Run repair_venv.bat first, then run this file again.
  pause
  exit /b 1
)

"%VENV_PY%" -c "import sys; print(sys.executable)" >nul 2>nul
if errorlevel 1 (
  echo The .venv in this folder is broken or points to another computer.
  echo Run repair_venv.bat to rebuild it for this machine.
  pause
  exit /b 1
)

"%VENV_PY%" -c "import PySide6" >nul 2>nul
if errorlevel 1 (
  echo PySide6 is missing from this .venv.
  echo Run repair_venv.bat first, then run this file again.
  pause
  exit /b 1
)

echo Starting GPMSelenium...
"%VENV_PY%" "%CD%\launch_gui.py"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo GPMSelenium exited with error code %EXIT_CODE%.
  echo If this is a new machine, run repair_venv.bat and try again.
)
pause
exit /b %EXIT_CODE%
