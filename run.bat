@echo off
REM EuroTaxCalc - Launcher for Windows

REM Get script directory
cd /d "%~dp0"

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python is not installed. Please install Python 3.12 or higher.
    echo    Visit: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

REM Install/verify dependencies (fast if already installed)
echo Checking dependencies...
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo ❌ Failed to install dependencies.
    pause
    exit /b 1
)

REM Run the application
echo 🚀 Starting EuroTaxCalc...
python main.py

REM Keep window open if there was an error
if %errorlevel% neq 0 (
    echo.
    echo ❌ Application encountered an error.
    pause
)
