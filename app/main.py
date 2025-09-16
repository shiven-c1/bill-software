import os
import sqlite3
from datetime import datetime, timedelta
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    plt = None
    FigureCanvasTkAgg = None
    Figure = None

class ToolTip:
    """Create a tooltip for a given widget"""
    def __init__(self, widget, text='widget info'):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        self.widget.bind('<Enter>', self.enter)
        self.widget.bind('<Leave>', self.leave)

    def enter(self, event=None):
        self.showtip()

    def leave(self, event=None):
        self.hidetip()

    def showtip(self):
        if self.tipwindow or not self.text:
            return
        x, y, cx, cy = self.widget.bbox("insert")
        x = x + self.widget.winfo_rootx() + 25
        y = y + cy + self.widget.winfo_rooty() + 25
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry("+%d+%d" % (x, y))
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                        background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                        font=("Segoe UI", 9))
        label.pack(ipadx=1)

    def hidetip(self):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()


APP_TITLE = "Simple Billing & Inventory"
DB_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DB_PATH = os.path.abspath(os.path.join(DB_DIR, "app.db"))
INVOICE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "invoices"))
BACKUP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backups"))
IMAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "images"))


def ensure_dirs():
    os.makedirs(DB_DIR, exist_ok=True)
    os.makedirs(INVOICE_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    os.makedirs(IMAGE_DIR, exist_ok=True)

def load_printer_icon():
    """Load printer icon from PNG file"""
    try:
        if Image and ImageTk:
            # Load printer icon from PNG file
            icon_path = os.path.join(os.path.dirname(__file__), "..", "images", "printer_icon.png")
            if os.path.exists(icon_path):
                img = Image.open(icon_path)
                # Resize to larger size for better visibility
                img = img.resize((50, 50), Image.Resampling.LANCZOS)
                return ImageTk.PhotoImage(img)
        return None
    except Exception:
        return None


def get_conn():
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            price REAL NOT NULL CHECK(price >= 0),
            stock INTEGER NOT NULL CHECK(stock >= 0)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            total REAL NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS bill_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            qty INTEGER NOT NULL CHECK(qty > 0),
            price REAL NOT NULL,
            subtotal REAL NOT NULL,
            FOREIGN KEY (bill_id) REFERENCES bills(id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
        """
    )
    conn.commit()
    # Add image_path column if it doesn't exist (simple migration)
    cur.execute("PRAGMA table_info(products)")
    cols = [row[1] for row in cur.fetchall()]
    if "image_path" not in cols:
        cur.execute("ALTER TABLE products ADD COLUMN image_path TEXT")
        conn.commit()
    # Settings table for company profile
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    conn.commit()
    conn.close()


# Inventory operations
def list_products(search_term: str = ""):
    conn = get_conn()
    cur = conn.cursor()
    if search_term:
        cur.execute(
            "SELECT * FROM products WHERE name LIKE ? ORDER BY name ASC",
            (f"%{search_term}%",),
        )
    else:
        cur.execute("SELECT * FROM products ORDER BY name ASC")
    rows = cur.fetchall()
    conn.close()
    return rows


def add_product(name: str, price: float, stock: int, image_path: str | None = None):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO products(name, price, stock, image_path) VALUES (?, ?, ?, ?)",
            (name.strip(), float(price), int(stock), image_path),
        )
        conn.commit()
        return True, None
    except sqlite3.IntegrityError as e:
        return False, str(e)
    finally:
        conn.close()


def update_product(pid: int, name: str, price: float, stock: int, image_path: str | None):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE products SET name=?, price=?, stock=?, image_path=? WHERE id=?",
            (name.strip(), float(price), int(stock), image_path, int(pid)),
        )
        conn.commit()
        return True, None
    except sqlite3.IntegrityError as e:
        return False, str(e)
    finally:
        conn.close()


def delete_product(pid: int):
    conn = get_conn()
    cur = conn.cursor()
    try:
        # First delete all bill_items that reference this product
        cur.execute("DELETE FROM bill_items WHERE product_id=?", (int(pid),))
        deleted_items = cur.rowcount
        print(f"Deleted {deleted_items} bill_items for product {pid}")
        
        # Then delete the product itself
        cur.execute("DELETE FROM products WHERE id=?", (int(pid),))
        conn.commit()
        print(f"Product {pid} deleted successfully")
    except Exception as e:
        print(f"Error deleting product {pid}: {e}")
        conn.rollback()
    finally:
        conn.close()


# Billing operations
def create_bill(cart_items):
    # cart_items: list of dicts {product_id, name, price, qty}
    conn = get_conn()
    cur = conn.cursor()
    try:
        total = 0.0
        # Check stock first
        for item in cart_items:
            cur.execute("SELECT stock FROM products WHERE id=?", (item["product_id"],))
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"Product not found: {item['name']}")
            if row["stock"] < item["qty"]:
                raise ValueError(f"Not enough stock for {item['name']}")
            total += float(item["price"]) * int(item["qty"])

        cur.execute(
            "INSERT INTO bills(created_at, total) VALUES (?, ?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), total),
        )
        bill_id = cur.lastrowid

        for item in cart_items:
            subtotal = float(item["price"]) * int(item["qty"])
            cur.execute(
                "INSERT INTO bill_items(bill_id, product_id, qty, price, subtotal) VALUES (?, ?, ?, ?, ?)",
                (bill_id, item["product_id"], int(item["qty"]), float(item["price"]), subtotal),
            )
            # decrease stock
            cur.execute(
                "UPDATE products SET stock = stock - ? WHERE id=?",
                (int(item["qty"]), item["product_id"]),
            )

        conn.commit()
        return bill_id, total
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_recent_bills(limit: int = 50):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, created_at, total FROM bills ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_daily_sales(date_str: str = None):
    """Get sales for a specific date (YYYY-MM-DD) or today if None"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, created_at, total FROM bills WHERE DATE(created_at) = ? ORDER BY id ASC",
        (date_str,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_sales_summary(start_date: str, end_date: str):
    """Get sales summary between two dates"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT DATE(created_at) as sale_date, COUNT(*) as bill_count, SUM(total) as total_sales FROM bills WHERE DATE(created_at) BETWEEN ? AND ? GROUP BY DATE(created_at) ORDER BY sale_date DESC",
        (start_date, end_date),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_bill_items(bill_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT bi.qty, bi.price, bi.subtotal, p.name
        FROM bill_items bi
        JOIN products p ON p.id = bi.product_id
        WHERE bi.bill_id = ?
        ORDER BY bi.id ASC
        """,
        (bill_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows

def get_all_bills():
    """Get all bills with complete details"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT id, created_at, total, 
           (SELECT COUNT(*) FROM bill_items WHERE bill_id = bills.id) as item_count,
           (SELECT SUM(qty) FROM bill_items WHERE bill_id = bills.id) as total_qty
           FROM bills ORDER BY id DESC"""
    )
    rows = cur.fetchall()
    conn.close()
    return rows

def get_comprehensive_bill_items(bill_id: int):
    """Get comprehensive bill items with product details"""
    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute(
        """
        SELECT bi.id, bi.qty, bi.price, bi.subtotal, 
               p.id as product_id, p.name, p.stock as current_stock,
               p.image_path
        FROM bill_items bi
        JOIN products p ON p.id = bi.product_id
        WHERE bi.bill_id = ?
        ORDER BY bi.id ASC
        """,
        (bill_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows

def get_sales_analytics():
    """Get comprehensive sales analytics"""
    conn = get_conn()
    cur = conn.cursor()
    
    # Total sales summary
    cur.execute("""
        SELECT 
            COUNT(*) as total_bills,
            SUM(total) as total_revenue,
            AVG(total) as avg_bill_value,
            MIN(created_at) as first_sale,
            MAX(created_at) as last_sale
        FROM bills
    """)
    summary = cur.fetchone()
    
    # Top selling products
    cur.execute("""
        SELECT p.name, SUM(bi.qty) as total_sold, SUM(bi.subtotal) as total_revenue
        FROM bill_items bi
        JOIN products p ON p.id = bi.product_id
        GROUP BY p.id, p.name
        ORDER BY total_sold DESC
        LIMIT 10
    """)
    top_products = cur.fetchall()
    
    # Daily sales trend (last 30 days)
    cur.execute("""
        SELECT DATE(created_at) as sale_date, 
               COUNT(*) as bill_count, 
               SUM(total) as daily_revenue
        FROM bills 
        WHERE created_at >= date('now', '-30 days')
        GROUP BY DATE(created_at)
        ORDER BY sale_date DESC
    """)
    daily_trend = cur.fetchall()
    
    conn.close()
    return summary, top_products, daily_trend


def save_invoice_text(bill_id: int):
    rows = get_bill_items(bill_id)
    bills = [b for b in get_recent_bills(10000) if b["id"] == bill_id]
    if not bills:
        return None
    bill = bills[0]
    # Create date-based folder structure
    bill_date = datetime.strptime(bill["created_at"], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
    date_folder = os.path.join(INVOICE_DIR, bill_date)
    os.makedirs(date_folder, exist_ok=True)
    filepath = os.path.join(date_folder, f"invoice-{bill_id}.txt")
    # Load company profile
    company = load_settings()
    lines = []
    if company.get("company_name"):
        lines.append(company.get("company_name"))
        addr = company.get("company_address") or ""
        phone = company.get("company_phone") or ""
        if addr:
            lines.append(addr)
        if phone:
            lines.append(f"Phone: {phone}")
        lines.append("")
    lines.append("==== INVOICE ====")
    lines.append(f"Bill ID: {bill_id}")
    lines.append(f"Date: {bill['created_at']}")
    lines.append("")
    lines.append("Items:")
    for r in rows:
        lines.append(f"- {r['name']} x {r['qty']} @ {r['price']:.2f} = {r['subtotal']:.2f}")
    lines.append("")
    lines.append(f"Total: {bill['total']:.2f}")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return filepath


# Backup/Restore
def backup_products_csv(path: str):
    rows = list_products("")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "price", "stock"])
        for r in rows:
            writer.writerow([r["name"], r["price"], r["stock"]])


def restore_products_csv(path: str):
    conn = get_conn()
    cur = conn.cursor()
    inserted = 0
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                cur.execute(
                    "INSERT OR IGNORE INTO products(name, price, stock) VALUES (?, ?, ?)",
                    (row["name"].strip(), float(row["price"]), int(row["stock"])),
                )
                inserted += cur.rowcount
            except Exception:
                pass
    conn.commit()
    conn.close()
    return inserted


# Settings persistence
def load_settings() -> dict:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM settings")
    rows = cur.fetchall()
    conn.close()
    data = {}
    for r in rows:
        data[r["key"]] = r["value"]
    return data


def save_settings(values: dict):
    conn = get_conn()
    cur = conn.cursor()
    for k, v in values.items():
        cur.execute("INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
    conn.commit()
    conn.close()


class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.master = master
        self.master.title(APP_TITLE)
        self.master.geometry("1000x650")
        self.pack(fill=tk.BOTH, expand=True)

        self.build_styles()
        self.build_header()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.inventory_tab = ttk.Frame(self.notebook)
        self.billing_tab = ttk.Frame(self.notebook)
        self.tables_tab = ttk.Frame(self.notebook)
        self.reports_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.inventory_tab, text="📦 Inventory", padding=[10, 8])
        self.notebook.add(self.billing_tab, text="🧾 Billing", padding=[10, 8])
        self.notebook.add(self.tables_tab, text="🍽️ Tables", padding=[10, 8])
        self.notebook.add(self.reports_tab, text="📊 Reports", padding=[10, 8])

        self.build_inventory_tab()
        self.build_billing_tab()
        self.build_tables_tab()
        self.build_reports_tab()
        self.build_menu()
        self.build_statusbar()
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

    def build_styles(self):
        self.base_font = ("Segoe UI", 10)
        self.heading_font = ("Segoe UI", 11, "bold")
        self.title_font = ("Segoe UI", 16, "bold")
        self.subtitle_font = ("Segoe UI", 10)

        style = ttk.Style(self.master)
        style.configure("TButton", font=self.base_font, padding=6)
        style.configure("TLabel", font=self.base_font)
        style.configure("Treeview", font=self.base_font, rowheight=26)
        style.configure("Treeview.Heading", font=self.heading_font)
        
        # Tab styling
        style.configure("TNotebook", tabposition="n")
        style.configure("TNotebook.Tab", padding=[15, 10], font=("Segoe UI", 11, "bold"), width=12)
        style.map("TNotebook.Tab", 
                 background=[("selected", "#2b74ff"), ("active", "#e3f2fd"), ("pressed", "#2b74ff")],
                 foreground=[("selected", "white"), ("active", "#1976d2"), ("pressed", "white")],
                 relief=[("pressed", "flat"), ("!pressed", "flat")],
                 borderwidth=[("pressed", 0), ("!pressed", 0)],
                 focuscolor="none")
        
        # Custom button styles
        style.configure("Success.TButton", foreground="white", background="#4CAF50")
        style.configure("Danger.TButton", foreground="white", background="#f44336")
        style.configure("Info.TButton", foreground="white", background="#2196F3")
        style.configure("Product.TFrame", relief="raised", borderwidth=2)

    def build_header(self):
        header = tk.Frame(self, bg="#2b74ff", height=80)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        # Main content frame
        content_frame = tk.Frame(header, bg="#2b74ff")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Left side - Title and description
        left_frame = tk.Frame(content_frame, bg="#2b74ff")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        tk.Label(left_frame, text="🏪 Professional Billing Software", 
                font=("Segoe UI", 20, "bold"), fg="white", bg="#2b74ff").pack(anchor=tk.W)
        tk.Label(left_frame, text="Complete Inventory & Restaurant Management Solution", 
                font=("Segoe UI", 12), fg="#e3f2fd", bg="#2b74ff").pack(anchor=tk.W, pady=(2, 0))
        
        # Right side - Status, version, and help
        right_frame = tk.Frame(content_frame, bg="#2b74ff")
        right_frame.pack(side=tk.RIGHT)
        
        # Help button
        help_btn = tk.Button(right_frame, text="❓ Help", command=self.show_help,
                           font=("Segoe UI", 10, "bold"), fg="white", bg="#1976D2",
                           relief="raised", bd=2, padx=15, pady=5, cursor="hand2")
        help_btn.pack(anchor=tk.E, pady=(0, 5))
        ToolTip(help_btn, "Click to open the user guide and help documentation")
        
        version_label = tk.Label(right_frame, text="Version 2.0 Professional", 
                               font=("Segoe UI", 9), fg="#e3f2fd", bg="#2b74ff")
        version_label.pack(anchor=tk.E, pady=(2, 0))

    def build_statusbar(self):
        self.status_var = tk.StringVar(value="🟢 System Ready - All modules loaded successfully")
        bar = tk.Frame(self, bg="#f5f5f5", height=25)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)
        
        # Status text
        status_label = tk.Label(bar, textvariable=self.status_var, 
                              font=("Segoe UI", 9), fg="#333333", bg="#f5f5f5")
        status_label.pack(side=tk.LEFT, padx=10, pady=5)
        
        # Right side info
        info_frame = tk.Frame(bar, bg="#f5f5f5")
        info_frame.pack(side=tk.RIGHT, padx=10, pady=5)
        
        # Current time
        self.time_var = tk.StringVar()
        time_label = tk.Label(info_frame, textvariable=self.time_var, 
                            font=("Segoe UI", 9), fg="#666666", bg="#f5f5f5")
        time_label.pack(side=tk.RIGHT)
        
        # Update time
        self.update_time()

    def update_time(self):
        """Update the current time in status bar"""
        if hasattr(self, "time_var"):
            current_time = datetime.now().strftime("%H:%M:%S")
            self.time_var.set(f"🕐 {current_time}")
        # Schedule next update
        self.after(1000, self.update_time)

    def set_status(self, text: str, status_type="info"):
        """Set status message with different types"""
        if hasattr(self, "status_var"):
            icons = {
                "info": "ℹ️",
                "success": "✅", 
                "warning": "⚠️",
                "error": "❌",
                "loading": "⏳"
            }
            icon = icons.get(status_type, "ℹ️")
            self.status_var.set(f"{icon} {text}")

    def show_help(self, tab_index=0):
        """Show help dialog with user guide"""
        help_window = tk.Toplevel(self)
        help_window.title("📚 Help & User Guide")
        help_window.geometry("800x600")
        help_window.resizable(True, True)
        
        # Main frame
        main_frame = ttk.Frame(help_window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Title
        title_label = ttk.Label(main_frame, text="📚 Professional Billing Software - User Guide", 
                               font=("Segoe UI", 16, "bold"))
        title_label.pack(pady=(0, 20))
        
        # Create notebook for different help sections
        help_notebook = ttk.Notebook(main_frame)
        help_notebook.pack(fill=tk.BOTH, expand=True)
        
        # Getting Started tab
        getting_started = ttk.Frame(help_notebook)
        help_notebook.add(getting_started, text="🚀 Getting Started")
        
        getting_started_text = tk.Text(getting_started, wrap=tk.WORD, font=("Segoe UI", 10), 
                                     padx=10, pady=10, bg="#f8f9fa")
        getting_started_text.pack(fill=tk.BOTH, expand=True)
        
        getting_started_content = """
🏪 Welcome to Professional Billing Software!

This software helps you manage your business with:
• 📦 Inventory Management
• 🧾 Billing & Invoicing  
• 🍽️ Restaurant Table Management
• 📊 Sales Reports & Analytics

QUICK START GUIDE:

1. 📦 INVENTORY TAB:
   • Add your products with names, prices, and stock
   • Upload product images for better identification
   • Search and filter products easily
   • Export/Import data for backup

2. 🧾 BILLING TAB:
   • Click on product images to add to cart
   • Generate professional invoices
   • Print bills directly to thermal printer
   • Remove items from cart as needed

3. 🍽️ TABLES TAB:
   • Manage restaurant tables (1-8)
   • Add orders to specific tables
   • Generate bills for each table
   • Print kitchen orders

4. 📊 REPORTS TAB:
   • View daily sales reports
   • See all bills and transactions
   • Click on any bill to see details
   • Export reports to CSV

TIPS:
• Use the search bar to quickly find products
• Hover over buttons to see helpful tooltips
• All data is automatically saved
• Check the status bar for system messages
        """
        
        getting_started_text.insert(tk.END, getting_started_content)
        getting_started_text.config(state=tk.DISABLED)
        
        # Features tab
        features = ttk.Frame(help_notebook)
        help_notebook.add(features, text="✨ Features")
        
        features_text = tk.Text(features, wrap=tk.WORD, font=("Segoe UI", 10), 
                              padx=10, pady=10, bg="#f8f9fa")
        features_text.pack(fill=tk.BOTH, expand=True)
        
        features_content = """
🎯 KEY FEATURES:

📦 INVENTORY MANAGEMENT:
• Add, edit, delete products
• Product images support
• Stock tracking
• Search and filter
• CSV import/export
• Duplicate detection

🧾 BILLING SYSTEM:
• Visual product selection
• Real-time cart calculation
• Professional invoice generation
• Thermal printer support
• Invoice preview
• Automatic numbering

🍽️ RESTAURANT MANAGEMENT:
• 8 table management system
• Order tracking per table
• Kitchen order printing
• Table status indicators
• Direct bill generation
• Order history

📊 REPORTING & ANALYTICS:
• Daily sales reports
• Complete transaction history
• Bill details viewer
• CSV export
• Sales analytics
• Date-based filtering

🔧 TECHNICAL FEATURES:
• SQLite database
• Automatic backups
• Error handling
• Data validation
• Professional UI/UX
• Cross-platform support
        """
        
        features_text.insert(tk.END, features_content)
        features_text.config(state=tk.DISABLED)
        
        # Contact tab
        contact = ttk.Frame(help_notebook)
        help_notebook.add(contact, text="📞 Contact")
        
        contact_text = tk.Text(contact, wrap=tk.WORD, font=("Segoe UI", 10), 
                             padx=10, pady=10, bg="#f8f9fa")
        contact_text.pack(fill=tk.BOTH, expand=True)
        
        contact_content = """
📞 CONTACT INFORMATION

For technical support or questions about the software, please contact us:

📱 Customer Care Number 1: 7020685839

📱 Customer Care Number 2: 9022966119

🕒 Support Hours:
• Monday - Friday: 9:00 AM - 6:00 PM
• Saturday: 10:00 AM - 4:00 PM
• Sunday: Closed

💬 What we can help with:
• Software installation and setup
• Feature explanations and tutorials
• Technical issues and troubleshooting
• Custom modifications and enhancements
• Data backup and recovery assistance

📧 Email Support:
For detailed queries, you can also reach us via email with your contact number.

Thank you for using our Professional Billing Software!
        """
        
        contact_text.insert(tk.END, contact_content)
        contact_text.config(state=tk.DISABLED)
        
        # Select the specified tab
        help_window.after(100, lambda: help_notebook.select(tab_index))
        
        # Close button
        close_btn = ttk.Button(main_frame, text="✅ Close Help", command=help_window.destroy)
        close_btn.pack(pady=(10, 0))

    def build_menu(self):
        menubar = tk.Menu(self.master)
        self.master.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="📤 Backup Products (CSV)", command=self.on_backup)
        file_menu.add_command(label="📥 Restore Products (CSV)", command=self.on_restore)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.master.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Getting Started", command=lambda: self.show_help(0))
        help_menu.add_command(label="Features", command=lambda: self.show_help(1))
        help_menu.add_command(label="Contact Us", command=lambda: self.show_help(2))
        menubar.add_cascade(label="Help", menu=help_menu)

        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="Company Profile", command=self.open_company_profile)
        menubar.add_cascade(label="Settings", menu=settings_menu)

    # Inventory Tab - Professional Design
    def build_inventory_tab(self):
        # Header with search and actions
        header_frame = ttk.Frame(self.inventory_tab)
        header_frame.pack(fill=tk.X, padx=15, pady=15)
        
        # Search bar
        search_frame = ttk.Frame(header_frame)
        search_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(search_frame, text="🔍 Search Products:", font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
        self.var_search = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.var_search, width=35, font=("Segoe UI", 10))
        search_entry.pack(side=tk.LEFT, padx=(15, 0))
        search_entry.bind("<KeyRelease>", lambda e: self.refresh_products())
        
        # Action buttons
        actions_frame = ttk.Frame(header_frame)
        actions_frame.pack(side=tk.RIGHT)
        
        refresh_btn = ttk.Button(actions_frame, text="🔄 Refresh", command=self.refresh_products)
        refresh_btn.pack(side=tk.LEFT, padx=(0, 8))
        ToolTip(refresh_btn, "Refresh the products list to see latest changes")
        
        export_btn = ttk.Button(actions_frame, text="📤 Export", command=self.export_products_csv)
        export_btn.pack(side=tk.LEFT, padx=(0, 8))
        ToolTip(export_btn, "Export all products to a CSV file for backup")
        
        import_btn = ttk.Button(actions_frame, text="📥 Import", command=self.import_products_csv)
        import_btn.pack(side=tk.LEFT)
        ToolTip(import_btn, "Import products from a CSV file")

        # Main content frame
        content_frame = ttk.Frame(self.inventory_tab)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        
        # Left side - Product Form
        form_frame = ttk.LabelFrame(content_frame, text="📝 Product Details")
        form_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Form fields
        self.var_pid = tk.StringVar()
        self.var_name = tk.StringVar()
        self.var_price = tk.StringVar()
        self.var_stock = tk.StringVar()
        self.var_image_path = tk.StringVar()

        # Product name
        name_frame = ttk.Frame(form_frame)
        name_frame.pack(fill=tk.X, padx=20, pady=12)
        ttk.Label(name_frame, text="📦 Product Name:", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W)
        name_entry = ttk.Entry(name_frame, textvariable=self.var_name, font=("Segoe UI", 10))
        name_entry.pack(fill=tk.X, pady=(8, 0))

        # Price and Stock
        price_stock_frame = ttk.Frame(form_frame)
        price_stock_frame.pack(fill=tk.X, padx=20, pady=12)
        
        # Price
        price_frame = ttk.Frame(price_stock_frame)
        price_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 15))
        ttk.Label(price_frame, text="💰 Price (₹):", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W)
        price_entry = ttk.Entry(price_frame, textvariable=self.var_price, font=("Segoe UI", 10))
        price_entry.pack(fill=tk.X, pady=(8, 0))
        
        # Stock
        stock_frame = ttk.Frame(price_stock_frame)
        stock_frame.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(15, 0))
        ttk.Label(stock_frame, text="📊 Stock Quantity:", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W)
        stock_entry = ttk.Entry(stock_frame, textvariable=self.var_stock, font=("Segoe UI", 10))
        stock_entry.pack(fill=tk.X, pady=(8, 0))

        # Image selection
        image_frame = ttk.Frame(form_frame)
        image_frame.pack(fill=tk.X, padx=20, pady=12)
        ttk.Label(image_frame, text="🖼️ Product Image:", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W)
        
        image_input_frame = ttk.Frame(image_frame)
        image_input_frame.pack(fill=tk.X, pady=(8, 0))
        image_entry = ttk.Entry(image_input_frame, textvariable=self.var_image_path, font=("Segoe UI", 9))
        image_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(image_input_frame, text="📁 Choose", command=self.on_choose_image).pack(side=tk.RIGHT, padx=(15, 0))

        # Image preview
        preview_frame = ttk.Frame(form_frame)
        preview_frame.pack(fill=tk.X, padx=20, pady=12)
        ttk.Label(preview_frame, text="👁️ Preview:", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W)
        self.image_preview_label = ttk.Label(preview_frame, text="No image selected", 
                                           font=("Segoe UI", 9), foreground="gray")
        self.image_preview_label.pack(pady=(8, 0))

        # Action buttons - all in one row
        buttons_frame = ttk.Frame(form_frame)
        buttons_frame.pack(fill=tk.X, padx=20, pady=20)
        
        # Single button row
        btn_row = ttk.Frame(buttons_frame)
        btn_row.pack(fill=tk.X)
        
        add_btn = ttk.Button(btn_row, text="➕ Add New Product", command=self.on_add_product, 
                  style="Success.TButton")
        add_btn.pack(side=tk.LEFT, padx=(0, 10))
        ToolTip(add_btn, "Add a new product to your inventory")
        
        update_btn = ttk.Button(btn_row, text="✏️ Update Product", command=self.on_update_product, 
                  style="Info.TButton")
        update_btn.pack(side=tk.LEFT, padx=(0, 10))
        ToolTip(update_btn, "Update the selected product's information")
        
        delete_btn = ttk.Button(btn_row, text="🗑️ Delete Product", command=self.on_delete_product, 
                  style="Danger.TButton")
        delete_btn.pack(side=tk.LEFT, padx=(0, 10))
        ToolTip(delete_btn, "Delete the selected product (cannot be undone)")
        
        clear_btn = ttk.Button(btn_row, text="🧹 Clear Form", command=self.clear_product_form)
        clear_btn.pack(side=tk.LEFT)
        ToolTip(clear_btn, "Clear all form fields to start fresh")

        # Right side - Products List
        list_frame = ttk.LabelFrame(content_frame, text="📋 Products List")
        list_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        
        # Products tree
        self.products_tree = ttk.Treeview(
            list_frame,
            columns=("id", "name", "price", "stock", "image"),
            show="headings",
            height=15,
        )
        
        # Configure columns
        columns_config = [
            ("id", "ID", 60),
            ("name", "Product Name", 220),
            ("price", "Price (₹)", 110),
            ("stock", "Stock", 90),
            ("image", "Image", 110)
        ]
        
        for col, text, width in columns_config:
            self.products_tree.heading(col, text=text)
            self.products_tree.column(col, width=width, anchor="center" if col != "name" else "w")
        
        self.products_tree.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        self.products_tree.bind("<<TreeviewSelect>>", self.on_select_product)
        self.products_tree.tag_configure("even", background="#f5f7fb")
        self.products_tree.tag_configure("odd", background="#ffffff")

        self.refresh_products()

    def export_products_csv(self):
        """Export products to CSV"""
        try:
            from tkinter import filedialog
            filename = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                title="Export Products to CSV"
            )
            if filename:
                products = list_products("")
                with open(filename, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['ID', 'Name', 'Price', 'Stock', 'Image Path'])
                    for p in products:
                        writer.writerow([p['id'], p['name'], p['price'], p['stock'], p.get('image_path', '')])
                messagebox.showinfo("Success", f"Products exported to {filename}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export: {e}")

    def import_products_csv(self):
        """Import products from CSV"""
        try:
            from tkinter import filedialog
            filename = filedialog.askopenfilename(
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                title="Import Products from CSV"
            )
            if filename:
                with open(filename, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    imported_count = 0
                    for row in reader:
                        try:
                            add_product(
                                row['Name'],
                                float(row['Price']),
                                int(row['Stock']),
                                row.get('Image Path', '')
                            )
                            imported_count += 1
                        except Exception as e:
                            print(f"Error importing row {row}: {e}")
                            continue
                messagebox.showinfo("Success", f"Imported {imported_count} products")
                self.refresh_products()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to import: {e}")

    def clear_product_form(self):
        self.var_pid.set("")
        self.var_name.set("")
        self.var_price.set("")
        self.var_stock.set("")
        self.var_image_path.set("")
        self.set_image_preview(None)

    def on_select_product(self, event=None):
        sel = self.products_tree.selection()
        if not sel:
            return
        item = self.products_tree.item(sel[0])
        pid, name, price, stock, image_status = item["values"]
        self.var_pid.set(pid)
        self.var_name.set(name)
        self.var_price.set(str(price))
        self.var_stock.set(str(stock))
        # load image path
        try:
            conn = get_conn(); cur = conn.cursor()
            cur.execute("SELECT image_path FROM products WHERE id=?", (int(pid),))
            row = cur.fetchone(); conn.close()
            img_path = row["image_path"] if row else None
        except Exception:
            img_path = None
        self.var_image_path.set(img_path or "")
        self.set_image_preview(img_path)

    def refresh_products(self):
        for i in self.products_tree.get_children():
            self.products_tree.delete(i)
        term = self.var_search.get().strip() if hasattr(self, "var_search") else ""
        for idx, r in enumerate(list_products(term)):
            tag = "even" if idx % 2 == 0 else "odd"
            # Check if image exists - use dictionary access instead of .get()
            image_path = r["image_path"] if "image_path" in r.keys() else None
            image_status = "✅ Yes" if image_path and os.path.exists(image_path) else "❌ No"
            self.products_tree.insert("", tk.END, values=(
                r["id"], 
                r["name"], 
                f"₹{r['price']:.2f}", 
                r["stock"],
                image_status
            ), tags=(tag,))

    def on_add_product(self):
        name = self.var_name.get().strip()
        price = self.var_price.get().strip()
        stock = self.var_stock.get().strip()
        
        # Enhanced validation
        if not name or not price or not stock:
            self.set_status("Please fill in all required fields", "error")
            messagebox.showwarning("⚠️ Missing Information", "Please fill in all required fields:\n• Product Name\n• Price (₹)\n• Stock Quantity")
            return
        
        try:
            price_val = float(price)
            stock_val = int(stock)
            if price_val < 0 or stock_val < 0:
                raise ValueError("Negative values not allowed")
            if price_val > 999999:
                raise ValueError("Price too high (maximum: ₹999,999)")
            if stock_val > 99999:
                raise ValueError("Stock too high (maximum: 99,999)")
        except ValueError as e:
            self.set_status(f"Invalid input: {str(e)}", "error")
            messagebox.showerror("❌ Invalid Input", f"Please check your input:\n{str(e)}")
            return
        
        # Check for duplicate product name
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT id FROM products WHERE name = ?", (name,))
            if cur.fetchone():
                conn.close()
                self.set_status(f"Product '{name}' already exists", "warning")
                messagebox.showwarning("⚠️ Duplicate Product", f"Product '{name}' already exists.\nPlease use a different name or update the existing product.")
                return
            conn.close()
        except Exception as e:
            self.set_status(f"Database error: {str(e)}", "error")
            messagebox.showerror("❌ Database Error", f"Could not check for duplicates:\n{str(e)}")
            return
        
        # Process image
        img_path = None
        if self.var_image_path.get().strip():
            try:
                img_path = self.copy_image_to_library(self.var_image_path.get().strip())
            except Exception as e:
                self.set_status(f"Image processing error: {str(e)}", "warning")
                messagebox.showwarning("⚠️ Image Warning", f"Could not process image:\n{str(e)}\n\nProduct will be added without image.")
        
        # Add product
        try:
            ok, err = add_product(name, price_val, stock_val, img_path)
            if ok:
                self.clear_product_form()
                self.refresh_products()
                self.refresh_billing_products()
                self.set_status(f"✅ Product '{name}' added successfully!", "success")
                messagebox.showinfo("✅ Success", f"Product '{name}' has been added to your inventory!\n\nPrice: ₹{price_val:.2f}\nStock: {stock_val} units")
            else:
                self.set_status(f"Failed to add product: {err}", "error")
                messagebox.showerror("❌ Error", f"Could not add product:\n{err}")
        except Exception as e:
            self.set_status(f"Unexpected error: {str(e)}", "error")
            messagebox.showerror("❌ Unexpected Error", f"An unexpected error occurred:\n{str(e)}")

    def on_update_product(self):
        if not self.var_pid.get():
            messagebox.showwarning("Select", "Please select a product from the list")
            return
        name = self.var_name.get().strip()
        price = self.var_price.get().strip()
        stock = self.var_stock.get().strip()
        try:
            price_val = float(price)
            stock_val = int(stock)
            if price_val < 0 or stock_val < 0:
                raise ValueError
        except Exception:
            messagebox.showerror("Invalid", "Price must be a number, Stock must be a whole number")
            return
        img_path = self.copy_image_to_library(self.var_image_path.get().strip()) if self.var_image_path.get().strip() else None
        ok, err = update_product(int(self.var_pid.get()), name, price_val, stock_val, img_path)
        if ok:
            self.refresh_products()
            self.refresh_billing_products()
            messagebox.showinfo("Updated", "Product updated")
        else:
            messagebox.showerror("Error", f"Could not update. {err}")

    def on_choose_image(self):
        path = filedialog.askopenfilename(
            filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.bmp;*.gif")],
            initialdir=IMAGE_DIR,
        )
        if not path:
            return
        self.var_image_path.set(path)
        self.set_image_preview(path)

    def set_image_preview(self, path: str | None):
        if not hasattr(self, 'image_preview_label') or self.image_preview_label is None:
            return
        if not path or not os.path.exists(path) or not Image:
            self.image_preview_label.config(text="No image selected")
            if hasattr(self.image_preview_label, "image"):
                self.image_preview_label.image = None
            return
        try:
            pil = Image.open(path).convert("RGB")
            pil.thumbnail((96, 96))
            img = ImageTk.PhotoImage(pil)
            self.image_preview_label.config(image=img, text="")
            self.image_preview_label.image = img
        except Exception:
            self.image_preview_label.config(text="(Image error)")

    def copy_image_to_library(self, src_path: str | None) -> str | None:
        if not src_path or not os.path.exists(src_path):
            return None
        try:
            name = os.path.basename(src_path)
            target = os.path.join(IMAGE_DIR, name)
            if os.path.abspath(src_path) != os.path.abspath(target):
                with open(src_path, "rb") as rf, open(target, "wb") as wf:
                    wf.write(rf.read())
            return target
        except Exception:
            return src_path

    def on_delete_product(self):
        if not self.var_pid.get():
            messagebox.showwarning("Select", "Please select a product from the list")
            return
        if not messagebox.askyesno("Confirm", "Delete this product?"):
            return
        delete_product(int(self.var_pid.get()))
        self.clear_product_form()
        self.refresh_products()
        self.refresh_billing_products()
        messagebox.showinfo("Deleted", "Product deleted")

    def on_tab_changed(self, event=None):
        try:
            tab = self.notebook.tab(self.notebook.select(), 'text')
            if tab == "Billing":
                self.refresh_billing_products()
            elif tab == "Tables":
                self.refresh_tables()
            elif tab == "Reports":
                self.refresh_reports()
        except Exception:
            pass

    # Billing Tab - Clean and Simple like Tables Tab
    def build_billing_tab(self):
        # Header with search and actions
        header_frame = ttk.Frame(self.billing_tab)
        header_frame.pack(fill=tk.X, padx=15, pady=15)
        
        # Search bar
        search_frame = ttk.Frame(header_frame)
        search_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(search_frame, text="🔍 Search Products:", font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
        self.var_bill_search = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.var_bill_search, width=35, font=("Segoe UI", 10))
        search_entry.pack(side=tk.LEFT, padx=(15, 0))
        search_entry.bind("<KeyRelease>", lambda e: self.refresh_billing_products())
        
        # Action buttons
        actions_frame = ttk.Frame(header_frame)
        actions_frame.pack(side=tk.RIGHT)
        ttk.Button(actions_frame, text="🔄 Refresh", command=self.refresh_billing_products).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(actions_frame, text="🗑️ Remove Selected", command=self.on_remove_cart_item, 
                  style="Danger.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(actions_frame, text="🧾 Generate Bill", command=self.on_checkout, 
                  style="Success.TButton").pack(side=tk.LEFT)

        # Main content frame
        content_frame = ttk.Frame(self.billing_tab)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        
        # Left side - Product Gallery
        products_frame = ttk.LabelFrame(content_frame, text="📦 Products - Click to Add")
        products_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        # Product gallery with vertical scroll
        self.billing_gallery_canvas = tk.Canvas(products_frame, bg="white")
        self.billing_gallery_scroll = ttk.Scrollbar(products_frame, orient=tk.VERTICAL, command=self.billing_gallery_canvas.yview)
        self.billing_gallery_inner = ttk.Frame(self.billing_gallery_canvas)
        
        self.billing_gallery_inner.bind(
            "<Configure>",
            lambda e: self.billing_gallery_canvas.configure(scrollregion=self.billing_gallery_canvas.bbox("all"))
        )
        
        self.billing_gallery_canvas.create_window((0, 0), window=self.billing_gallery_inner, anchor="nw")
        self.billing_gallery_canvas.configure(yscrollcommand=self.billing_gallery_scroll.set)
        
        self.billing_gallery_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.billing_gallery_scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=10)

        # Right side - Cart/Order
        cart_frame = ttk.LabelFrame(content_frame, text="🛒 Selected Items")
        cart_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        
        # Cart tree
        self.cart_tree = ttk.Treeview(
            cart_frame,
            columns=("name", "price", "qty", "subtotal"),
            show="headings",
            height=15,
        )
        for col, text in [("name", "Product"), ("price", "Price"), ("qty", "Qty"), ("subtotal", "Total")]:
            self.cart_tree.heading(col, text=text)
            self.cart_tree.column(col, width=130)
        self.cart_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.cart_tree.tag_configure("even", background="#f5f7fb")
        self.cart_tree.tag_configure("odd", background="#ffffff")

        # Bottom total and actions
        bottom_frame = ttk.Frame(self.billing_tab)
        bottom_frame.pack(fill=tk.X, padx=15, pady=15)
        
        # Total display
        total_frame = ttk.Frame(bottom_frame)
        total_frame.pack(side=tk.LEFT)
        ttk.Label(total_frame, text="💰 Total:", font=("Segoe UI", 13, "bold")).pack(side=tk.LEFT)
        self.var_total = tk.StringVar(value="₹0.00")
        ttk.Label(total_frame, textvariable=self.var_total, font=("Segoe UI", 18, "bold"), 
                 foreground="#2b74ff").pack(side=tk.LEFT, padx=15)
        
        # Action buttons
        action_buttons_frame = ttk.Frame(bottom_frame)
        action_buttons_frame.pack(side=tk.RIGHT)
        ttk.Button(action_buttons_frame, text="🗑️ Remove Selected", command=self.on_remove_cart_item, 
                  style="Danger.TButton").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(action_buttons_frame, text="🧾 Generate Bill", command=self.on_checkout, 
                  style="Success.TButton").pack(side=tk.LEFT)

        self.cart_items = []  # list of dicts
        self.refresh_billing_products()

    def refresh_billing_products(self):
        """Refresh the billing product gallery"""
        term = self.var_bill_search.get().strip() if hasattr(self, "var_bill_search") else ""
        rows = list_products(term)
        self.refresh_billing_gallery(rows)

    def refresh_billing_gallery(self, products):
        """Refresh the billing product gallery with images"""
        # Clear existing widgets
        for w in self.billing_gallery_inner.winfo_children():
            w.destroy()
        
        if not products:
            ttk.Label(self.billing_gallery_inner, text="No products found", 
                     font=("Segoe UI", 12), foreground="gray").pack(pady=20)
            return
        
        # Show a hint if Pillow isn't installed
        if not Image:
            ttk.Label(self.billing_gallery_inner, text="Install Pillow to show images: pip install pillow", 
                     font=("Segoe UI", 10), foreground="orange").pack(pady=20)
            return
        
        thumb_size = (50, 50)
        self._billing_gallery_images = []
        
        # Create product grid (5 columns for better layout)
        for idx, p in enumerate(products):
            row = idx // 5
            col = idx % 5
            
            # Product frame - uniform size (optimized for 5 columns)
            product_frame = tk.Frame(self.billing_gallery_inner, relief="raised", borderwidth=2, width=120, height=130, bg="white")
            product_frame.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
            product_frame.grid_propagate(False)  # Prevent frame from shrinking
            product_frame.pack_propagate(False)  # Prevent frame from shrinking due to content
            
            # Image frame - centered with fixed size
            img_frame = tk.Frame(product_frame, width=100, height=50, bg="white")
            img_frame.pack(pady=6)
            img_frame.pack_propagate(False)
            
            # Product image
            img_label = ttk.Label(img_frame, cursor="hand2")
            img = None
            if p["image_path"] and os.path.exists(p["image_path"]):
                try:
                    pil = Image.open(p["image_path"]).convert("RGB")
                    pil.thumbnail(thumb_size)
                    img = ImageTk.PhotoImage(pil)
                except Exception:
                    img = None
            
            if img is not None:
                img_label.configure(image=img)
                img_label.image = img
                self._billing_gallery_images.append(img)
            else:
                img_label.configure(text="📦", font=("Segoe UI", 20), width=8)
            
            img_label.pack(expand=True)
            
            # Text frame with fixed size
            text_frame = tk.Frame(product_frame, width=110, height=60)
            text_frame.pack(pady=(0, 6))
            text_frame.pack_propagate(False)
            
            # Product name
            name_label = ttk.Label(text_frame, text=p["name"], font=("Segoe UI", 8, "bold"), 
                                 wraplength=100, justify="center")
            name_label.pack(pady=(1, 1))
            
            # Price
            price_label = ttk.Label(text_frame, text=f"₹{p['price']:.2f}", 
                                  font=("Segoe UI", 9, "bold"), foreground="#2b74ff")
            price_label.pack(pady=1)
            
            # Stock
            stock_label = ttk.Label(text_frame, text=f"Stock: {p['stock']}", 
                                  font=("Segoe UI", 9, "bold"), foreground="#E65100")
            stock_label.pack(pady=1)
            
            # Click to add functionality
            def make_click_handler(pid):
                def on_click(event):
                    self.add_product_to_cart(pid)
                return on_click
            
            # Bind click events to all widgets in the product frame
            for widget in [product_frame, img_label, name_label, price_label, stock_label]:
                widget.bind("<Button-1>", make_click_handler(p["id"]))
            
            # No hover effects - just uniform sizing
        
        # Configure grid weights for 5 columns
        for i in range(5):
            self.billing_gallery_inner.columnconfigure(i, weight=1)

    def add_product_to_cart(self, pid: int):
        """Add product to cart by clicking on product image"""
        prod = [r for r in list_products("") if r["id"] == pid]
        if not prod:
            return
        prod = prod[0]
        
        if prod["stock"] <= 0:
            messagebox.showwarning("Stock", f"Out of stock: {prod['name']}")
            return
        
        # Show popup dialog for quantity selection
        self.show_product_popup(prod)
    
    def show_product_popup(self, product):
        """Show popup dialog for product quantity selection"""
        # Create popup window
        popup = tk.Toplevel(self.master)
        popup.title(f"Add {product['name']} to Cart")
        popup.geometry("450x600")
        popup.resizable(False, False)
        popup.transient(self.master)
        popup.grab_set()
        
        # Center the popup properly
        popup.update_idletasks()
        
        # Get screen dimensions
        screen_width = popup.winfo_screenwidth()
        screen_height = popup.winfo_screenheight()
        
        # Calculate position to center the window
        x = (screen_width - 450) // 2
        y = (screen_height - 600) // 2
        
        # Ensure positive coordinates and proper centering
        x = max(0, x)
        y = max(0, y)
        
        # Set the geometry with calculated position
        popup.geometry(f"450x600+{x}+{y}")
        
        # Force the popup to be visible and centered
        popup.lift()
        popup.focus_force()
        popup.attributes('-topmost', True)
        popup.after_idle(lambda: popup.attributes('-topmost', False))
        
        # Configure popup style
        popup.configure(bg="#F5F5F5")
        
        # Main frame with professional styling
        main_frame = tk.Frame(popup, bg="#FFFFFF", relief="solid", bd=1)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # Product info frame - centered
        info_frame = tk.Frame(main_frame, bg="#FFFFFF")
        info_frame.pack(fill=tk.X, padx=20, pady=15)
        
        # Product image - centered
        try:
            if product.get("image_path") and os.path.exists(product["image_path"]):
                img = Image.open(product["image_path"])
                img = img.resize((80, 80), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                img_label = tk.Label(info_frame, image=photo, bg="#FFFFFF")
                img_label.image = photo  # Keep a reference
            else:
                img_label = tk.Label(info_frame, text="📦", font=("Segoe UI", 24), bg="#FFFFFF")
        except:
            img_label = tk.Label(info_frame, text="📦", font=("Segoe UI", 24), bg="#FFFFFF")
        
        img_label.pack(pady=10)
        
        # Product details - centered
        details_frame = tk.Frame(info_frame, bg="#FFFFFF")
        details_frame.pack(fill=tk.X, pady=5)
        
        name_label = tk.Label(details_frame, text=product["name"], 
                             font=("Segoe UI", 16, "bold"), bg="#FFFFFF", fg="#333333")
        name_label.pack(pady=2)
        
        price_label = tk.Label(details_frame, text=f"₹{product['price']:.2f}", 
                              font=("Segoe UI", 14, "bold"), bg="#FFFFFF", fg="#2E7D32")
        price_label.pack(pady=2)
        
        stock_label = tk.Label(details_frame, text=f"Stock: {product['stock']} units", 
                              font=("Segoe UI", 11), bg="#FFFFFF", fg="#888888")
        stock_label.pack(pady=2)
        
        # Quantity selection frame - centered
        qty_frame = tk.Frame(main_frame, bg="#FFFFFF")
        qty_frame.pack(fill=tk.X, padx=20, pady=15)
        
        qty_label = tk.Label(qty_frame, text="Quantity:", 
                             font=("Segoe UI", 14, "bold"), bg="#FFFFFF")
        qty_label.pack(pady=10)
        
        # Quantity controls with professional styling - centered
        controls_frame = tk.Frame(qty_frame, bg="#FFFFFF")
        controls_frame.pack(expand=True)
        
        # Quantity variable
        qty_var = tk.StringVar(value="1")
        
        # Minus button - professional styling
        minus_btn = tk.Button(controls_frame, text="−", font=("Segoe UI", 20, "bold"),
                             width=4, height=1, bg="#FF5722", fg="white",
                             relief="flat", bd=0, cursor="hand2",
                             activebackground="#E64A19", activeforeground="white")
        minus_btn.pack(side=tk.LEFT, padx=(0, 20))
        
        # Quantity input - professional styling
        qty_entry = tk.Entry(controls_frame, textvariable=qty_var, font=("Segoe UI", 18, "bold"),
                            width=8, justify=tk.CENTER, relief="solid", bd=2,
                            bg="#F8F9FA", fg="#333333", insertbackground="#333333")
        qty_entry.pack(side=tk.LEFT, padx=10)
        
        # Plus button - professional styling
        plus_btn = tk.Button(controls_frame, text="+", font=("Segoe UI", 20, "bold"),
                            width=4, height=1, bg="#4CAF50", fg="white",
                            relief="flat", bd=0, cursor="hand2",
                            activebackground="#45A049", activeforeground="white")
        plus_btn.pack(side=tk.LEFT, padx=(20, 0))
        
        # Total price display with professional styling - centered
        total_frame = tk.Frame(main_frame, bg="#F8F9FA", relief="solid", bd=1)
        total_frame.pack(fill=tk.X, padx=20, pady=15)
        
        total_label = tk.Label(total_frame, text="Total: ₹0.00", 
                              font=("Segoe UI", 18, "bold"), bg="#F8F9FA", fg="#2E7D32")
        total_label.pack(pady=15)
        
        # Buttons frame with professional styling - centered
        buttons_frame = tk.Frame(main_frame, bg="#FFFFFF")
        buttons_frame.pack(fill=tk.X, padx=20, pady=30)
        
        # Center the buttons
        buttons_container = tk.Frame(buttons_frame, bg="#FFFFFF")
        buttons_container.pack()
        
        # Cancel button - professional styling
        cancel_btn = tk.Button(buttons_container, text="Cancel", font=("Segoe UI", 14, "bold"),
                              width=15, height=3, bg="#E0E0E0", fg="#666666",
                              relief="raised", bd=2, cursor="hand2",
                              activebackground="#BDBDBD", activeforeground="#333333",
                              command=popup.destroy)
        cancel_btn.pack(side=tk.LEFT, padx=(0, 20))
        
        # Add button - professional styling
        add_btn = tk.Button(buttons_container, text="Add to Cart", font=("Segoe UI", 14, "bold"),
                           width=18, height=3, bg="#2196F3", fg="white",
                           relief="raised", bd=2, cursor="hand2",
                           activebackground="#1976D2", activeforeground="white")
        add_btn.pack(side=tk.LEFT)
        
        # Functions for quantity controls
        def update_quantity(delta):
            try:
                current_qty = int(qty_var.get())
                new_qty = max(1, min(current_qty + delta, product["stock"]))
                qty_var.set(str(new_qty))
                update_total()
            except ValueError:
                qty_var.set("1")
                update_total()
        
        def update_total():
            try:
                qty = int(qty_var.get())
                total = qty * float(product["price"])
                total_label.config(text=f"Total: ₹{total:.2f}")
            except ValueError:
                total_label.config(text="Total: ₹0.00")
        
        def add_to_cart():
            try:
                qty = int(qty_var.get())
                if qty <= 0:
                    messagebox.showwarning("Invalid Quantity", "Please enter a valid quantity")
                    return
                
                if qty > product["stock"]:
                    messagebox.showwarning("Stock", f"Only {product['stock']} units available")
                    return
                
                # Check if already in cart
                for item in self.cart_items:
                    if item["product_id"] == product["id"]:
                        if item["qty"] + qty > product["stock"]:
                            messagebox.showwarning("Stock", f"Only {product['stock']} units available")
                            return
                        item["qty"] += qty
                        break
                else:
                    self.cart_items.append({
                        "product_id": product["id"],
                        "name": product["name"],
                        "price": float(product["price"]),
                        "qty": qty,
                    })
                
                self.refresh_cart()
                
                # Close popup immediately - no success message to speed up process
                popup.destroy()
                
            except ValueError:
                messagebox.showwarning("Invalid Quantity", "Please enter a valid number")
        
        # Bind events
        minus_btn.config(command=lambda: update_quantity(-1))
        plus_btn.config(command=lambda: update_quantity(1))
        add_btn.config(command=add_to_cart)
        
        # Bind quantity entry changes
        qty_var.trace("w", lambda *args: update_total())
        
        # Initial total update
        update_total()
        
        # Focus on quantity entry and ensure popup is visible
        qty_entry.focus()
        qty_entry.select_range(0, tk.END)
        
        # Ensure popup is on top and visible
        popup.lift()
        popup.focus_force()
        popup.attributes('-topmost', True)
        popup.after_idle(lambda: popup.attributes('-topmost', False))
        
        # Force update and show
        popup.update()
        popup.deiconify()

    def show_add_success_popup(self, parent_popup, product, qty):
        """Show success popup after adding product to cart"""
        # Close the quantity popup first
        parent_popup.destroy()
        
        # Create success popup
        success_popup = tk.Toplevel(self.master)
        success_popup.title("Product Added Successfully")
        success_popup.geometry("400x250")
        success_popup.resizable(False, False)
        success_popup.transient(self.master)
        success_popup.grab_set()
        
        # Center the popup
        success_popup.update_idletasks()
        x = (success_popup.winfo_screenwidth() // 2) - (400 // 2)
        y = (success_popup.winfo_screenheight() // 2) - (250 // 2)
        success_popup.geometry(f"400x250+{x}+{y}")
        
        # Configure popup style
        success_popup.configure(bg="#F5F5F5")
        
        # Main frame
        main_frame = tk.Frame(success_popup, bg="#FFFFFF", relief="solid", bd=1)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # Success icon and message
        success_frame = tk.Frame(main_frame, bg="#FFFFFF")
        success_frame.pack(fill=tk.X, padx=20, pady=20)
        
        # Success icon
        icon_label = tk.Label(success_frame, text="✅", font=("Segoe UI", 32), bg="#FFFFFF")
        icon_label.pack(pady=10)
        
        # Success message
        success_msg = tk.Label(success_frame, 
                              text=f"Successfully added {qty} x {product['name']} to cart!",
                              font=("Segoe UI", 14, "bold"), bg="#FFFFFF", fg="#2E7D32")
        success_msg.pack(pady=5)
        
        # Cart total
        cart_total = sum(item["price"] * item["qty"] for item in self.cart_items)
        total_msg = tk.Label(success_frame, 
                            text=f"Cart Total: ₹{cart_total:.2f}",
                            font=("Segoe UI", 12), bg="#FFFFFF", fg="#666666")
        total_msg.pack(pady=5)
        
        # Buttons frame
        buttons_frame = tk.Frame(main_frame, bg="#FFFFFF")
        buttons_frame.pack(fill=tk.X, padx=20, pady=20)
        
        # Continue Billing button
        continue_btn = tk.Button(buttons_frame, text="Continue Billing", 
                                font=("Segoe UI", 12, "bold"),
                                width=15, height=2, bg="#4CAF50", fg="white",
                                relief="flat", bd=0, cursor="hand2",
                                activebackground="#45A049", activeforeground="white",
                                command=success_popup.destroy)
        continue_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # View Cart button
        view_cart_btn = tk.Button(buttons_frame, text="View Cart", 
                                 font=("Segoe UI", 12, "bold"),
                                 width=12, height=2, bg="#2196F3", fg="white",
                                 relief="flat", bd=0, cursor="hand2",
                                 activebackground="#1976D2", activeforeground="white",
                                 command=lambda: [success_popup.destroy(), self.switch_to_billing_tab()])
        view_cart_btn.pack(side=tk.RIGHT)
        
        # Ensure popup is visible
        success_popup.lift()
        success_popup.focus_force()
        success_popup.attributes('-topmost', True)
        success_popup.after_idle(lambda: success_popup.attributes('-topmost', False))

    def switch_to_billing_tab(self):
        """Switch to billing tab to show the cart"""
        # Find the billing tab and switch to it
        for i, tab in enumerate(self.notebook.tabs()):
            if "Billing" in self.notebook.tab(tab, "text"):
                self.notebook.select(i)
                break

    def recalc_total(self):
        total = sum(i["price"] * i["qty"] for i in self.cart_items)
        self.var_total.set(f"₹{total:.2f}")


    def refresh_cart(self):
        for i in self.cart_tree.get_children():
            self.cart_tree.delete(i)
        for idx, item in enumerate(self.cart_items):
            subtotal = item["price"] * item["qty"]
            tag = "even" if idx % 2 == 0 else "odd"
            self.cart_tree.insert("", tk.END, values=(item["name"], f"₹{item['price']:.2f}", item["qty"], f"₹{subtotal:.2f}"), tags=(tag,))
        self.recalc_total()

    def on_remove_cart_item(self):
        sel = self.cart_tree.selection()
        if not sel:
            return
        item = self.cart_tree.item(sel[0])
        name = item["values"][0]
        self.cart_items = [i for i in self.cart_items if i["name"] != name]
        self.refresh_cart()

    def on_checkout(self):
        if not self.cart_items:
            messagebox.showwarning("Empty", "Cart is empty")
            return
        try:
            bill_id, total = create_bill(self.cart_items)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return
        path = save_invoice_text(bill_id)
        self.cart_items = []
        self.refresh_cart()
        self.refresh_products()  # stock changed
        self.refresh_billing_products()
        self.refresh_reports()
        if path:
            self.show_invoice_preview(bill_id, path)
        else:
            messagebox.showinfo("Done", f"Bill #{bill_id} saved.")

    def show_invoice_preview(self, bill_id: int, path: str):
        win = tk.Toplevel(self.master)
        win.title(f"Invoice #{bill_id} Preview")
        win.geometry("700x500")

        top = ttk.Frame(win)
        top.pack(fill=tk.X, padx=10, pady=8)
        ttk.Label(top, text=f"Invoice file: {os.path.basename(path)}").pack(side=tk.LEFT)

        txt = tk.Text(win, wrap="word")
        txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        try:
            with open(path, "r", encoding="utf-8") as f:
                txt.insert("1.0", f.read())
        except Exception as e:
            txt.insert("1.0", f"Could not load invoice: {e}")
        txt.configure(state="disabled")

        btns = ttk.Frame(win)
        btns.pack(fill=tk.X, padx=10, pady=8)
        ttk.Button(btns, text="Open File", command=lambda: self.open_file(path)).pack(side=tk.LEFT)
        ttk.Button(btns, text="Print", command=lambda: self.print_file(path)).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Close", command=win.destroy).pack(side=tk.RIGHT)

    def open_file(self, path: str):
        try:
            if os.name == "nt":
                os.startfile(path)  # Opens in default app (likely Notepad)
            else:
                messagebox.showinfo("Open", "Open is only set up for Windows in this app.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # Settings helpers
    def open_company_profile(self):
        win = tk.Toplevel(self.master)
        win.title("Company Profile")
        win.geometry("420x260")
        data = load_settings()

        vars_ = {
            "company_name": tk.StringVar(value=data.get("company_name", "")),
            "company_address": tk.StringVar(value=data.get("company_address", "")),
            "company_phone": tk.StringVar(value=data.get("company_phone", "")),
        }

        form = ttk.Frame(win)
        form.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        ttk.Label(form, text="Company Name").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=vars_["company_name"], width=40).grid(row=0, column=1, sticky="w")
        ttk.Label(form, text="Address").grid(row=1, column=0, sticky="w")
        ttk.Entry(form, textvariable=vars_["company_address"], width=40).grid(row=1, column=1, sticky="w")
        ttk.Label(form, text="Phone").grid(row=2, column=0, sticky="w")
        ttk.Entry(form, textvariable=vars_["company_phone"], width=40).grid(row=2, column=1, sticky="w")

        btns = ttk.Frame(win)
        btns.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btns, text="Save", command=lambda: (save_settings({k: v.get() for k, v in vars_.items()}), win.destroy(), messagebox.showinfo("Saved", "Company profile saved"))).pack(side=tk.RIGHT)

    def print_file(self, path: str):
        try:
            if hasattr(os, "startfile"):
                # Sends to default printer; for thermal printers set as default, it will print there
                os.startfile(path, "print")
                messagebox.showinfo("Print", "Sent to printer. If nothing prints, check the default printer.")
            else:
                messagebox.showwarning("Print", "Printing is supported on Windows using the default printer.")
        except Exception as e:
            messagebox.showerror("Print Error", str(e))

    # Tables Tab
    def build_tables_tab(self):
        # Table status tracking - 8 tables with more space
        self.current_table = 0
        self.table_orders = {i+1: [] for i in range(8)}  # Store orders for each table
        self.table_status = {i+1: "empty" for i in range(8)}  # empty, ordering, ready, served

        # Professional header
        header_frame = ttk.Frame(self.tables_tab, style="Header.TFrame")
        header_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        title_label = ttk.Label(header_frame, text="🍽️ Restaurant Table Management", 
                               font=("Segoe UI", 16, "bold"), style="Header.TLabel")
        title_label.pack(side=tk.LEFT)
        
        # Quick stats
        stats_frame = ttk.Frame(header_frame)
        stats_frame.pack(side=tk.RIGHT)
        
        self.var_total_tables = tk.StringVar(value="Tables: 8")
        
        ttk.Label(stats_frame, textvariable=self.var_total_tables, font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=5)

        # Main container for table view
        self.tables_main_frame = ttk.Frame(self.tables_tab)
        self.tables_main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Menu view frame (initially hidden)
        self.menu_view_frame = ttk.Frame(self.tables_tab)
        
        self.build_tables_view()

    def build_tables_view(self):
        """Build the main tables view with 12 tables"""
        # Clear existing widgets
        for widget in self.tables_main_frame.winfo_children():
            widget.destroy()
        
        # Restaurant Layout
        layout_frame = ttk.Frame(self.tables_main_frame)
        layout_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # A/C Section
        ac_frame = tk.LabelFrame(layout_frame, text="🍽️ A/C Section - Tables 1-8", 
                                font=("Segoe UI", 15, "bold"), fg="#1976D2")
        ac_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Create systematic table grid (2 rows x 4 columns for 8 tables)
        self.table_buttons = []
        
        # Row labels removed for cleaner layout
        
        # Column labels removed for cleaner layout
        
        for i in range(8):
            table_num = i + 1
            row = i // 4  # Direct row positioning
            col = i % 4   # Direct column positioning
            
            # Systematic table frame - bigger with more space and rounded appearance
            table_frame = tk.Frame(ac_frame, width=220, height=240, 
                                 relief="raised", bd=3, bg="#FFFFFF", 
                                 highlightbackground="#E0E0E0", highlightthickness=2)
            table_frame.grid(row=row, column=col, padx=12, pady=12, sticky="nsew")
            table_frame.grid_propagate(False)
            
            # Table header with systematic layout - bigger and rounded
            header_frame = tk.Frame(table_frame, height=45, bg=self.get_table_color(table_num),
                                  relief="raised", bd=2)
            header_frame.pack(fill=tk.X)
            header_frame.pack_propagate(False)
            
            # Table number - centered and systematic - bigger
            table_label = tk.Label(
                header_frame, 
                text=f"Table {table_num:02d}",
                font=("Segoe UI", 14, "bold"),
                bg=self.get_table_color(table_num),
                fg="#1976D2"
            )
            table_label.pack(side=tk.LEFT, padx=12, pady=8)
            
            # Status indicator - bigger
            status_label = tk.Label(
                header_frame,
                text=self.get_status_emoji(table_num),
                font=("Segoe UI", 16),
                bg=self.get_table_color(table_num),
                fg="#424242"
            )
            status_label.pack(side=tk.RIGHT, padx=12, pady=8)
            
            # Remove button - systematic placement - bigger and rounded
            remove_btn = tk.Button(
                header_frame,
                text="✕",
                font=("Segoe UI", 12, "bold"),
                command=lambda t=table_num: self.clear_table_order(t),
                bg="#F44336",
                fg="white",
                relief="raised",
                bd=4,
                width=2,
                height=1,
                cursor="hand2"
            )
            remove_btn.pack(side=tk.RIGHT, padx=4, pady=8)
            remove_btn.bind("<Enter>", lambda e, b=remove_btn: b.configure(bg="#D32F2F"))
            remove_btn.bind("<Leave>", lambda e, b=remove_btn: b.configure(bg="#F44336"))
            
            # Main table button area with status text - bigger and rounded
            btn = tk.Button(
                table_frame, 
                text=self.get_status_text(table_num),
                command=lambda t=table_num: self.open_table_menu(t),
                font=("Segoe UI", 12, "bold"),
                bg=self.get_table_color(table_num),
                fg="#1976D2",
                relief="raised",
                bd=4,
                cursor="hand2"
            )
            btn.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
            btn.bind("<Enter>", lambda e, b=btn, t=table_num: b.configure(bg=self.get_hover_color(t)))
            btn.bind("<Leave>", lambda e, b=btn, t=table_num: b.configure(bg=self.get_table_color(table_num)))
            
            # Status icons frame - bigger
            icons_frame = tk.Frame(table_frame, height=30, bg=self.get_table_color(table_num))
            icons_frame.pack(side=tk.BOTTOM, fill=tk.X)
            icons_frame.pack_propagate(False)
            
            # Add status icons
            self.add_table_icons(icons_frame, table_num)
            
            # Systematic buttons layout - bigger with more space
            buttons_frame = tk.Frame(table_frame, height=80)
            buttons_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=3)
            buttons_frame.pack_propagate(False)
            
            # Generate Bill button - professional square design
            bill_btn = tk.Button(
                buttons_frame,
                text="📄\nGENERATE\nBILL",
                font=("Segoe UI", 8, "bold"),
                command=lambda t=table_num: self.generate_table_bill_direct(t),
                bg="#4CAF50",
                fg="white",
                relief="raised",
                bd=3,
                width=8,
                height=4,
                cursor="hand2",
                state="disabled",
                compound="center"
            )
            bill_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2, pady=2)
            bill_btn.bind("<Enter>", lambda e, b=bill_btn: b.configure(bg="#45a049") if b['state'] == 'normal' else None)
            bill_btn.bind("<Leave>", lambda e, b=bill_btn: b.configure(bg="#4CAF50") if b['state'] == 'normal' else None)
            
            # View Bill button - professional square design
            view_bill_btn = tk.Button(
                buttons_frame,
                text="👁️\nVIEW\nBILL",
                font=("Segoe UI", 8, "bold"),
                command=lambda t=table_num: self.view_table_bill_direct(t),
                bg="#2196F3",
                fg="white",
                relief="raised",
                bd=3,
                width=8,
                height=4,
                cursor="hand2",
                state="disabled",
                compound="center"
            )
            view_bill_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2, pady=2)
            view_bill_btn.bind("<Enter>", lambda e, b=view_bill_btn: b.configure(bg="#1976D2") if b['state'] == 'normal' else None)
            view_bill_btn.bind("<Leave>", lambda e, b=view_bill_btn: b.configure(bg="#2196F3") if b['state'] == 'normal' else None)
            
            self.table_buttons.append((table_frame, btn, icons_frame, header_frame, bill_btn, view_bill_btn))
        
        # Configure grid weights for systematic layout
        for i in range(4):  # 4 columns
            ac_frame.columnconfigure(i, weight=1)
        for i in range(2):  # 2 rows
            ac_frame.rowconfigure(i, weight=1)

    def open_table_menu(self, table_num):
        """Open menu view for selected table"""
        self.current_table = table_num
        self.table_status[table_num] = "ordering"
        self.update_table_display()
        
        # Hide tables view and show menu view
        self.tables_main_frame.pack_forget()
        self.menu_view_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.build_menu_view(table_num)

    def build_menu_view(self, table_num):
        """Build menu view for selected table"""
        # Clear existing widgets
        for widget in self.menu_view_frame.winfo_children():
            widget.destroy()
        
        # Header with back button and table info
        header_frame = ttk.Frame(self.menu_view_frame)
        header_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Back to tables button - colorful
        back_btn = tk.Button(header_frame, text="🔙 Back to Tables", 
                            command=self.back_to_tables,
                            font=("Segoe UI", 10, "bold"),
                            bg="#FF5722", fg="white", relief="raised", bd=3,
                            cursor="hand2", height=2)
        back_btn.pack(side=tk.LEFT, padx=5, pady=5)
        back_btn.bind("<Enter>", lambda e, b=back_btn: b.configure(bg="#E64A19"))
        back_btn.bind("<Leave>", lambda e, b=back_btn: b.configure(bg="#FF5722"))
        
        # Table info
        table_info_frame = ttk.Frame(header_frame)
        table_info_frame.pack(side=tk.RIGHT)
        
        ttk.Label(table_info_frame, text=f"Table {table_num}", 
                 font=("Segoe UI", 16, "bold")).pack()
        
        # Order summary
        order = self.table_orders[table_num]
        item_count = len(order)
        total = sum(item["price"] * item["qty"] for item in order)
        
        ttk.Label(table_info_frame, text=f"Items: {item_count} | Total: ₹{total:.2f}", 
                 font=("Segoe UI", 10)).pack()
        
        # Main content frame
        content_frame = ttk.Frame(self.menu_view_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Left side - Product menu
        menu_frame = ttk.LabelFrame(content_frame, text="Menu - Click to Add Items")
        menu_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Search bar
        search_frame = ttk.Frame(menu_frame)
        search_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT)
        self.var_table_search = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.var_table_search, width=30)
        search_entry.pack(side=tk.LEFT, padx=5)
        search_entry.bind("<KeyRelease>", lambda e: self.refresh_table_products())
        
        # Product gallery
        gallery_frame = ttk.Frame(menu_frame)
        gallery_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Canvas with scrollbars
        canvas_frame = ttk.Frame(gallery_frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.table_gallery_canvas = tk.Canvas(canvas_frame, height=400)
        
        # Scrollbars
        h_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.table_gallery_canvas.xview)
        v_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.table_gallery_canvas.yview)
        
        self.table_gallery_canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)
        
        # Inner frame for images
        self.table_gallery_inner = ttk.Frame(self.table_gallery_canvas)
        self.table_gallery_inner.bind(
            "<Configure>",
            lambda e: self.table_gallery_canvas.configure(scrollregion=self.table_gallery_canvas.bbox("all")),
        )
        self.table_gallery_canvas.create_window((0, 0), window=self.table_gallery_inner, anchor="nw")
        
        # Pack everything
        self.table_gallery_canvas.grid(row=0, column=0, sticky="nsew")
        h_scroll.grid(row=1, column=0, sticky="ew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)
        
        # Right side - Current order
        order_frame = ttk.LabelFrame(content_frame, text=f"Table {table_num} Order")
        order_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        # Order tree
        self.table_order_tree = ttk.Treeview(
            order_frame,
            columns=("name", "price", "qty", "subtotal"),
            show="headings",
            height=15,
        )
        for col, text in [("name", "Item"), ("price", "Price"), ("qty", "Qty"), ("subtotal", "Subtotal")]:
            self.table_order_tree.heading(col, text=text)
            self.table_order_tree.column(col, width=120)
        
        # Scrollbar for order tree
        order_scroll = ttk.Scrollbar(order_frame, orient=tk.VERTICAL, command=self.table_order_tree.yview)
        self.table_order_tree.configure(yscrollcommand=order_scroll.set)
        
        self.table_order_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=5)
        order_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.table_order_tree.tag_configure("even", background="#f5f7fb")
        self.table_order_tree.tag_configure("odd", background="#ffffff")
        
        # Bind events
        self.table_order_tree.bind("<Double-1>", self.remove_selected_table_item)
        self.table_order_tree.bind("<Delete>", self.remove_selected_table_item)
        self.table_order_tree.bind("<BackSpace>", self.remove_selected_table_item)
        
        # Order actions
        actions_frame = ttk.Frame(order_frame)
        actions_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.var_table_total = tk.StringVar(value="0.00")
        ttk.Label(actions_frame, text="Total:").pack(side=tk.LEFT)
        ttk.Label(actions_frame, textvariable=self.var_table_total, font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT, padx=5)
        
        # Action buttons - colorful and modern
        remove_btn = tk.Button(actions_frame, text="🗑️ Remove Selected", 
                              command=self.remove_selected_table_item,
                              font=("Segoe UI", 9, "bold"),
                              bg="#F44336", fg="white", relief="raised", bd=3,
                              cursor="hand2", height=2)
        remove_btn.pack(side=tk.RIGHT, padx=3)
        remove_btn.bind("<Enter>", lambda e, b=remove_btn: b.configure(bg="#D32F2F"))
        remove_btn.bind("<Leave>", lambda e, b=remove_btn: b.configure(bg="#F44336"))
        
        clear_btn = tk.Button(actions_frame, text="🧹 Clear Order", 
                             command=self.clear_table_order,
                             font=("Segoe UI", 9, "bold"),
                             bg="#FF9800", fg="white", relief="raised", bd=3,
                             cursor="hand2", height=2)
        clear_btn.pack(side=tk.RIGHT, padx=3)
        clear_btn.bind("<Enter>", lambda e, b=clear_btn: b.configure(bg="#F57C00"))
        clear_btn.bind("<Leave>", lambda e, b=clear_btn: b.configure(bg="#FF9800"))
        
        generate_btn = tk.Button(actions_frame, text="💳 Generate Bill", 
                                command=self.generate_table_bill,
                                font=("Segoe UI", 9, "bold"),
                                bg="#4CAF50", fg="white", relief="raised", bd=3,
                                cursor="hand2", height=2)
        generate_btn.pack(side=tk.RIGHT, padx=3)
        generate_btn.bind("<Enter>", lambda e, b=generate_btn: b.configure(bg="#45a049"))
        generate_btn.bind("<Leave>", lambda e, b=generate_btn: b.configure(bg="#4CAF50"))
        
        # Refresh the menu
        self.refresh_table_products()
        self.refresh_table_order()

    def back_to_tables(self):
        """Go back to tables view"""
        self.menu_view_frame.pack_forget()
        self.tables_main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.update_table_display()

    def get_table_color(self, table_num):
        """Get color based on table status"""
        status = self.table_status.get(table_num, "empty")
        if status == "empty":
            return "#E8F5E8"  # Light green
        elif status == "ordering":
            return "#E3F2FD"  # Light blue
        elif status == "ready":
            return "#FFF3E0"  # Light orange
        elif status == "served":
            return "#F3E5F5"  # Light purple
        return "#E8F5E8"

    def get_hover_color(self, table_num):
        """Get hover color for table"""
        status = self.table_status.get(table_num, "empty")
        if status == "empty":
            return "#C8E6C9"  # Medium green
        elif status == "ordering":
            return "#BBDEFB"  # Medium blue
        elif status == "ready":
            return "#FFE0B2"  # Medium orange
        elif status == "served":
            return "#E1BEE7"  # Medium purple
        return "#C8E6C9"

    def get_status_emoji(self, table_num):
        """Get status emoji for table header"""
        status = self.table_status.get(table_num, "empty")
        if status == "empty":
            return ""
        elif status == "ordering":
            return "📝"
        elif status == "ready":
            return "✅"
        elif status == "served":
            return "🍽️"
        return ""

    def get_status_text(self, table_num):
        """Get status text for table button"""
        status = self.table_status.get(table_num, "empty")
        order = self.table_orders[table_num]
        item_count = len(order)
        
        if status == "empty":
            return "VIEW"
        elif status == "ordering":
            return f"ORDERING\n({item_count} items)"
        elif status == "ready":
            return f"READY\n({item_count} items)"
        elif status == "served":
            return f"SERVED\n({item_count} items)"
        return "VIEW"

    def add_table_icons(self, parent, table_num):
        """Add status icons to table - only for kitchen bill functionality"""
        status = self.table_status.get(table_num, "empty")
        
        # Only show printer button for tables with orders (kitchen bill functionality)
        if status in ["ordering", "ready", "served"]:
            # Centered PRINT text in the middle of orange button - properly centered
            printer_btn = tk.Button(
                parent, 
                text="PRINT",
                font=("Segoe UI", 10, "bold"),
                command=lambda: self.print_table_order(table_num),
                bg="#FF9800", fg="white", relief="raised", bd=3, width=4, height=1,
                cursor="hand2"
            )
            printer_btn.pack(expand=True, pady=2)
            printer_btn.bind("<Enter>", lambda e, b=printer_btn: b.configure(bg="#F57C00"))
            printer_btn.bind("<Leave>", lambda e, b=printer_btn: b.configure(bg="#FF9800"))

    def update_table_display(self):
        """Update all table displays with current status"""
        for i, (frame, btn, icons_frame, header_frame, bill_btn, view_bill_btn) in enumerate(self.table_buttons):
            table_num = i + 1
            color = self.get_table_color(table_num)
            btn.configure(bg=color)
            header_frame.configure(bg=color)
            icons_frame.configure(bg=color)
            
            # Update header label color
            for widget in header_frame.winfo_children():
                if isinstance(widget, tk.Label):
                    widget.configure(bg=color)
            
            # Update buttons based on table status
            order = self.table_orders[table_num]
            if order:
                bill_btn.configure(state="normal", bg="#4CAF50", fg="white", text="📄\nGENERATE\nBILL")
                view_bill_btn.configure(state="normal", bg="#2196F3", fg="white", text="👁️\nVIEW\nBILL")
                # Rebind hover events for enabled state
                bill_btn.bind("<Enter>", lambda e, b=bill_btn: b.configure(bg="#45a049"))
                bill_btn.bind("<Leave>", lambda e, b=bill_btn: b.configure(bg="#4CAF50"))
                view_bill_btn.bind("<Enter>", lambda e, b=view_bill_btn: b.configure(bg="#1976D2"))
                view_bill_btn.bind("<Leave>", lambda e, b=view_bill_btn: b.configure(bg="#2196F3"))
            else:
                bill_btn.configure(state="disabled", bg="#E0E0E0", fg="#9E9E9E", text="📄\nGENERATE\nBILL")
                view_bill_btn.configure(state="disabled", bg="#E0E0E0", fg="#9E9E9E", text="👁️\nVIEW\nBILL")
                # Remove hover events for disabled state
                bill_btn.unbind("<Enter>")
                bill_btn.unbind("<Leave>")
                view_bill_btn.unbind("<Enter>")
                view_bill_btn.unbind("<Leave>")
            
            # Clear and rebuild icons
            for widget in icons_frame.winfo_children():
                widget.destroy()
            self.add_table_icons(icons_frame, table_num)

    def select_table(self, table_num):
        # This method is now replaced by open_table_menu
        self.open_table_menu(table_num)

    def refresh_table_products(self):
        term = self.var_table_search.get().strip() if hasattr(self, "var_table_search") else ""
        rows = list_products(term)
        
        # Refresh image gallery only
        self.refresh_table_gallery(rows)

    def refresh_table_gallery(self, products):
        """Refresh the product image gallery for tables"""
        # Clear previous widgets
        for w in self.table_gallery_inner.winfo_children():
            w.destroy()
        
        if not Image:
            ttk.Label(self.table_gallery_inner, text="Install Pillow to show images: pip install pillow").grid(row=0, column=0, padx=8, pady=8)
            return
        
        thumb_size = (60, 60)  # Smaller images
        self._table_gallery_images = []
        
        # Arrange in a grid: 6 columns, multiple rows for more products per row
        cols_per_row = 6
        row = 0
        col = 0
        
        for p in products:
            frame = ttk.Frame(self.table_gallery_inner, padding=2)
            frame.grid(row=row, column=col, padx=1, pady=1, sticky="nw")
            
            # Make the entire frame clickable
            img_label = ttk.Label(frame, cursor="hand2")
            img = None
            if p["image_path"] and os.path.exists(p["image_path"]):
                try:
                    pil = Image.open(p["image_path"]).convert("RGB")
                    pil.thumbnail(thumb_size)
                    img = ImageTk.PhotoImage(pil)
                except Exception:
                    img = None
            
            if img is not None:
                img_label.configure(image=img)
                img_label.image = img
                self._table_gallery_images.append(img)
            else:
                img_label.configure(text="(No Image)", width=8)
            
            # Bind click to add product
            img_label.bind("<Button-1>", lambda e, pid=p["id"]: self.add_product_id_to_table(pid))
            img_label.pack()
            
            # Smaller text labels
            name_label = ttk.Label(frame, text=p["name"][:10], width=10, wraplength=80, font=("Segoe UI", 8))
            name_label.pack()
            name_label.bind("<Button-1>", lambda e, pid=p["id"]: self.add_product_id_to_table(pid))
            
            price_label = ttk.Label(frame, text=f"₹{p['price']:.0f}", font=("Segoe UI", 8, "bold"))
            price_label.pack()
            price_label.bind("<Button-1>", lambda e, pid=p["id"]: self.add_product_id_to_table(pid))
            
            # Make the entire frame clickable
            frame.bind("<Button-1>", lambda e, pid=p["id"]: self.add_product_id_to_table(pid))
            
            # Move to next position
            col += 1
            if col >= cols_per_row:
                col = 0
                row += 1

    def add_product_id_to_table(self, pid: int):
        """Add product directly from image gallery to table order"""
        if self.current_table == 0:
            messagebox.showwarning("No Table Selected", "Please select a table first")
            return
            
        prod = [r for r in list_products("") if r["id"] == pid]
        if not prod:
            messagebox.showerror("Error", "Product not found")
            return
        prod = prod[0]
        
        if prod["stock"] <= 0:
            messagebox.showwarning("Out of Stock", f"{prod['name']} is out of stock")
            return
        
        # Add to table order
        order = self.table_orders[self.current_table]
        for item in order:
            if item["product_id"] == pid:
                if item["qty"] + 1 > prod["stock"]:
                    messagebox.showwarning("Stock Limit", f"Only {prod['stock']} units available for {prod['name']}")
                    return
                item["qty"] += 1
                break
        else:
            order.append({
                "product_id": pid,
                "name": prod["name"],
                "price": float(prod["price"]),
                "qty": 1,
            })
        
        # Update table status to ordering
        self.table_status[self.current_table] = "ordering"
        self.update_table_display()
        self.refresh_table_order()
        
        # Show success feedback
        self.show_success_feedback(f"Added {prod['name']} to Table {self.current_table}")

    def add_to_table_order(self):
        # This method is no longer used since we removed the dropdown
        # Products are now added via image gallery clicks
        pass

    def refresh_table_order(self):
        if self.current_table == 0:
            # Clear tree and show message
            for i in self.table_order_tree.get_children():
                self.table_order_tree.delete(i)
            self.table_order_tree.insert("", tk.END, values=("No table selected", "", "", ""))
            self.var_table_total.set("0.00")
            return
        
        # Clear tree
        for i in self.table_order_tree.get_children():
            self.table_order_tree.delete(i)
        
        # Populate with current table's order
        order = self.table_orders[self.current_table]
        total = 0
        
        if not order:
            self.table_order_tree.insert("", tk.END, values=("No items in order", "", "", ""))
        else:
            for idx, item in enumerate(order):
                subtotal = item["price"] * item["qty"]
                total += subtotal
                tag = "even" if idx % 2 == 0 else "odd"
                self.table_order_tree.insert("", tk.END, values=(
                    item["name"], 
                    f"₹{item['price']:.2f}", 
                    item["qty"], 
                    f"₹{subtotal:.2f}"
                ), tags=(tag,))
        
        self.var_table_total.set(f"₹{total:.2f}")

    def remove_selected_table_item(self, event=None):
        """Remove selected item from table order (double-click or button)"""
        if self.current_table == 0:
            messagebox.showwarning("No Table", "Please select a table first")
            return
        
        sel = self.table_order_tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Please select an item to remove")
            return
        
        item = self.table_order_tree.item(sel[0])
        name = item["values"][0]
        
        # Remove from table order
        order = self.table_orders[self.current_table]
        self.table_orders[self.current_table] = [i for i in order if i["name"] != name]
        self.refresh_table_order()

    def remove_from_table_order(self):
        """Legacy method - redirects to remove_selected_table_item"""
        self.remove_selected_table_item()

    def clear_table_order(self, table_num=None):
        if table_num is None:
            table_num = self.current_table
        
        if table_num == 0:
            return
        
        if messagebox.askyesno("Clear Order", f"Clear all items from Table {table_num}?"):
            self.table_orders[table_num] = []
            self.table_status[table_num] = "empty"
            if table_num == self.current_table:
                self.refresh_table_order()
            self.update_table_display()

    def generate_table_bill_direct(self, table_num):
        """Generate bill directly from table button"""
        order = self.table_orders[table_num]
        if not order:
            messagebox.showwarning("Empty Order", f"No items in Table {table_num} order")
            return
        
        # Show confirmation with order summary
        total = sum(item["price"] * item["qty"] for item in order)
        item_count = sum(item["qty"] for item in order)
        
        confirm_msg = f"Generate bill for Table {table_num}?\n\n"
        confirm_msg += f"Items: {item_count}\n"
        confirm_msg += f"Total: ₹{total:.2f}\n\n"
        confirm_msg += "This will create an invoice and clear the table order."
        
        if not messagebox.askyesno("Confirm Bill Generation", confirm_msg):
            return
        
        try:
            # Show loading message
            loading_label = ttk.Label(self.tables_tab, text="Generating bill...", 
                                    font=("Segoe UI", 10, "bold"), foreground="blue")
            loading_label.place(relx=0.5, rely=0.5, anchor="center")
            self.update()
            
            bill_id, total = create_bill(order)
            path = save_invoice_text(bill_id)
            
            # Remove loading message
            loading_label.destroy()
            
            # Clear table after billing - reset to empty state
            self.table_status[table_num] = "empty"
            self.table_orders[table_num] = []
            
            # Update current table if it's the same
            if self.current_table == table_num:
                self.refresh_table_order()
            
            self.update_table_display()
            self.update_active_orders_count()
            self.refresh_products()  # stock changed
            self.refresh_billing_products()
            self.refresh_reports()
            
            if path:
                # Success message
                success_msg = f"✅ Bill Generated Successfully!\n\n"
                success_msg += f"Bill ID: {bill_id}\n"
                success_msg += f"Table: {table_num}\n"
                success_msg += f"Total: ₹{total:.2f}\n"
                success_msg += f"Items: {item_count}\n\n"
                success_msg += f"Invoice saved to:\n{path}"
                
                messagebox.showinfo("Bill Generated", success_msg)
                self.show_invoice_preview(bill_id, path)
                self.show_success_feedback(f"Table {table_num} bill generated!")
            else:
                messagebox.showinfo("Done", f"Table {table_num} bill #{bill_id} saved.")
        except Exception as e:
            # Remove loading message if it exists
            try:
                loading_label.destroy()
            except:
                pass
            messagebox.showerror("Error", f"Failed to create bill:\n{str(e)}")

    def generate_table_bill(self):
        if self.current_table == 0:
            messagebox.showwarning("No Table Selected", "Please select a table first")
            return
        
        order = self.table_orders[self.current_table]
        if not order:
            messagebox.showwarning("Empty Order", f"No items in Table {self.current_table} order")
            return
        
        # Show confirmation with order summary
        total = sum(item["price"] * item["qty"] for item in order)
        item_count = sum(item["qty"] for item in order)
        
        confirm_msg = f"Generate bill for Table {self.current_table}?\n\n"
        confirm_msg += f"Items: {item_count}\n"
        confirm_msg += f"Total: ₹{total:.2f}\n\n"
        confirm_msg += "This will create an invoice and clear the table order."
        
        if not messagebox.askyesno("Confirm Bill Generation", confirm_msg):
            return
        
        try:
            # Show loading message
            loading_label = ttk.Label(self.tables_tab, text="Generating bill...", 
                                    font=("Segoe UI", 10, "bold"), foreground="blue")
            loading_label.place(relx=0.5, rely=0.5, anchor="center")
            self.update()
            
            bill_id, total = create_bill(order)
            path = save_invoice_text(bill_id)
            
            # Remove loading message
            loading_label.destroy()
            
            # Clear table after billing - reset to empty state
            self.table_status[self.current_table] = "empty"
            self.table_orders[self.current_table] = []
            self.refresh_table_order()
            self.update_table_display()
            self.update_active_orders_count()
            self.refresh_products()  # stock changed
            self.refresh_billing_products()
            self.refresh_reports()
            
            if path:
                # Success message
                success_msg = f"✅ Bill Generated Successfully!\n\n"
                success_msg += f"Bill ID: {bill_id}\n"
                success_msg += f"Table: {self.current_table}\n"
                success_msg += f"Total: ₹{total:.2f}\n"
                success_msg += f"Items: {item_count}\n\n"
                success_msg += f"Invoice saved to:\n{path}"
                
                messagebox.showinfo("Bill Generated", success_msg)
                self.show_invoice_preview(bill_id, path)
                self.show_success_feedback(f"Table {self.current_table} bill generated!")
            else:
                messagebox.showinfo("Done", f"Table {self.current_table} bill #{bill_id} saved.")
        except Exception as e:
            # Remove loading message if it exists
            try:
                loading_label.destroy()
            except:
                pass
            messagebox.showerror("Error", f"Failed to create bill:\n{str(e)}")

    def print_table_order(self, table_num):
        """Print table order (kitchen order)"""
        order = self.table_orders.get(table_num, [])
        if not order:
            messagebox.showwarning("Empty Order", f"Table {table_num} has no items to print")
            return
        
        # Create kitchen order text
        lines = []
        lines.append(f"=== KITCHEN ORDER - TABLE {table_num} ===")
        lines.append(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("Items:")
        for item in order:
            lines.append(f"- {item['name']} x {item['qty']}")
        lines.append("")
        lines.append("=== END ORDER ===")
        
        # Save to file
        kitchen_file = os.path.join(INVOICE_DIR, f"kitchen-order-table-{table_num}.txt")
        with open(kitchen_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        
        # Print if possible
        try:
            if hasattr(os, "startfile"):
                os.startfile(kitchen_file, "print")
                messagebox.showinfo("Printed", f"Kitchen order for Table {table_num} sent to printer")
            else:
                messagebox.showinfo("Saved", f"Kitchen order saved to {kitchen_file}")
        except Exception as e:
            messagebox.showinfo("Saved", f"Kitchen order saved to {kitchen_file}")

    def view_table_order(self, table_num):
        """View table order details"""
        order = self.table_orders.get(table_num, [])
        if not order:
            messagebox.showinfo("Empty Order", f"Table {table_num} has no items")
            return
        
        # Create order summary
        total = sum(item["price"] * item["qty"] for item in order)
        lines = []
        lines.append(f"Table {table_num} Order Summary")
        lines.append("=" * 30)
        for item in order:
            subtotal = item["price"] * item["qty"]
            lines.append(f"{item['name']} x {item['qty']} = ₹{subtotal:.2f}")
        lines.append("-" * 30)
        lines.append(f"Total: ₹{total:.2f}")
        
        messagebox.showinfo(f"Table {table_num} Order", "\n".join(lines))

    def view_table_bill_direct(self, table_num):
        """View table bill directly from table button"""
        order = self.table_orders.get(table_num, [])
        if not order:
            messagebox.showinfo(f"Table {table_num}", "No items in order")
            return
        
        # Create a detailed view window
        view_window = tk.Toplevel(self.master)
        view_window.title(f"Table {table_num} - Order Details")
        view_window.geometry("500x400")
        view_window.resizable(False, False)
        
        # Center the window
        view_window.transient(self.master)
        view_window.grab_set()
        
        # Header
        header_frame = ttk.Frame(view_window)
        header_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(header_frame, text=f"Table {table_num} Order", 
                 font=("Segoe UI", 16, "bold")).pack()
        
        # Order details
        details_frame = ttk.LabelFrame(view_window, text="Order Items")
        details_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Treeview for order items
        tree = ttk.Treeview(details_frame, columns=("qty", "price", "subtotal"), show="headings", height=8)
        tree.heading("#0", text="Item")
        tree.heading("qty", text="Qty")
        tree.heading("price", text="Price")
        tree.heading("subtotal", text="Subtotal")
        
        tree.column("#0", width=200)
        tree.column("qty", width=80)
        tree.column("price", width=100)
        tree.column("subtotal", width=100)
        
        # Add items to tree
        total = 0
        for idx, item in enumerate(order):
            subtotal = item["price"] * item["qty"]
            total += subtotal
            tag = "even" if idx % 2 == 0 else "odd"
            tree.insert("", tk.END, text=item["name"], 
                       values=(item["qty"], f"₹{item['price']:.2f}", f"₹{subtotal:.2f}"), 
                       tags=(tag,))
        
        tree.tag_configure("even", background="#f5f7fb")
        tree.tag_configure("odd", background="#ffffff")
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(details_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Total section
        total_frame = ttk.Frame(view_window)
        total_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(total_frame, text=f"Total: ₹{total:.2f}", 
                 font=("Segoe UI", 14, "bold")).pack(side=tk.LEFT)
        
        # Action buttons
        action_frame = ttk.Frame(view_window)
        action_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(action_frame, text="Close", 
                  command=view_window.destroy).pack(side=tk.RIGHT, padx=5)
        
        ttk.Button(action_frame, text="Generate Bill", 
                  command=lambda: [self.generate_table_bill_direct(table_num), view_window.destroy()]).pack(side=tk.RIGHT, padx=5)

    def refresh_tables(self):
        if hasattr(self, 'refresh_table_products'):
            self.refresh_table_products()

    def show_success_feedback(self, message: str):
        """Show temporary success message"""
        # Create a temporary label for feedback
        feedback_label = ttk.Label(self.tables_tab, text=message, 
                                 font=("Segoe UI", 10, "bold"), 
                                 foreground="green")
        feedback_label.place(relx=0.5, rely=0.1, anchor="center")
        
        # Remove after 2 seconds
        self.after(2000, feedback_label.destroy)

    def update_active_orders_count(self):
        """Update the active orders count in the header"""
        if hasattr(self, 'var_active_orders'):
            active_count = sum(1 for status in self.table_status.values() if status in ["ordering", "ready"])
            self.var_active_orders.set(f"Active: {active_count}")

    # Reports Tab
    def build_reports_tab(self):
        # Create notebook for different report views
        self.reports_notebook = ttk.Notebook(self.reports_tab)
        self.reports_notebook.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        # Daily Sales Tab
        self.daily_sales_tab = ttk.Frame(self.reports_notebook)
        self.reports_notebook.add(self.daily_sales_tab, text="Daily Sales")

        # All Bills Tab
        self.all_bills_tab = ttk.Frame(self.reports_notebook)
        self.reports_notebook.add(self.all_bills_tab, text="All Bills")

        self.build_daily_sales_tab()
        self.build_all_bills_tab()

    def build_daily_sales_tab(self):
        # Header with date selection and controls
        header_frame = ttk.Frame(self.daily_sales_tab)
        header_frame.pack(fill=tk.X, padx=15, pady=15)
        
        # Date selection
        date_frame = ttk.Frame(header_frame)
        date_frame.pack(side=tk.LEFT)
        ttk.Label(date_frame, text="📅 Select Date:", font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
        self.var_sales_date = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        date_entry = ttk.Entry(date_frame, textvariable=self.var_sales_date, width=15, font=("Segoe UI", 10))
        date_entry.pack(side=tk.LEFT, padx=10)
        date_entry.bind("<KeyRelease>", lambda e: self.refresh_daily_sales())
        
        # Control buttons
        buttons_frame = ttk.Frame(header_frame)
        buttons_frame.pack(side=tk.RIGHT)
        
        ttk.Button(buttons_frame, text="🔄 Refresh", command=self.refresh_daily_sales).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="📤 Export Daily CSV", command=self.export_daily_csv).pack(side=tk.LEFT, padx=5)

        # Enhanced summary
        summary_frame = ttk.LabelFrame(self.daily_sales_tab, text="📊 Daily Summary - Complete Details")
        summary_frame.pack(fill=tk.X, padx=10, pady=5)
        
        stats_frame = ttk.Frame(summary_frame)
        stats_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.var_daily_count = tk.StringVar(value="0")
        self.var_daily_total = tk.StringVar(value="₹0.00")
        self.var_daily_avg = tk.StringVar(value="₹0.00")
        self.var_daily_items = tk.StringVar(value="0")
        
        ttk.Label(stats_frame, text="Bills:", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(stats_frame, textvariable=self.var_daily_count, font=("Segoe UI", 10, "bold"), foreground="blue").grid(row=0, column=1, sticky="w", padx=5, pady=2)
        
        ttk.Label(stats_frame, text="Total Revenue:", font=("Segoe UI", 10, "bold")).grid(row=0, column=2, sticky="w", padx=20, pady=2)
        ttk.Label(stats_frame, textvariable=self.var_daily_total, font=("Segoe UI", 10, "bold"), foreground="green").grid(row=0, column=3, sticky="w", padx=5, pady=2)
        
        ttk.Label(stats_frame, text="Avg Bill:", font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(stats_frame, textvariable=self.var_daily_avg, font=("Segoe UI", 10, "bold"), foreground="orange").grid(row=1, column=1, sticky="w", padx=5, pady=2)
        
        ttk.Label(stats_frame, text="Total Items:", font=("Segoe UI", 10, "bold")).grid(row=1, column=2, sticky="w", padx=20, pady=2)
        ttk.Label(stats_frame, textvariable=self.var_daily_items, font=("Segoe UI", 10, "bold"), foreground="purple").grid(row=1, column=3, sticky="w", padx=5, pady=2)

        # Main content frame
        content_frame = ttk.Frame(self.daily_sales_tab)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Left side - Daily bills
        bills_frame = ttk.LabelFrame(content_frame, text="📋 Daily Bills - Complete Details")
        bills_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        self.daily_bills_tree = ttk.Treeview(
            bills_frame,
            columns=("id", "time", "total", "items", "qty"),
            show="headings",
            height=12,
        )
        for col, text in [("id", "Bill #"), ("time", "Time"), ("total", "Total ₹"), ("items", "Items"), ("qty", "Qty")]:
            self.daily_bills_tree.heading(col, text=text)
            self.daily_bills_tree.column(col, width=100)
        self.daily_bills_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.daily_bills_tree.tag_configure("even", background="#f5f7fb")
        self.daily_bills_tree.tag_configure("odd", background="#ffffff")
        self.daily_bills_tree.bind("<<TreeviewSelect>>", self.on_select_daily_bill)

        # Right side - Bill items
        items_frame = ttk.LabelFrame(content_frame, text="🧾 Bill Items - Complete Details")
        items_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        self.daily_bill_items_tree = ttk.Treeview(
            items_frame,
            columns=("product_id", "name", "qty", "price", "subtotal", "current_stock"),
            show="headings",
            height=12,
        )
        for col, text in [("product_id", "PID"), ("name", "Product Name"), ("qty", "Qty"), ("price", "Price ₹"), ("subtotal", "Subtotal ₹"), ("current_stock", "Current Stock")]:
            self.daily_bill_items_tree.heading(col, text=text)
            self.daily_bill_items_tree.column(col, width=100)
        self.daily_bill_items_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.daily_bill_items_tree.tag_configure("even", background="#f5f7fb")
        self.daily_bill_items_tree.tag_configure("odd", background="#ffffff")

        self.refresh_daily_sales()

    def build_all_bills_tab(self):
        # Header with controls
        header_frame = ttk.Frame(self.all_bills_tab)
        header_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(header_frame, text="🔄 Refresh All", command=self.refresh_reports).pack(side=tk.LEFT, padx=5)
        ttk.Button(header_frame, text="📤 Export CSV", command=self.export_bills_csv).pack(side=tk.LEFT, padx=5)
        
        # Summary stats
        stats_frame = ttk.Frame(header_frame)
        stats_frame.pack(side=tk.RIGHT)
        
        self.var_total_bills = tk.StringVar(value="Total Bills: 0")
        self.var_total_revenue = tk.StringVar(value="Revenue: ₹0.00")
        ttk.Label(stats_frame, textvariable=self.var_total_bills, font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=5)
        ttk.Label(stats_frame, textvariable=self.var_total_revenue, font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=5)

        # Main content frame
        content_frame = ttk.Frame(self.all_bills_tab)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Bills and items section
        bills_items_frame = ttk.Frame(content_frame)
        bills_items_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left side - Bills list
        bills_frame = ttk.LabelFrame(bills_items_frame, text="📋 All Bills - Complete Details")
        bills_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        self.bills_tree = ttk.Treeview(
            bills_frame,
            columns=("id", "created", "total", "items", "qty"),
            show="headings",
            height=15,
        )
        for col, text in [("id", "Bill #"), ("created", "Date & Time"), ("total", "Total ₹"), ("items", "Items"), ("qty", "Qty")]:
            self.bills_tree.heading(col, text=text)
            self.bills_tree.column(col, width=120)
        self.bills_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.bills_tree.tag_configure("even", background="#f5f7fb")
        self.bills_tree.tag_configure("odd", background="#ffffff")
        self.bills_tree.bind("<<TreeviewSelect>>", self.on_select_bill)

        # Right side - Bill items details
        items_frame = ttk.LabelFrame(bills_items_frame, text="🧾 Bill Items - Complete Details")
        items_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        self.bill_items_tree = ttk.Treeview(
            items_frame,
            columns=("product_id", "name", "qty", "price", "subtotal", "current_stock"),
            show="headings",
            height=15,
        )
        for col, text in [("product_id", "PID"), ("name", "Product Name"), ("qty", "Qty"), ("price", "Price ₹"), ("subtotal", "Subtotal ₹"), ("current_stock", "Current Stock")]:
            self.bill_items_tree.heading(col, text=text)
            self.bill_items_tree.column(col, width=100)
        self.bill_items_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.bill_items_tree.tag_configure("even", background="#f5f7fb")
        self.bill_items_tree.tag_configure("odd", background="#ffffff")


        self.refresh_reports()


    def refresh_reports(self):
        # Clear existing data
        for i in self.bills_tree.get_children():
            self.bills_tree.delete(i)
        for i in self.bill_items_tree.get_children():
            self.bill_items_tree.delete(i)
        
        # Get all bills with comprehensive details
        bills = get_all_bills()
        total_revenue = 0
        
        print(f"Found {len(bills)} bills in database")  # Debug print
        
        if not bills:
            # Show a message if no bills found
            self.bills_tree.insert("", tk.END, values=(
                "No bills", "No bills found in database", "", "", ""
            ))
        
        for idx, bill in enumerate(bills):
            tag = "even" if idx % 2 == 0 else "odd"
            # Format date and time properly
            date_time = bill["created_at"]
            if " " in date_time:
                date_part, time_part = date_time.split(" ", 1)
                # Format date as DD-MM-YYYY and time as HH:MM
                try:
                    dt = datetime.strptime(date_time, "%Y-%m-%d %H:%M:%S")
                    formatted_time = dt.strftime("%d-%m-%Y %H:%M")
                except:
                    formatted_time = f"{date_part} {time_part}"
            else:
                formatted_time = date_time
                
            self.bills_tree.insert("", tk.END, values=(
                bill["id"], 
                formatted_time, 
                f"₹{bill['total']:.2f}",
                bill["item_count"],
                bill["total_qty"]
            ), tags=(tag,))
            total_revenue += bill["total"]
        
        # Update summary stats
        self.var_total_bills.set(f"Total Bills: {len(bills)}")
        self.var_total_revenue.set(f"Revenue: ₹{total_revenue:.2f}")

    def refresh_daily_sales(self):
        date_str = self.var_sales_date.get().strip()
        if not date_str:
            return
        try:
            # Validate date format
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Invalid Date", "Please use YYYY-MM-DD format")
            return
        
        bills = get_daily_sales(date_str)
        total_sales = sum(bill["total"] for bill in bills)
        avg_bill = total_sales / len(bills) if bills else 0
        
        # Get comprehensive bill data
        comprehensive_bills = []
        total_items = 0
        for bill in bills:
            # Get item count and total quantity for each bill
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) as item_count, SUM(qty) as total_qty 
                FROM bill_items WHERE bill_id = ?
            """, (bill["id"],))
            result = cur.fetchone()
            conn.close()
            
            comprehensive_bills.append({
                **bill,
                "item_count": result["item_count"] or 0,
                "total_qty": result["total_qty"] or 0
            })
            total_items += result["total_qty"] or 0
        
        # Update summary stats
        self.var_daily_count.set(str(len(bills)))
        self.var_daily_total.set(f"₹{total_sales:.2f}")
        self.var_daily_avg.set(f"₹{avg_bill:.2f}")
        self.var_daily_items.set(str(total_items))
        
        # Clear and populate daily bills with comprehensive details
        for i in self.daily_bills_tree.get_children():
            self.daily_bills_tree.delete(i)
        for idx, bill in enumerate(comprehensive_bills):
            # Format time properly
            date_time = bill["created_at"]
            if " " in date_time:
                try:
                    dt = datetime.strptime(date_time, "%Y-%m-%d %H:%M:%S")
                    time_str = dt.strftime("%H:%M")
                except:
                    time_str = date_time.split(" ")[1] if " " in date_time else date_time
            else:
                time_str = date_time
            tag = "even" if idx % 2 == 0 else "odd"
            self.daily_bills_tree.insert("", tk.END, values=(
                bill["id"], 
                time_str, 
                f"₹{bill['total']:.2f}",
                bill["item_count"],
                bill["total_qty"]
            ), tags=(tag,))
        
        # Clear bill items
        for i in self.daily_bill_items_tree.get_children():
            self.daily_bill_items_tree.delete(i)

    def on_select_daily_bill(self, event=None):
        sel = self.daily_bills_tree.selection()
        if not sel:
            return
        
        try:
            bill_id = int(self.daily_bills_tree.item(sel[0])["values"][0])
            
            # Get comprehensive bill items
            rows = get_comprehensive_bill_items(bill_id)
            
            # Clear existing items
            for i in self.daily_bill_items_tree.get_children():
                self.daily_bill_items_tree.delete(i)
            
            # Add comprehensive details
            if rows:
                for idx, r in enumerate(rows):
                    tag = "even" if idx % 2 == 0 else "odd"
                    self.daily_bill_items_tree.insert("", tk.END, values=(
                        r["product_id"],
                        r["name"], 
                        r["qty"], 
                        f"₹{r['price']:.2f}", 
                        f"₹{r['subtotal']:.2f}",
                        r["current_stock"]
                    ), tags=(tag,))
            else:
                # Show a message if no items found
                self.daily_bill_items_tree.insert("", tk.END, values=(
                    "No items", "No items found for this bill", "", "", "", ""
                ))
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load bill items: {e}")
            # Also clear the items tree on error
            for i in self.daily_bill_items_tree.get_children():
                self.daily_bill_items_tree.delete(i)

    def on_select_bill(self, event=None):
        sel = self.bills_tree.selection()
        if not sel:
            return
        bill_id = int(self.bills_tree.item(sel[0])["values"][0])
        
        # Get comprehensive bill items
        rows = get_comprehensive_bill_items(bill_id)
        
        # Clear existing items
        for i in self.bill_items_tree.get_children():
            self.bill_items_tree.delete(i)
        
        # Add comprehensive details
        for idx, r in enumerate(rows):
            tag = "even" if idx % 2 == 0 else "odd"
            self.bill_items_tree.insert("", tk.END, values=(
                r["product_id"],
                r["name"], 
                r["qty"], 
                f"₹{r['price']:.2f}", 
                f"₹{r['subtotal']:.2f}",
                r["current_stock"]
            ), tags=(tag,))

    def show_analytics(self):
        """Show comprehensive sales analytics"""
        try:
            summary, top_products, daily_trend = get_sales_analytics()
            
            # Create analytics window
            analytics_window = tk.Toplevel(self.master)
            analytics_window.title("📊 Sales Analytics - Complete Details")
            analytics_window.geometry("800x600")
            analytics_window.transient(self.master)
            analytics_window.grab_set()
            
            # Main frame
            main_frame = ttk.Frame(analytics_window)
            main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # Summary section
            summary_frame = ttk.LabelFrame(main_frame, text="📈 Overall Summary")
            summary_frame.pack(fill=tk.X, padx=5, pady=5)
            
            summary_text = f"""
Total Bills: {summary['total_bills']:,}
Total Revenue: ₹{summary['total_revenue']:.2f}
Average Bill Value: ₹{summary['avg_bill_value']:.2f}
First Sale: {summary['first_sale']}
Last Sale: {summary['last_sale']}
            """
            ttk.Label(summary_frame, text=summary_text, font=("Segoe UI", 10)).pack(padx=10, pady=5)
            
            # Top products section
            products_frame = ttk.LabelFrame(main_frame, text="🏆 Top Selling Products")
            products_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            products_tree = ttk.Treeview(products_frame, columns=("name", "sold", "revenue"), show="headings", height=8)
            products_tree.heading("name", text="Product Name")
            products_tree.heading("sold", text="Total Sold")
            products_tree.heading("revenue", text="Revenue ₹")
            products_tree.column("name", width=300)
            products_tree.column("sold", width=100)
            products_tree.column("revenue", width=150)
            products_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            
            for idx, product in enumerate(top_products):
                tag = "even" if idx % 2 == 0 else "odd"
                products_tree.insert("", tk.END, values=(
                    product["name"],
                    f"{product['total_sold']:,}",
                    f"₹{product['total_revenue']:.2f}"
                ), tags=(tag,))
            
            products_tree.tag_configure("even", background="#f5f7fb")
            products_tree.tag_configure("odd", background="#ffffff")
            
            # Close button
            ttk.Button(main_frame, text="Close", command=analytics_window.destroy).pack(pady=10)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load analytics: {str(e)}")

    def export_bills_csv(self):
        """Export all bills to CSV file"""
        try:
            bills = get_all_bills()
            if not bills:
                messagebox.showwarning("No Data", "No bills found to export")
                return
            
            filename = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                title="Export Bills to CSV"
            )
            
            if filename:
                with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(['Bill ID', 'Date & Time', 'Total ₹', 'Item Count', 'Total Quantity'])
                    
                    for bill in bills:
                        writer.writerow([
                            bill['id'],
                            bill['created_at'],
                            f"{bill['total']:.2f}",
                            bill['item_count'],
                            bill['total_qty']
                        ])
                
                messagebox.showinfo("Success", f"Exported {len(bills)} bills to {filename}")
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export: {str(e)}")

    def export_daily_csv(self):
        """Export daily sales to CSV file"""
        try:
            date_str = self.var_sales_date.get().strip()
            if not date_str:
                messagebox.showwarning("No Date", "Please select a date first")
                return
                
            bills = get_daily_sales(date_str)
            if not bills:
                messagebox.showwarning("No Data", f"No sales found for {date_str}")
                return
            
            filename = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                title=f"Export Daily Sales for {date_str}"
            )
            
            if filename:
                with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(['Date', 'Bill ID', 'Time', 'Total ₹', 'Item Count', 'Total Quantity'])
                    
                    for bill in bills:
                        time_str = bill["created_at"].split(" ")[1] if " " in bill["created_at"] else bill["created_at"]
                        # Get item count and total quantity
                        conn = get_conn()
                        cur = conn.cursor()
                        cur.execute("""
                            SELECT COUNT(*) as item_count, SUM(qty) as total_qty 
                            FROM bill_items WHERE bill_id = ?
                        """, (bill["id"],))
                        result = cur.fetchone()
                        conn.close()
                        
                        writer.writerow([
                            date_str,
                            bill['id'],
                            time_str,
                            f"{bill['total']:.2f}",
                            result["item_count"] or 0,
                            result["total_qty"] or 0
                        ])
                
                messagebox.showinfo("Success", f"Exported {len(bills)} bills for {date_str} to {filename}")
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export daily sales: {str(e)}")

    # Backup / Restore handlers
    def on_backup(self):
        default = os.path.join(BACKUP_DIR, f"products-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv")
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile=os.path.basename(default),
            initialdir=BACKUP_DIR,
        )
        if not path:
            return
        try:
            backup_products_csv(path)
            messagebox.showinfo("Backup", f"Products saved to\n{path}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def on_restore(self):
        path = filedialog.askopenfilename(
            filetypes=[("CSV files", "*.csv")],
            initialdir=BACKUP_DIR,
        )
        if not path:
            return
        try:
            count = restore_products_csv(path)
            self.refresh_products()
            self.refresh_billing_products()
            messagebox.showinfo("Restore", f"Added {count} products from file")
        except Exception as e:
            messagebox.showerror("Error", str(e))


def fix_data_mismatch():
    """Check for data mismatch between bill_items and products (without auto-creating products)"""
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # Get all product IDs that exist in products table
        cur.execute("SELECT id FROM products ORDER BY id")
        existing_product_ids = [row[0] for row in cur.fetchall()]
        print(f"Existing product IDs: {existing_product_ids}")
        
        if not existing_product_ids:
            print("No products found, cannot check data mismatch")
            return
        
        # Get all unique product_ids referenced in bill_items
        cur.execute("SELECT DISTINCT product_id FROM bill_items ORDER BY product_id")
        referenced_product_ids = [row[0] for row in cur.fetchall()]
        print(f"Referenced product IDs in bill_items: {referenced_product_ids}")
        
        # Find missing product IDs
        missing_product_ids = [pid for pid in referenced_product_ids if pid not in existing_product_ids]
        print(f"Missing product IDs: {missing_product_ids}")
        
        if missing_product_ids:
            print("Found orphaned bill_items referencing deleted products. These will be ignored.")
            # Note: We don't recreate products anymore - deleted products stay deleted
        else:
            print("No data mismatch found")
            
    except Exception as e:
        print(f"Error checking data mismatch: {e}")
    finally:
        conn.close()

def create_sample_data():
    """Create sample data for testing"""
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # Check if data already exists
        cur.execute("SELECT COUNT(*) FROM products")
        product_count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM bills")
        bill_count = cur.fetchone()[0]
        
        print(f"Found {product_count} products and {bill_count} bills in database")
        
        if product_count == 0:
            # Add sample products
            sample_products = [
                ("Pizza Margherita", 250.0, 50, "images/pizza.png"),
                ("Burger Deluxe", 180.0, 30, "images/burger.png"),
                ("Pasta Carbonara", 220.0, 25, "images/pasta.png"),
                ("Chicken Wings", 150.0, 40, "images/wings.png"),
                ("Caesar Salad", 120.0, 20, "images/salad.png"),
                ("Coca Cola", 30.0, 100, "images/coke.png")
            ]
            
            for name, price, stock, image in sample_products:
                cur.execute("INSERT INTO products (name, price, stock, image_path) VALUES (?, ?, ?, ?)",
                           (name, price, stock, image))
            
            print("Sample products created successfully!")
        
        if bill_count == 0:
            # Create sample bills for today and yesterday
            today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
            
            # Bill 1 - Today
            cur.execute("INSERT INTO bills (created_at, total) VALUES (?, ?)", (today, 450.0))
            bill_id_1 = cur.lastrowid
            
            # Bill 2 - Yesterday
            cur.execute("INSERT INTO bills (created_at, total) VALUES (?, ?)", (yesterday, 320.0))
            bill_id_2 = cur.lastrowid
            
            # Add sample bill items for bill 1
            sample_items_1 = [
                (bill_id_1, 1, 2, 250.0, 500.0),  # 2x Pizza
                (bill_id_1, 2, 1, 180.0, 180.0),  # 1x Burger
                (bill_id_1, 6, 2, 30.0, 60.0)     # 2x Coke
            ]
            
            # Add sample bill items for bill 2
            sample_items_2 = [
                (bill_id_2, 3, 1, 220.0, 220.0),  # 1x Pasta
                (bill_id_2, 4, 2, 150.0, 300.0),  # 2x Wings
                (bill_id_2, 5, 1, 120.0, 120.0)   # 1x Salad
            ]
            
            for bill_id, product_id, qty, price, subtotal in sample_items_1 + sample_items_2:
                cur.execute("INSERT INTO bill_items (bill_id, product_id, qty, price, subtotal) VALUES (?, ?, ?, ?, ?)",
                           (bill_id, product_id, qty, price, subtotal))
            
            conn.commit()
            print("Sample bills created successfully!")
        else:
            print("Bills already exist, skipping creation")
            
        # Always try to fix data mismatch
        fix_data_mismatch()
            
    except Exception as e:
        print(f"Error creating sample data: {e}")
        conn.rollback()
    finally:
        conn.close()

def main():
    init_db()
    create_sample_data()  # Create sample data for testing
    root = tk.Tk()
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()



