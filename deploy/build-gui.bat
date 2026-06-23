:: Build a standalone serial-tcp-gui.exe (Windows GUI) via PyInstaller.
:: Usage: deploy\build-gui.bat [path\to\python.exe]
::
:: Produces serial-tcp-gui.exe in the repository root. Uses a throwaway
:: virtualenv (.buildenv) so it does NOT touch your working .venv.
@echo off
setlocal
set PYTHONIOENCODING=utf-8

:: Use provided python path or default to "python"
set PYTHON=python
if not "%~1"=="" set PYTHON=%~1

:: Move to the repository root (parent of this script's folder)
cd /d "%~dp0.."

:: Check Python version >= 3.9
for /f "tokens=2 delims= " %%v in ('"%PYTHON%" --version 2^>^&1') do set PYVER=%%v
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    if %%a LSS 3 (
        echo ERROR: Python ^>=3.9 required, found %PYVER%
        exit /b 1
    )
    if %%a==3 if %%b LSS 9 (
        echo ERROR: Python ^>=3.9 required, found %PYVER%
        exit /b 1
    )
)
echo Using Python %PYVER% (%PYTHON%)

"%PYTHON%" -m venv .buildenv || exit /b 1
call .buildenv\Scripts\activate.bat

python -m pip install --upgrade pip
pip install pyinstaller "pyserial>=3.3" "pyyaml>=5.1" || exit /b 1

pyinstaller --onefile --windowed ^
    --name serial-tcp-gui ^
    --paths "." ^
    --paths "gui" ^
    --icon gui\serialtcp_gui\assets\app.ico ^
    --add-data "gui\serialtcp_gui\assets;serialtcp_gui/assets" ^
    --hidden-import serial.tools.list_ports ^
    --hidden-import yaml ^
    gui\serialtcp_gui\__main__.py || exit /b 1

move /y "dist\serial-tcp-gui.exe" "serial-tcp-gui.exe"

call deactivate
rmdir /s /q dist
rmdir /s /q build
rmdir /s /q .buildenv
del serial-tcp-gui.spec

echo.
echo Built: %CD%\serial-tcp-gui.exe
