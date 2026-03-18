:: generates exe from serial_tcp_clients package using a clean venv
:: Usage: build.bat [path\to\python.exe]
@echo off

set PYTHONIOENCODING=utf-8

:: Use provided python path or default to "python"
set PYTHON=python
if not "%~1"=="" set PYTHON=%~1

:: Check Python version >= 3.9
for /f "tokens=2 delims= " %%v in ('"%PYTHON%" --version 2^>^&1') do set PYVER=%%v
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    if %%a LSS 3 (
        echo ERROR: Python ^>=3.9 required, found %PYVER%
        echo Install Python 3.9+ or pass path: %~nx0 C:\Python310\python.exe
        exit /b 1
    )
    if %%a==3 if %%b LSS 9 (
        echo ERROR: Python ^>=3.9 required, found %PYVER%
        echo Install Python 3.9+ or pass path: %~nx0 C:\Python310\python.exe
        exit /b 1
    )
)
echo Using Python %PYVER% (%PYTHON%)

"%PYTHON%" -m venv .venv
call .venv\Scripts\activate.bat

pip install pyinstaller
pip install pyserial>=3.3

pyinstaller --onefile --console ^
    --name serial-tcp-server ^
    --paths "." ^
    --hidden-import serial.tools.list_ports ^
    serialtcp\__main__.py

move "%~dp0dist\serial-tcp-server.exe" "%~dp0"

rmdir /s /q "%~dp0dist\"
rmdir /s /q "%~dp0build\"
rmdir /s /q "%~dp0.venv\"

del serial-tcp-server.spec
