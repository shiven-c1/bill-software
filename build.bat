@echo off
echo ========================================
echo    Building Bill Software
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://python.org
    pause
    exit /b 1
)

echo ✅ Python found
echo.

REM Run the build script
python build_software.py

echo.
echo Press any key to exit...
pause >nul
