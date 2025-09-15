@echo off
echo ========================================
echo    Quick Build - Bill Software
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed
    pause
    exit /b 1
)

echo ✅ Python found
echo.

REM Install PyInstaller if not present
echo 📦 Checking PyInstaller...
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    python -m pip install pyinstaller
)

echo.
echo 🔨 Building executable...
echo This may take a few minutes...

REM Build the executable
python -m PyInstaller --onefile --windowed --name "BillSoftware" --add-data "images;images" --add-data "invoices;invoices" app/main.py

if exist "dist\BillSoftware.exe" (
    echo.
    echo ✅ SUCCESS! Executable created!
    echo 📁 Location: dist\BillSoftware.exe
    echo.
    echo 💼 You can now:
    echo    1. Copy dist\BillSoftware.exe to any computer
    echo    2. Double-click to run the software
    echo    3. No installation required!
    echo.
    
    REM Create a simple launcher
    echo @echo off > "Run Bill Software.bat"
    echo start "" "dist\BillSoftware.exe" >> "Run Bill Software.bat"
    
    echo ✅ Created "Run Bill Software.bat" for easy launching
) else (
    echo ❌ Build failed
)

echo.
pause
