#!/usr/bin/env python3
"""
Create Professional Client Package
Packages the software for distribution to clients
"""

import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

def create_client_package():
    """Create a professional package for clients"""
    
    # Create package directory
    package_dir = "BillSoftware_ClientPackage"
    if os.path.exists(package_dir):
        shutil.rmtree(package_dir)
    os.makedirs(package_dir)
    
    print("📦 Creating professional client package...")
    
    # Copy executable
    if os.path.exists("dist/BillSoftware.exe"):
        shutil.copy2("dist/BillSoftware.exe", f"{package_dir}/BillSoftware.exe")
        print("✅ Added executable")
    else:
        print("❌ Executable not found! Run quick_build.bat first")
        return False
    
    # Create professional README
    readme_content = f"""# Bill Software - Professional Edition

## 🚀 Welcome to Bill Software!

Thank you for choosing our professional billing and inventory management software. This powerful tool will help streamline your business operations.

## 📋 What's Included

✅ **Complete Billing System** - Generate professional invoices
✅ **Inventory Management** - Track products with images
✅ **Table Management** - Restaurant-style ordering system
✅ **Comprehensive Reports** - Daily sales and analytics
✅ **Data Export** - Export reports to CSV
✅ **Thermal Printer Support** - Ready for receipt printing

## 🚀 Quick Start

1. **Double-click** `BillSoftware.exe` to start
2. **No installation required** - Runs immediately
3. **All data saved locally** - Your information stays secure

## 💼 Key Features

### 📊 Inventory Management
- Add products with images
- Track stock levels
- Manage pricing
- Bulk import/export

### 🧾 Smart Billing
- Generate professional invoices
- Print to thermal printers
- Save invoice history
- Multiple payment methods

### 🍽️ Table Management
- Restaurant-style table system
- Kitchen order management
- Real-time order tracking
- Multiple table support

### 📈 Reports & Analytics
- Daily sales reports
- Complete bill history
- Export to CSV
- Business insights

## 🛠️ System Requirements

- **Operating System:** Windows 10/11 (64-bit)
- **Memory:** 4GB RAM minimum
- **Storage:** 100MB free space
- **Printer:** Thermal printer (optional)

## 📞 Support

For technical support or questions:
- **Email:** support@billsoftware.com
- **Phone:** +1-800-BILL-SOFT
- **Website:** www.billsoftware.com

## 📄 License

This software is licensed for single business use.
© 2024 Bill Software. All rights reserved.

---
**Version:** 1.0.0
**Package Date:** {datetime.now().strftime("%B %d, %Y")}
**Build:** Professional Edition
"""
    
    with open(f"{package_dir}/README.txt", "w", encoding="utf-8") as f:
        f.write(readme_content)
    
    # Create installation guide
    install_guide = """# Installation Guide

## Option 1: Simple Run (Recommended)
1. Double-click "BillSoftware.exe"
2. The software will start immediately
3. No installation required!

## Option 2: Professional Installation
1. Create a folder: C:\\BillSoftware\\
2. Copy BillSoftware.exe to that folder
3. Create a desktop shortcut
4. Run from desktop shortcut

## First Time Setup
1. Start the software
2. Go to Inventory tab
3. Add your products
4. Set up your company details
5. Start billing!

## Data Storage
- All data is stored locally on your computer
- Database file: bill_software.db
- Invoice files: invoices/ folder
- Images: images/ folder

## Backup Your Data
- Copy the entire software folder to backup
- Your data is always safe and portable
"""
    
    with open(f"{package_dir}/INSTALLATION_GUIDE.txt", "w", encoding="utf-8") as f:
        f.write(install_guide)
    
    # Create user manual
    user_manual = """# Bill Software - User Manual

## Getting Started

### 1. Inventory Management
- **Add Products:** Click "Add Product" button
- **Upload Images:** Drag & drop product images
- **Set Prices:** Enter product prices and stock
- **Edit Products:** Double-click to edit

### 2. Billing
- **Select Products:** Click on product images
- **Set Quantities:** Use +/- buttons
- **Generate Invoice:** Click "Generate Invoice"
- **Print:** Click "Print" button

### 3. Table Management
- **Select Table:** Click on table number
- **Add Items:** Click product images
- **View Order:** Check "Table Order" section
- **Generate Bill:** Click "Generate Bill"

### 4. Reports
- **Daily Sales:** View today's sales
- **All Bills:** Complete bill history
- **Export Data:** Click "Export CSV"

## Keyboard Shortcuts
- **Ctrl+N:** New product
- **Ctrl+S:** Save
- **Ctrl+P:** Print
- **F5:** Refresh

## Troubleshooting
- **Software won't start:** Run as Administrator
- **Images not showing:** Check image file formats
- **Print issues:** Check printer connection
- **Data lost:** Check backup folder

## Tips & Tricks
- Use product images for faster billing
- Set up table numbers for restaurants
- Export reports regularly
- Keep backups of your data
"""
    
    with open(f"{package_dir}/USER_MANUAL.txt", "w", encoding="utf-8") as f:
        f.write(user_manual)
    
    # Create license file
    license_content = """# Software License Agreement

## Bill Software - Professional Edition
Single User License

### License Terms
1. This software is licensed for use by one business entity
2. You may install and use the software on multiple computers within your business
3. You may not distribute, sell, or share this software with other businesses
4. All rights reserved by the software developer

### Permitted Uses
- Business billing and inventory management
- Generating invoices and receipts
- Managing product catalogs
- Creating business reports
- Data backup and restoration

### Restrictions
- No reverse engineering
- No redistribution
- No modification of the software
- No use beyond licensed scope

### Support
Technical support is provided for licensed users only.

### Warranty
Software provided "as is" without warranty.

---
By using this software, you agree to these terms.
© 2024 Bill Software. All rights reserved.
"""
    
    with open(f"{package_dir}/LICENSE.txt", "w", encoding="utf-8") as f:
        f.write(license_content)
    
    # Create batch file for easy launching
    launcher_content = """@echo off
title Bill Software - Professional Edition
echo.
echo ========================================
echo    Bill Software - Professional Edition
echo ========================================
echo.
echo Starting Bill Software...
echo.

start "" "BillSoftware.exe"

echo Software started successfully!
echo You can close this window.
timeout /t 3 >nul
"""
    
    with open(f"{package_dir}/Start Bill Software.bat", "w", encoding="utf-8") as f:
        f.write(launcher_content)
    
    print("✅ Created professional documentation")
    
    # Create ZIP package
    zip_filename = f"BillSoftware_v1.0_{datetime.now().strftime('%Y%m%d')}.zip"
    
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(package_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, package_dir)
                zipf.write(file_path, arcname)
    
    print(f"✅ Created ZIP package: {zip_filename}")
    
    # Create delivery instructions
    delivery_instructions = f"""# Delivery Instructions for Client

## Package Contents
- BillSoftware.exe (Main application)
- README.txt (Overview and features)
- INSTALLATION_GUIDE.txt (Setup instructions)
- USER_MANUAL.txt (Detailed usage guide)
- LICENSE.txt (Software license)
- Start Bill Software.bat (Easy launcher)

## How to Send to Client

### Option 1: Email (Small files)
- Attach the ZIP file to email
- Include brief description
- Provide installation instructions

### Option 2: Cloud Storage (Recommended)
- Upload to Google Drive, Dropbox, or OneDrive
- Share download link with client
- Include access instructions

### Option 3: USB Drive
- Copy ZIP file to USB drive
- Deliver physically to client
- Include printed instructions

### Option 4: File Transfer Service
- Use WeTransfer, SendAnywhere, or similar
- Send download link to client
- Set expiration date if needed

## Client Communication Template

Subject: Your Bill Software - Professional Edition is Ready!

Dear [Client Name],

Your professional billing software is ready for delivery!

📦 **Package:** {zip_filename}
📋 **Size:** ~50MB
🚀 **Installation:** No installation required - just run!

**What's Included:**
✅ Complete billing system
✅ Inventory management
✅ Table management for restaurants
✅ Professional reports
✅ Thermal printer support

**Next Steps:**
1. Download the attached file
2. Extract to a folder on your computer
3. Double-click "Start Bill Software.bat"
4. Follow the user manual for setup

**Support:**
- Read the USER_MANUAL.txt for detailed instructions
- Contact us for any technical support
- We're here to help you succeed!

Best regards,
[Your Name]
[Your Company]
[Contact Information]

---
Package created: {datetime.now().strftime("%B %d, %Y at %I:%M %p")}
"""
    
    with open("DELIVERY_INSTRUCTIONS.txt", "w", encoding="utf-8") as f:
        f.write(delivery_instructions)
    
    print("\n🎉 CLIENT PACKAGE CREATED SUCCESSFULLY!")
    print("=" * 50)
    print(f"📁 Package folder: {package_dir}/")
    print(f"📦 ZIP file: {zip_filename}")
    print("📋 Delivery instructions: DELIVERY_INSTRUCTIONS.txt")
    print("\n💼 Ready to send to client!")
    
    return True

if __name__ == "__main__":
    create_client_package()
