#!/usr/bin/env python3
"""
Professional Build Script for Bill Software
Creates a distributable executable with icon
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def create_icon():
    """Create a professional application icon"""
    icon_svg = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="256" height="256" viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#2b74ff;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#1976d2;stop-opacity:1" />
    </linearGradient>
    <linearGradient id="icon" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#ffffff;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#e3f2fd;stop-opacity:1" />
    </linearGradient>
  </defs>
  
  <!-- Background -->
  <rect width="256" height="256" rx="40" fill="url(#bg)"/>
  
  <!-- Document/Invoice Icon -->
  <rect x="60" y="50" width="136" height="180" rx="8" fill="url(#icon)" stroke="#1976d2" stroke-width="3"/>
  
  <!-- Lines on document -->
  <rect x="75" y="80" width="106" height="4" rx="2" fill="#1976d2"/>
  <rect x="75" y="95" width="80" height="4" rx="2" fill="#1976d2"/>
  <rect x="75" y="110" width="90" height="4" rx="2" fill="#1976d2"/>
  <rect x="75" y="125" width="70" height="4" rx="2" fill="#1976d2"/>
  
  <!-- Total line -->
  <rect x="75" y="180" width="106" height="6" rx="3" fill="#2b74ff"/>
  
  <!-- Dollar sign -->
  <text x="128" y="160" font-family="Arial, sans-serif" font-size="48" font-weight="bold" text-anchor="middle" fill="#2b74ff">₹</text>
  
  <!-- App name -->
  <text x="128" y="220" font-family="Arial, sans-serif" font-size="16" font-weight="bold" text-anchor="middle" fill="white">Bill Software</text>
</svg>'''
    
    with open("icon.svg", "w", encoding="utf-8") as f:
        f.write(icon_svg)
    
    print("✅ Created professional icon (icon.svg)")

def install_dependencies():
    """Install required dependencies for building"""
    print("📦 Installing build dependencies...")
    
    dependencies = [
        "pyinstaller",
        "pillow",
        "matplotlib"
    ]
    
    for dep in dependencies:
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", dep], check=True)
            print(f"✅ Installed {dep}")
        except subprocess.CalledProcessError:
            print(f"❌ Failed to install {dep}")

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
    icon='icon.ico'
)
'''
    
    with open("BillSoftware.spec", "w", encoding="utf-8") as f:
        f.write(spec_content)
    
    print("✅ Created PyInstaller spec file")

def convert_icon():
    """Convert SVG icon to ICO format"""
    try:
        from PIL import Image
        import cairosvg
        
        # Convert SVG to PNG
        cairosvg.svg2png(url="icon.svg", write_to="icon.png", output_width=256, output_height=256)
        
        # Convert PNG to ICO
        img = Image.open("icon.png")
        img.save("icon.ico", format="ICO", sizes=[(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)])
        
        print("✅ Converted icon to ICO format")
        return True
    except ImportError:
        print("❌ Installing cairosvg for icon conversion...")
        subprocess.run([sys.executable, "-m", "pip", "install", "cairosvg"], check=True)
        return convert_icon()
    except Exception as e:
        print(f"❌ Icon conversion failed: {e}")
        return False

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

def create_installer_script():
    """Create a simple installer script"""
    installer_content = '''@echo off
echo ========================================
echo    Bill Software - Professional Edition
echo ========================================
echo.
echo Installing Bill Software...
echo.

REM Create installation directory
if not exist "C:\\Program Files\\BillSoftware" mkdir "C:\\Program Files\\BillSoftware"

REM Copy executable
copy "BillSoftware.exe" "C:\\Program Files\\BillSoftware\\"

REM Create desktop shortcut
echo [InternetShortcut] > "%USERPROFILE%\\Desktop\\Bill Software.url"
echo URL=file:///C:/Program Files/BillSoftware/BillSoftware.exe >> "%USERPROFILE%\\Desktop\\Bill Software.url"
echo IconFile=C:\\Program Files\\BillSoftware\\BillSoftware.exe >> "%USERPROFILE%\\Desktop\\Bill Software.url"
echo IconIndex=0 >> "%USERPROFILE%\\Desktop\\Bill Software.url"

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

def create_readme():
    """Create a professional README for distribution"""
    readme_content = '''# Bill Software - Professional Edition

## 🚀 Features
- **Inventory Management** - Add, edit, and manage products with images
- **Smart Billing** - Generate professional invoices with thermal printer support
- **Table Management** - Restaurant-style table ordering system
- **Comprehensive Reports** - Daily sales, all bills, and detailed analytics
- **Data Export** - Export reports to CSV format
- **Professional UI** - Modern, user-friendly interface

## 📋 System Requirements
- Windows 10/11 (64-bit)
- 4GB RAM minimum
- 100MB free disk space
- Thermal printer (optional)

## 🛠️ Installation
1. Run `install.bat` as Administrator
2. The software will be installed to `C:\\Program Files\\BillSoftware\\`
3. A desktop shortcut will be created automatically

## 💼 For Business Use
This software is designed for:
- Restaurants and cafes
- Retail stores
- Small to medium businesses
- Professional billing and inventory management

## 📞 Support
For technical support or licensing inquiries, contact the developer.

## 📄 License
Professional License - Single User
© 2024 Bill Software. All rights reserved.

---
**Version:** 1.0.0
**Build Date:** ''' + str(Path().cwd()) + '''
'''
    
    with open("README.txt", "w", encoding="utf-8") as f:
        f.write(readme_content)
    
    print("✅ Created professional README")

def main():
    """Main build process"""
    print("🏗️  Building Bill Software - Professional Edition")
    print("=" * 50)
    
    # Step 1: Create icon
    create_icon()
    
    # Step 2: Install dependencies
    install_dependencies()
    
    # Step 3: Convert icon
    if not convert_icon():
        print("⚠️  Continuing without custom icon...")
    
    # Step 4: Create spec file
    create_spec_file()
    
    # Step 5: Build executable
    if build_executable():
        # Step 6: Create installer
        create_installer_script()
        
        # Step 7: Create README
        create_readme()
        
        print("\n🎉 BUILD COMPLETED SUCCESSFULLY!")
        print("=" * 50)
        print("📁 Files created:")
        print("   • dist/BillSoftware.exe - Main executable")
        print("   • install.bat - Installation script")
        print("   • README.txt - User documentation")
        print("   • icon.ico - Application icon")
        print("\n💼 Ready for distribution!")
        print("   Run 'install.bat' to install the software")
        
    else:
        print("\n❌ Build failed. Please check the errors above.")

if __name__ == "__main__":
    main()
