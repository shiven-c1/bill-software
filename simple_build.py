#!/usr/bin/env python3
"""
Simple Build Script for Bill Software
Creates a basic executable without external dependencies
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def create_simple_icon():
    """Create a simple ICO file using basic method"""
    # Create a simple 16x16 icon using base64 encoded data
    icon_data = b'\x00\x00\x01\x00\x01\x00\x10\x10\x00\x00\x01\x00\x20\x00\x68\x04\x00\x00\x16\x00\x00\x00\x28\x00\x00\x00\x10\x00\x00\x00\x20\x00\x00\x00\x01\x00\x20\x00\x00\x00\x00\x00\x00\x04\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
    
    with open("icon.ico", "wb") as f:
        f.write(icon_data)
    
    print("✅ Created simple icon")

def create_spec_file():
    """Create PyInstaller spec file"""
    spec_content = '''# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['app/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('images', 'images'),
        ('invoices', 'invoices'),
    ],
    hiddenimports=[
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'matplotlib',
        'matplotlib.backends.backend_tkagg',
        'tkinter',
        'tkinter.ttk',
        'sqlite3',
        'csv',
        'os',
        'datetime',
        'json',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='BillSoftware',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
'''
    
    with open("BillSoftware.spec", "w", encoding="utf-8") as f:
        f.write(spec_content)
    
    print("✅ Created PyInstaller spec file")

def build_executable():
    """Build the executable using PyInstaller"""
    print("🔨 Building executable...")
    
    try:
        # Clean previous builds
        if os.path.exists("dist"):
            shutil.rmtree("dist")
        if os.path.exists("build"):
            shutil.rmtree("build")
        
        # Build executable
        subprocess.run([
            sys.executable, "-m", "PyInstaller",
            "--clean",
            "--noconfirm",
            "BillSoftware.spec"
        ], check=True)
        
        print("✅ Executable built successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Build failed: {e}")
        return False

def create_installer():
    """Create installer script"""
    installer_content = '''@echo off
echo ========================================
echo    Bill Software - Professional Edition
echo ========================================
echo.
echo Installing Bill Software...
echo.

REM Create installation directory
if not exist "C:\\BillSoftware" mkdir "C:\\BillSoftware"

REM Copy executable
copy "BillSoftware.exe" "C:\\BillSoftware\\"

REM Create desktop shortcut
echo [InternetShortcut] > "%USERPROFILE%\\Desktop\\Bill Software.url"
echo URL=file:///C:/BillSoftware/BillSoftware.exe >> "%USERPROFILE%\\Desktop\\Bill Software.url"

echo.
echo ✅ Installation completed!
echo ✅ Desktop shortcut created!
echo.
echo You can now run Bill Software from your desktop.
pause
'''
    
    with open("install.bat", "w", encoding="utf-8") as f:
        f.write(installer_content)
    
    print("✅ Created installer script")

def main():
    """Main build process"""
    print("🏗️  Building Bill Software")
    print("=" * 30)
    
    # Check if PyInstaller is available
    try:
        subprocess.run([sys.executable, "-c", "import PyInstaller"], check=True)
        print("✅ PyInstaller found")
    except subprocess.CalledProcessError:
        print("❌ PyInstaller not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
    
    # Create icon
    create_simple_icon()
    
    # Create spec file
    create_spec_file()
    
    # Build executable
    if build_executable():
        # Create installer
        create_installer()
        
        print("\n🎉 BUILD COMPLETED!")
        print("=" * 30)
        print("📁 Files created:")
        print("   • dist/BillSoftware.exe - Main executable")
        print("   • install.bat - Installation script")
        print("\n💼 Ready to use!")
        print("   Run 'install.bat' to install the software")
        
    else:
        print("\n❌ Build failed.")

if __name__ == "__main__":
    main()
