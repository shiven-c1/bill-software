import os
import sqlite3
from datetime import datetime
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None


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
    cur.execute("DELETE FROM products WHERE id=?", (int(pid),))
    conn.commit()
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


def save_invoice_text(bill_id: int):
    rows = get_bill_items(bill_id)
    bills = [b for b in get_recent_bills(10000) if b["id"] == bill_id]
    if not bills:
        return None
    bill = bills[0]
    filepath = os.path.join(INVOICE_DIR, f"invoice-{bill_id}.txt")
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
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.inventory_tab = ttk.Frame(self.notebook)
        self.billing_tab = ttk.Frame(self.notebook)
        self.reports_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.inventory_tab, text="Inventory")
        self.notebook.add(self.billing_tab, text="Billing")
        self.notebook.add(self.reports_tab, text="Reports")

        self.build_inventory_tab()
        self.build_billing_tab()
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

    def build_header(self):
        header = tk.Frame(self, bg="#2b74ff")
        header.pack(fill=tk.X)
        tk.Label(header, text="Simple Billing & Inventory", font=self.title_font, fg="white", bg="#2b74ff").pack(anchor=tk.W, padx=12, pady=(10, 0))
        tk.Label(header, text="Manage products, generate invoices, and view reports — easy!", font=self.subtitle_font, fg="white", bg="#2b74ff").pack(anchor=tk.W, padx=12, pady=(0, 10))

    def build_statusbar(self):
        self.status_var = tk.StringVar(value="Ready")
        bar = tk.Label(self, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W)
        bar.pack(fill=tk.X, side=tk.BOTTOM)

    def set_status(self, text: str):
        if hasattr(self, "status_var"):
            self.status_var.set(text)

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
        help_menu.add_command(label="About", command=lambda: messagebox.showinfo(
            "About",
            "Simple Billing & Inventory\nData stored locally (SQLite).\nMade easy for everyone.",
        ))
        menubar.add_cascade(label="Help", menu=help_menu)

        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="Company Profile", command=self.open_company_profile)
        menubar.add_cascade(label="Settings", menu=settings_menu)

    # Inventory Tab
    def build_inventory_tab(self):
        form = ttk.LabelFrame(self.inventory_tab, text="Add / Edit Product")
        form.pack(fill=tk.X, padx=10, pady=10)

        self.var_pid = tk.StringVar()
        self.var_name = tk.StringVar()
        self.var_price = tk.StringVar()
        self.var_stock = tk.StringVar()
        self.var_image_path = tk.StringVar()

        row = ttk.Frame(form)
        row.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(row, text="Name:").pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.var_name, width=40).pack(side=tk.LEFT, padx=5)

        row2 = ttk.Frame(form)
        row2.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(row2, text="Price:").pack(side=tk.LEFT)
        ttk.Entry(row2, textvariable=self.var_price, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Label(row2, text="Stock:").pack(side=tk.LEFT)
        ttk.Entry(row2, textvariable=self.var_stock, width=10).pack(side=tk.LEFT, padx=5)

        row3 = ttk.Frame(form)
        row3.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(row3, text="Image:").pack(side=tk.LEFT)
        ttk.Entry(row3, textvariable=self.var_image_path, width=50).pack(side=tk.LEFT, padx=5)
        ttk.Button(row3, text="Choose...", command=self.on_choose_image).pack(side=tk.LEFT)

        preview_row = ttk.Frame(form)
        preview_row.pack(fill=tk.X, padx=10, pady=5)
        self.image_preview_label = ttk.Label(preview_row, text="No image selected")
        self.image_preview_label.pack(side=tk.LEFT)

        btns = ttk.Frame(form)
        btns.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(btns, text="Add New", command=self.on_add_product).pack(side=tk.LEFT)
        ttk.Button(btns, text="Update", command=self.on_update_product).pack(side=tk.LEFT, padx=5)
        ttk.Button(btns, text="Delete", command=self.on_delete_product).pack(side=tk.LEFT)
        ttk.Button(btns, text="Clear", command=self.clear_product_form).pack(side=tk.LEFT, padx=5)

        search_row = ttk.Frame(self.inventory_tab)
        search_row.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(search_row, text="Search:").pack(side=tk.LEFT)
        self.var_search = tk.StringVar()
        search_entry = ttk.Entry(search_row, textvariable=self.var_search)
        search_entry.pack(side=tk.LEFT, padx=5)
        search_entry.bind("<KeyRelease>", lambda e: self.refresh_products())

        self.products_tree = ttk.Treeview(
            self.inventory_tab,
            columns=("id", "name", "price", "stock"),
            show="headings",
            height=12,
        )
        for col, text in [("id", "ID"), ("name", "Name"), ("price", "Price"), ("stock", "Stock")]:
            self.products_tree.heading(col, text=text)
            self.products_tree.column(col, width=110 if col != "name" else 360)
        self.products_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.products_tree.bind("<<TreeviewSelect>>", self.on_select_product)
        self.products_tree.tag_configure("even", background="#f5f7fb")
        self.products_tree.tag_configure("odd", background="#ffffff")

        self.refresh_products()

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
        pid, name, price, stock = item["values"]
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
            self.products_tree.insert("", tk.END, values=(r["id"], r["name"], r["price"], r["stock"]), tags=(tag,))

    def on_add_product(self):
        name = self.var_name.get().strip()
        price = self.var_price.get().strip()
        stock = self.var_stock.get().strip()
        if not name or not price or not stock:
            messagebox.showwarning("Missing", "Please fill Name, Price and Stock")
            return
        try:
            price_val = float(price)
            stock_val = int(stock)
            if price_val < 0 or stock_val < 0:
                raise ValueError
        except Exception:
            messagebox.showerror("Invalid", "Price must be a number, Stock must be a whole number")
            return
        img_path = self.copy_image_to_library(self.var_image_path.get().strip()) if self.var_image_path.get().strip() else None
        ok, err = add_product(name, price_val, stock_val, img_path)
        if ok:
            self.clear_product_form()
            self.refresh_products()
            # update billing choices/gallery immediately
            self.refresh_product_choices()
            messagebox.showinfo("Saved", "Product added")
        else:
            messagebox.showerror("Error", f"Could not add product. {err}")

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
            self.refresh_product_choices()
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
        self.refresh_product_choices()
        messagebox.showinfo("Deleted", "Product deleted")

    def on_tab_changed(self, event=None):
        try:
            tab = self.notebook.tab(self.notebook.select(), 'text')
            if tab == "Billing":
                self.refresh_product_choices()
            elif tab == "Reports":
                self.refresh_reports()
        except Exception:
            pass

    # Billing Tab
    def build_billing_tab(self):
        top = ttk.LabelFrame(self.billing_tab, text="Add Item to Cart")
        top.pack(fill=tk.X, padx=10, pady=10)

        # Top actions so important buttons are always visible
        actions = ttk.Frame(self.billing_tab)
        actions.pack(fill=tk.X, padx=10, pady=4)
        ttk.Button(actions, text="Refresh", command=self.refresh_product_choices).pack(side=tk.LEFT)
        ttk.Button(actions, text="Generate Invoice", command=self.on_checkout).pack(side=tk.RIGHT)
        ttk.Button(actions, text="Remove Selected", command=self.on_remove_cart_item).pack(side=tk.RIGHT, padx=6)

        self.var_bill_product = tk.StringVar()
        self.var_bill_qty = tk.StringVar(value="1")

        row = ttk.Frame(top)
        row.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(row, text="Search Product:").pack(side=tk.LEFT)
        self.var_bill_search = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.var_bill_search, width=40)
        entry.pack(side=tk.LEFT, padx=5)
        entry.bind("<KeyRelease>", lambda e: self.refresh_product_choices())

        self.product_combo = ttk.Combobox(top, textvariable=self.var_bill_product, state="readonly", width=50)
        self.product_combo.pack(fill=tk.X, padx=10)

        row2 = ttk.Frame(top)
        row2.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(row2, text="Quantity:").pack(side=tk.LEFT)
        ttk.Entry(row2, textvariable=self.var_bill_qty, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Button(row2, text="🛒 Add to Cart", command=self.on_add_to_cart).pack(side=tk.LEFT)

        # Image gallery
        gallery_frame = ttk.LabelFrame(self.billing_tab, text="Products (click to add)")
        gallery_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.gallery_canvas = tk.Canvas(gallery_frame, height=180)
        self.gallery_scroll_x = ttk.Scrollbar(gallery_frame, orient=tk.HORIZONTAL, command=self.gallery_canvas.xview)
        self.gallery_scroll_y = ttk.Scrollbar(gallery_frame, orient=tk.VERTICAL, command=self.gallery_canvas.yview)
        self.gallery_inner = ttk.Frame(self.gallery_canvas)
        self.gallery_inner.bind(
            "<Configure>",
            lambda e: self.gallery_canvas.configure(scrollregion=self.gallery_canvas.bbox("all")),
        )
        self.gallery_canvas.create_window((0, 0), window=self.gallery_inner, anchor="nw")
        self.gallery_canvas.configure(xscrollcommand=self.gallery_scroll_x.set, yscrollcommand=self.gallery_scroll_y.set)
        self.gallery_canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0,4))
        self.gallery_scroll_x.pack(fill=tk.X, side=tk.BOTTOM)
        self.gallery_scroll_y.pack(fill=tk.Y, side=tk.RIGHT)

        # Up/Down buttons
        nav = ttk.Frame(self.billing_tab)
        nav.pack(fill=tk.X, padx=10, pady=(0,6))
        ttk.Button(nav, text="▲ Up", command=lambda: self.gallery_canvas.yview_scroll(-1, "units")).pack(side=tk.LEFT)
        ttk.Button(nav, text="▼ Down", command=lambda: self.gallery_canvas.yview_scroll(1, "units")).pack(side=tk.LEFT, padx=6)

        # Cart
        self.cart_tree = ttk.Treeview(
            self.billing_tab,
            columns=("name", "price", "qty", "subtotal"),
            show="headings",
            height=12,
        )
        for col, text in [("name", "Name"), ("price", "Price"), ("qty", "Qty"), ("subtotal", "Subtotal")]:
            self.cart_tree.heading(col, text=text)
            self.cart_tree.column(col, width=180 if col == "name" else 140)
        self.cart_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.cart_tree.tag_configure("even", background="#f5f7fb")
        self.cart_tree.tag_configure("odd", background="#ffffff")

        bottom = ttk.Frame(self.billing_tab)
        bottom.pack(fill=tk.X, padx=10, pady=5)
        self.var_total = tk.StringVar(value="0.00")
        ttk.Label(bottom, text="Total:").pack(side=tk.LEFT)
        ttk.Label(bottom, textvariable=self.var_total, font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT)
        ttk.Button(bottom, text="Remove Selected", command=self.on_remove_cart_item, width=18).pack(side=tk.RIGHT)
        ttk.Button(bottom, text="Generate Invoice", command=self.on_checkout, width=18).pack(side=tk.RIGHT, padx=6)

        self.cart_items = []  # list of dicts
        self.refresh_product_choices()

    def refresh_product_choices(self):
        term = self.var_bill_search.get().strip() if hasattr(self, "var_bill_search") else ""
        rows = list_products(term)
        display = [f"{r['id']} - {r['name']} (₹{r['price']:.2f}, stock {r['stock']})" for r in rows]
        self.product_combo["values"] = display
        if display:
            self.product_combo.current(0)
        self.refresh_gallery(rows)

    def recalc_total(self):
        total = sum(i["price"] * i["qty"] for i in self.cart_items)
        self.var_total.set(f"{total:.2f}")

    def on_add_to_cart(self):
        sel = self.product_combo.get()
        if not sel:
            messagebox.showwarning("Select", "Please choose a product")
            return
        try:
            pid = int(sel.split(" - ")[0])
        except Exception:
            messagebox.showerror("Error", "Could not read selected product")
            return
        qty_str = self.var_bill_qty.get().strip()
        try:
            qty = int(qty_str)
            if qty <= 0:
                raise ValueError
        except Exception:
            messagebox.showerror("Invalid", "Quantity must be a positive whole number")
            return
        # fetch product
        prod = [r for r in list_products("") if r["id"] == pid]
        if not prod:
            messagebox.showerror("Error", "Product not found")
            return
        prod = prod[0]
        if qty > prod["stock"]:
            messagebox.showwarning("Stock", f"Only {prod['stock']} in stock")
            return
        # if already in cart, increase qty
        for item in self.cart_items:
            if item["product_id"] == pid:
                if item["qty"] + qty > prod["stock"]:
                    messagebox.showwarning("Stock", f"Only {prod['stock']} in stock")
                    return
                item["qty"] += qty
                break
        else:
            self.cart_items.append({
                "product_id": pid,
                "name": prod["name"],
                "price": float(prod["price"]),
                "qty": qty,
            })
        self.refresh_cart()

    def refresh_gallery(self, products):
        for w in self.gallery_inner.winfo_children():
            w.destroy()
        # Show a hint if Pillow isn't installed
        if not Image:
            ttk.Label(self.gallery_inner, text="Install Pillow to show images: pip install pillow").grid(row=0, column=0, padx=8, pady=8)
            return
        thumb_size = (96, 96)
        self._gallery_images = []
        col = 0
        for p in products:
            frame = ttk.Frame(self.gallery_inner, padding=6)
            frame.grid(row=0, column=col, padx=4, pady=4, sticky="n")
            img_label = ttk.Label(frame)
            img = None
            if Image and p["image_path"] and os.path.exists(p["image_path"]):
                try:
                    pil = Image.open(p["image_path"]).convert("RGB")
                    pil.thumbnail(thumb_size)
                    img = ImageTk.PhotoImage(pil)
                except Exception:
                    img = None
            if img is not None:
                img_label.configure(image=img)
                img_label.image = img
                self._gallery_images.append(img)
            else:
                img_label.configure(text="(No Image)", width=12)
            img_label.pack()
            ttk.Label(frame, text=p["name"], width=14).pack()
            ttk.Label(frame, text=f"₹{p['price']:.2f}").pack()
            ttk.Button(frame, text="Add", command=lambda pid=p["id"]: self.add_product_id_to_cart(pid)).pack(pady=(2,0))
            col += 1

    def add_product_id_to_cart(self, pid: int):
        self.var_bill_qty.set("1")
        prod = [r for r in list_products("") if r["id"] == pid]
        if not prod:
            return
        prod = prod[0]
        if 1 > prod["stock"]:
            messagebox.showwarning("Stock", f"Only {prod['stock']} in stock")
            return
        for item in self.cart_items:
            if item["product_id"] == pid:
                if item["qty"] + 1 > prod["stock"]:
                    messagebox.showwarning("Stock", f"Only {prod['stock']} in stock")
                    return
                item["qty"] += 1
                break
        else:
            self.cart_items.append({
                "product_id": pid,
                "name": prod["name"],
                "price": float(prod["price"]),
                "qty": 1,
            })
        self.refresh_cart()

    def refresh_cart(self):
        for i in self.cart_tree.get_children():
            self.cart_tree.delete(i)
        for idx, item in enumerate(self.cart_items):
            subtotal = item["price"] * item["qty"]
            tag = "even" if idx % 2 == 0 else "odd"
            self.cart_tree.insert("", tk.END, values=(item["name"], f"{item['price']:.2f}", item["qty"], f"{subtotal:.2f}"), tags=(tag,))
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
        self.refresh_product_choices()
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

    # Reports Tab
    def build_reports_tab(self):
        top = ttk.Frame(self.reports_tab)
        top.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(top, text="🔄 Refresh", command=self.refresh_reports).pack(side=tk.LEFT)

        self.bills_tree = ttk.Treeview(
            self.reports_tab,
            columns=("id", "created", "total"),
            show="headings",
            height=10,
        )
        for col, text in [("id", "Bill #"), ("created", "Date"), ("total", "Total")]:
            self.bills_tree.heading(col, text=text)
            self.bills_tree.column(col, width=180)
        self.bills_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.bills_tree.tag_configure("even", background="#f5f7fb")
        self.bills_tree.tag_configure("odd", background="#ffffff")
        self.bills_tree.bind("<<TreeviewSelect>>", self.on_select_bill)

        ttk.Label(self.reports_tab, text="🧾 Bill Items:").pack(anchor=tk.W, padx=10)
        self.bill_items_tree = ttk.Treeview(
            self.reports_tab,
            columns=("name", "qty", "price", "subtotal"),
            show="headings",
            height=10,
        )
        for col, text in [("name", "Name"), ("qty", "Qty"), ("price", "Price"), ("subtotal", "Subtotal")]:
            self.bill_items_tree.heading(col, text=text)
            self.bill_items_tree.column(col, width=160)
        self.bill_items_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.bill_items_tree.tag_configure("even", background="#f5f7fb")
        self.bill_items_tree.tag_configure("odd", background="#ffffff")

        self.refresh_reports()

    def refresh_reports(self):
        for i in self.bills_tree.get_children():
            self.bills_tree.delete(i)
        for idx, r in enumerate(get_recent_bills()):
            tag = "even" if idx % 2 == 0 else "odd"
            self.bills_tree.insert("", tk.END, values=(r["id"], r["created_at"], f"{r['total']:.2f}"), tags=(tag,))
        for i in self.bill_items_tree.get_children():
            self.bill_items_tree.delete(i)

    def on_select_bill(self, event=None):
        sel = self.bills_tree.selection()
        if not sel:
            return
        bill_id = int(self.bills_tree.item(sel[0])["values"][0])
        for i in self.bill_items_tree.get_children():
            self.bill_items_tree.delete(i)
        for idx, r in enumerate(get_bill_items(bill_id)):
            tag = "even" if idx % 2 == 0 else "odd"
            self.bill_items_tree.insert("", tk.END, values=(r["name"], r["qty"], f"{r['price']:.2f}", f"{r['subtotal']:.2f}"), tags=(tag,))

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
            self.refresh_product_choices()
            messagebox.showinfo("Restore", f"Added {count} products from file")
        except Exception as e:
            messagebox.showerror("Error", str(e))


def main():
    init_db()
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



