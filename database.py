import aiosqlite
import json
from config import DATABASE_PATH

DB: aiosqlite.Connection | None = None


async def init_db():
    global DB
    DB = await aiosqlite.connect(DATABASE_PATH)
    DB.row_factory = aiosqlite.Row
    await DB.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            potato_id INTEGER UNIQUE NOT NULL,
            first_name TEXT DEFAULT '',
            role TEXT DEFAULT 'buyer',
            referred_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            price REAL NOT NULL,
            category TEXT DEFAULT '',
            options_json TEXT DEFAULT '[]',
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (seller_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS product_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            file_id TEXT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS cart_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER DEFAULT 1,
            selected_options_json TEXT DEFAULT '{}',
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );
        CREATE TABLE IF NOT EXISTS addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            label TEXT DEFAULT '',
            full_address TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            address_id INTEGER,
            status TEXT DEFAULT 'pending_payment',
            total REAL DEFAULT 0,
            payment_address TEXT DEFAULT '',
            invoice_id TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (address_id) REFERENCES addresses(id)
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER DEFAULT 1,
            price REAL NOT NULL,
            selected_options_json TEXT DEFAULT '{}',
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products(id)
        );
        CREATE TABLE IF NOT EXISTS disputes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            message TEXT DEFAULT '',
            status TEXT DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (product_id) REFERENCES products(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            admin_reply TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            balance REAL DEFAULT 0,
            deposit_address TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS fsm_states (
            user_id INTEGER PRIMARY KEY,
            state TEXT NOT NULL,
            data_json TEXT DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS seller_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            potato_id INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    await DB.commit()


def db() -> aiosqlite.Connection:
    assert DB is not None, "Database not initialized"
    return DB


# ── Users ──────────────────────────────────────────────
async def get_user(potato_id: int) -> dict | None:
    cur = await db().execute("SELECT * FROM users WHERE potato_id=?", (potato_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def create_user(potato_id: int, first_name: str = "", referred_by: int | None = None) -> dict:
    await db().execute(
        "INSERT OR IGNORE INTO users (potato_id, first_name, referred_by) VALUES (?,?,?)",
        (potato_id, first_name, referred_by),
    )
    await db().commit()
    return await get_user(potato_id)  # type: ignore


async def set_user_role(potato_id: int, role: str):
    await db().execute("UPDATE users SET role=? WHERE potato_id=?", (role, potato_id))
    await db().commit()


async def get_sellers() -> list[dict]:
    cur = await db().execute("SELECT * FROM users WHERE role='seller'")
    return [dict(r) for r in await cur.fetchall()]


# ── Seller Requests ────────────────────────────────────
async def create_seller_request(user_id: int, potato_id: int) -> int:
    # Check if already pending
    cur = await db().execute(
        "SELECT id FROM seller_requests WHERE user_id=? AND status='pending'", (user_id,)
    )
    existing = await cur.fetchone()
    if existing:
        return existing[0]
    cur = await db().execute(
        "INSERT INTO seller_requests (user_id, potato_id) VALUES (?,?)",
        (user_id, potato_id),
    )
    await db().commit()
    return cur.lastrowid  # type: ignore


async def get_pending_seller_requests() -> list[dict]:
    cur = await db().execute(
        """SELECT sr.*, u.first_name FROM seller_requests sr
           JOIN users u ON sr.user_id=u.id
           WHERE sr.status='pending' ORDER BY sr.id DESC"""
    )
    return [dict(r) for r in await cur.fetchall()]


async def update_seller_request(request_id: int, status: str):
    await db().execute("UPDATE seller_requests SET status=? WHERE id=?", (status, request_id))
    await db().commit()


async def get_seller_request(request_id: int) -> dict | None:
    cur = await db().execute("SELECT * FROM seller_requests WHERE id=?", (request_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def has_pending_request(user_id: int) -> bool:
    cur = await db().execute(
        "SELECT 1 FROM seller_requests WHERE user_id=? AND status='pending'", (user_id,)
    )
    return (await cur.fetchone()) is not None


# ── Products ───────────────────────────────────────────
async def add_product(seller_id: int, name: str, description: str, price: float,
                      category: str = "", options: list | None = None) -> int:
    cur = await db().execute(
        "INSERT INTO products (seller_id,name,description,price,category,options_json) VALUES (?,?,?,?,?,?)",
        (seller_id, name, description, price, category, json.dumps(options or [])),
    )
    await db().commit()
    return cur.lastrowid  # type: ignore


async def update_product(product_id: int, **fields):
    if "options" in fields:
        fields["options_json"] = json.dumps(fields.pop("options"))
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [product_id]
    await db().execute(f"UPDATE products SET {sets} WHERE id=?", vals)
    await db().commit()


async def get_product(product_id: int) -> dict | None:
    cur = await db().execute("SELECT * FROM products WHERE id=?", (product_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def list_products(page: int = 0, limit: int = 5, seller_id: int | None = None,
                        active_only: bool = True) -> list[dict]:
    q = "SELECT * FROM products WHERE 1=1"
    params: list = []
    if active_only:
        q += " AND active=1"
    if seller_id is not None:
        q += " AND seller_id=?"
        params.append(seller_id)
    q += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, page * limit])
    cur = await db().execute(q, params)
    return [dict(r) for r in await cur.fetchall()]


async def count_products(seller_id: int | None = None, active_only: bool = True) -> int:
    q = "SELECT COUNT(*) FROM products WHERE 1=1"
    params: list = []
    if active_only:
        q += " AND active=1"
    if seller_id is not None:
        q += " AND seller_id=?"
        params.append(seller_id)
    cur = await db().execute(q, params)
    return (await cur.fetchone())[0]


async def deactivate_product(product_id: int):
    await db().execute("UPDATE products SET active=0 WHERE id=?", (product_id,))
    await db().commit()


# ── Product Images ─────────────────────────────────────
async def add_product_image(product_id: int, file_id: str):
    await db().execute("INSERT INTO product_images (product_id, file_id) VALUES (?,?)", (product_id, file_id))
    await db().commit()


async def get_product_images(product_id: int) -> list[str]:
    cur = await db().execute("SELECT file_id FROM product_images WHERE product_id=?", (product_id,))
    return [r[0] for r in await cur.fetchall()]


# ── Cart ───────────────────────────────────────────────
async def add_to_cart(user_id: int, product_id: int, qty: int = 1, options: dict | None = None):
    cur = await db().execute(
        "SELECT id, quantity FROM cart_items WHERE user_id=? AND product_id=? AND selected_options_json=?",
        (user_id, product_id, json.dumps(options or {})),
    )
    row = await cur.fetchone()
    if row:
        await db().execute("UPDATE cart_items SET quantity=? WHERE id=?", (row[1] + qty, row[0]))
    else:
        await db().execute(
            "INSERT INTO cart_items (user_id, product_id, quantity, selected_options_json) VALUES (?,?,?,?)",
            (user_id, product_id, qty, json.dumps(options or {})),
        )
    await db().commit()


async def get_cart(user_id: int) -> list[dict]:
    cur = await db().execute(
        """SELECT ci.*, p.name, p.price FROM cart_items ci
           JOIN products p ON ci.product_id=p.id WHERE ci.user_id=?""",
        (user_id,),
    )
    return [dict(r) for r in await cur.fetchall()]


async def remove_cart_item(item_id: int):
    await db().execute("DELETE FROM cart_items WHERE id=?", (item_id,))
    await db().commit()


async def clear_cart(user_id: int):
    await db().execute("DELETE FROM cart_items WHERE user_id=?", (user_id,))
    await db().commit()


# ── Addresses ──────────────────────────────────────────
async def add_address(user_id: int, label: str, full_address: str) -> int:
    cur = await db().execute(
        "INSERT INTO addresses (user_id, label, full_address) VALUES (?,?,?)",
        (user_id, label, full_address),
    )
    await db().commit()
    return cur.lastrowid  # type: ignore


async def get_addresses(user_id: int) -> list[dict]:
    cur = await db().execute("SELECT * FROM addresses WHERE user_id=?", (user_id,))
    return [dict(r) for r in await cur.fetchall()]


async def get_address(address_id: int) -> dict | None:
    cur = await db().execute("SELECT * FROM addresses WHERE id=?", (address_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


# ── Orders ─────────────────────────────────────────────
async def create_order(user_id: int, address_id: int, total: float,
                       payment_address: str = "", invoice_id: str = "") -> int:
    cur = await db().execute(
        "INSERT INTO orders (user_id, address_id, total, payment_address, invoice_id) VALUES (?,?,?,?,?)",
        (user_id, address_id, total, payment_address, invoice_id),
    )
    await db().commit()
    return cur.lastrowid  # type: ignore


async def add_order_item(order_id: int, product_id: int, quantity: int,
                         price: float, options: dict | None = None):
    await db().execute(
        "INSERT INTO order_items (order_id, product_id, quantity, price, selected_options_json) VALUES (?,?,?,?,?)",
        (order_id, product_id, quantity, price, json.dumps(options or {})),
    )
    await db().commit()


async def get_order(order_id: int) -> dict | None:
    cur = await db().execute("SELECT * FROM orders WHERE id=?", (order_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def get_order_items(order_id: int) -> list[dict]:
    cur = await db().execute(
        """SELECT oi.*, p.name as product_name FROM order_items oi
           JOIN products p ON oi.product_id=p.id WHERE oi.order_id=?""",
        (order_id,),
    )
    return [dict(r) for r in await cur.fetchall()]


async def get_user_orders(user_id: int, status: str | None = None) -> list[dict]:
    q = "SELECT * FROM orders WHERE user_id=?"
    params: list = [user_id]
    if status:
        q += " AND status=?"
        params.append(status)
    q += " ORDER BY id DESC"
    cur = await db().execute(q, params)
    return [dict(r) for r in await cur.fetchall()]


async def get_seller_orders(seller_id: int, status: str | None = None) -> list[dict]:
    q = """SELECT DISTINCT o.* FROM orders o
           JOIN order_items oi ON o.id=oi.order_id
           JOIN products p ON oi.product_id=p.id
           WHERE p.seller_id=?"""
    params: list = [seller_id]
    if status:
        q += " AND o.status=?"
        params.append(status)
    q += " ORDER BY o.id DESC"
    cur = await db().execute(q, params)
    return [dict(r) for r in await cur.fetchall()]


async def update_order_status(order_id: int, status: str):
    await db().execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    await db().commit()


async def count_seller_orders(seller_id: int, status: str | None = None) -> int:
    q = """SELECT COUNT(DISTINCT o.id) FROM orders o
           JOIN order_items oi ON o.id=oi.order_id
           JOIN products p ON oi.product_id=p.id
           WHERE p.seller_id=?"""
    params: list = [seller_id]
    if status:
        q += " AND o.status=?"
        params.append(status)
    cur = await db().execute(q, params)
    return (await cur.fetchone())[0]


# ── Disputes ───────────────────────────────────────────
async def create_dispute(order_id: int, product_id: int, user_id: int,
                         reason: str, message: str = "") -> int:
    cur = await db().execute(
        "INSERT INTO disputes (order_id, product_id, user_id, reason, message) VALUES (?,?,?,?,?)",
        (order_id, product_id, user_id, reason, message),
    )
    await db().commit()
    return cur.lastrowid  # type: ignore


async def get_user_disputes(user_id: int) -> list[dict]:
    cur = await db().execute("SELECT * FROM disputes WHERE user_id=? ORDER BY id DESC", (user_id,))
    return [dict(r) for r in await cur.fetchall()]


async def get_dispute(dispute_id: int) -> dict | None:
    cur = await db().execute("SELECT * FROM disputes WHERE id=?", (dispute_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def get_all_disputes(status: str | None = None) -> list[dict]:
    q = "SELECT * FROM disputes"
    params: list = []
    if status:
        q += " WHERE status=?"
        params.append(status)
    q += " ORDER BY id DESC"
    cur = await db().execute(q, params)
    return [dict(r) for r in await cur.fetchall()]


async def update_dispute_status(dispute_id: int, status: str):
    await db().execute("UPDATE disputes SET status=? WHERE id=?", (status, dispute_id))
    await db().commit()


# ── Support ────────────────────────────────────────────
async def create_ticket(user_id: int, message: str) -> int:
    cur = await db().execute(
        "INSERT INTO support_tickets (user_id, message) VALUES (?,?)",
        (user_id, message),
    )
    await db().commit()
    return cur.lastrowid  # type: ignore


async def get_open_tickets() -> list[dict]:
    cur = await db().execute("SELECT * FROM support_tickets WHERE status='open' ORDER BY id DESC")
    return [dict(r) for r in await cur.fetchall()]


async def close_ticket(ticket_id: int, reply: str = ""):
    await db().execute(
        "UPDATE support_tickets SET status='closed', admin_reply=? WHERE id=?",
        (reply, ticket_id),
    )
    await db().commit()


async def get_ticket(ticket_id: int) -> dict | None:
    cur = await db().execute("SELECT * FROM support_tickets WHERE id=?", (ticket_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


# ── Wallets ────────────────────────────────────────────
async def get_wallet(user_id: int) -> dict:
    cur = await db().execute("SELECT * FROM wallets WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    if row:
        return dict(row)
    await db().execute("INSERT INTO wallets (user_id) VALUES (?)", (user_id,))
    await db().commit()
    return {"user_id": user_id, "balance": 0.0, "deposit_address": ""}


async def update_wallet_balance(user_id: int, amount: float):
    w = await get_wallet(user_id)
    new_bal = w["balance"] + amount
    await db().execute("UPDATE wallets SET balance=? WHERE user_id=?", (new_bal, user_id))
    await db().commit()


async def set_wallet_deposit_address(user_id: int, address: str):
    await get_wallet(user_id)
    await db().execute("UPDATE wallets SET deposit_address=? WHERE user_id=?", (address, user_id))
    await db().commit()


# ── FSM ────────────────────────────────────────────────
async def get_fsm(user_id: int) -> tuple[str, dict]:
    cur = await db().execute("SELECT state, data_json FROM fsm_states WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    if row:
        return row[0], json.loads(row[1])
    return "", {}


async def set_fsm(user_id: int, state: str, data: dict | None = None):
    await db().execute(
        "INSERT OR REPLACE INTO fsm_states (user_id, state, data_json) VALUES (?,?,?)",
        (user_id, state, json.dumps(data or {})),
    )
    await db().commit()


async def clear_fsm(user_id: int):
    await db().execute("DELETE FROM fsm_states WHERE user_id=?", (user_id,))
    await db().commit()
