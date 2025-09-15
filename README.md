## Simple Billing & Inventory (Free, Offline)

Data is saved locally on your computer (SQLite). No internet or payments needed.

### What you can do
- Add products with name, price, and stock
- Make a bill (cart), checkout, and auto-update stock
- See recent bills and what was sold
- Save/Load products to a CSV file (backup/restore)

### How to start (Windows)
1. Open PowerShell and go to your project folder:
   ```powershell
   cd "C:\Users\Shiven\Desktop\projects\bill-software"
   ```
2. (Optional) Create and use a virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
3. Run the app:
   ```powershell
   python -m app.main
   ```

Folders `data`, `invoices`, and `backups` will be created automatically.

### Tips
- Price can be a decimal number (like 12.50). Stock and quantity are whole numbers.
- Invoices are saved as text files inside the `invoices` folder.

### Troubleshooting
- If the window does not open, make sure you installed Python from `python.org` or the Microsoft Store. Tkinter is included by default on Windows.


