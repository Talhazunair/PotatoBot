import asyncio
import logging
import ssl

import asyncpg
import json
from config import DATABASE_URL

log = logging.getLogger("database")

POOL: asyncpg.Pool | None = None


async def init_db():
    global POOL

    # Create SSL context that doesn't verify certs (Railway uses self-signed)
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            log.info("Connecting to database (attempt %d/%d)...", attempt, max_retries)
            POOL = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=1,
                max_size=10,
                command_timeout=60,
                max_inactive_connection_lifetime=300,
                ssl=ssl_ctx,
                server_settings={
                    'application_name': 'PotatoBot',
                    'statement_timeout': '60000',
                    'idle_in_transaction_session_timeout': '60000'
                }
            )
            log.info("Database pool created successfully.")
            break
        except (ConnectionRefusedError, OSError, asyncpg.PostgresError) as exc:
            log.warning("Database connection attempt %d failed: %s", attempt, exc)
            if attempt == max_retries:
                raise
            await asyncio.sleep(2 ** attempt)  # exponential backoff: 2, 4, 8, 16s


    async with POOL.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                potato_id BIGINT UNIQUE NOT NULL,
                first_name TEXT DEFAULT '',
                role TEXT DEFAULT 'buyer',
                referred_by BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
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
                id SERIAL PRIMARY KEY,
                product_id INTEGER NOT NULL,
                file_id TEXT NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS cart_items (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER DEFAULT 1,
                selected_options_json TEXT DEFAULT '{}',
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            );
            CREATE TABLE IF NOT EXISTS addresses (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                label TEXT DEFAULT '',
                full_address TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
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
                id SERIAL PRIMARY KEY,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER DEFAULT 1,
                price REAL NOT NULL,
                selected_options_json TEXT DEFAULT '{}',
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );
            CREATE TABLE IF NOT EXISTS disputes (
                id SERIAL PRIMARY KEY,
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
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                status TEXT DEFAULT 'open',
                admin_reply TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS wallets (
                id SERIAL PRIMARY KEY,
                user_id INTEGER UNIQUE NOT NULL,
                balance REAL DEFAULT 0,
                deposit_address TEXT DEFAULT '',
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS fsm_states (
                user_id BIGINT PRIMARY KEY,
                state TEXT NOT NULL,
                data_json TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS seller_requests (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                potato_id BIGINT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)

    # Create categories table in a separate connection
    async with POOL.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                parent_id INTEGER REFERENCES categories(id) ON DELETE CASCADE
            );
        """)

    # Add category_id column to products in a separate connection
    async with POOL.acquire() as conn:
        try:
            await conn.execute("""
                ALTER TABLE products ADD COLUMN IF NOT EXISTS category_id INTEGER REFERENCES categories(id);
            """)
        except Exception as e:
            log.warning("Could not add category_id column (may already exist): %s", e)


def pool() -> asyncpg.Pool:
    assert POOL is not None, "Database pool not initialized"
    return POOL


# ── Helper to convert asyncpg Record to dict ───────────
def to_dict(record) -> dict | None:
    return dict(record) if record else None


# ── Users ──────────────────────────────────────────────
async def get_user(potato_id: int) -> dict | None:
    async with pool().acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE potato_id=$1", potato_id)
        return to_dict(row)


async def create_user(potato_id: int, first_name: str = "", referred_by: int | None = None) -> dict:
    async with pool().acquire() as conn:
        await conn.execute(
            "INSERT INTO users (potato_id, first_name, referred_by) VALUES ($1,$2,$3) ON CONFLICT (potato_id) DO NOTHING",
            potato_id, first_name, referred_by
        )
    user = await get_user(potato_id)
    return user


async def set_user_role(potato_id: int, role: str):
    async with pool().acquire() as conn:
        await conn.execute("UPDATE users SET role=$1 WHERE potato_id=$2", role, potato_id)


async def get_sellers() -> list[dict]:
    async with pool().acquire() as conn:
        rows = await conn.fetch("SELECT * FROM users WHERE role='seller'")
        return [dict(r) for r in rows]


# ── Seller Requests ────────────────────────────────────
async def create_seller_request(user_id: int, potato_id: int) -> int:
    async with pool().acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM seller_requests WHERE user_id=$1 AND status='pending'", user_id
        )
        if existing:
            return existing["id"]

        request_id = await conn.fetchval(
            "INSERT INTO seller_requests (user_id, potato_id) VALUES ($1,$2) RETURNING id",
            user_id, potato_id
        )
        return request_id


async def get_pending_seller_requests() -> list[dict]:
    async with pool().acquire() as conn:
        rows = await conn.fetch(
            """SELECT sr.*, u.first_name FROM seller_requests sr
               JOIN users u ON sr.user_id=u.id
               WHERE sr.status='pending' ORDER BY sr.id DESC"""
        )
        return [dict(r) for r in rows]


async def update_seller_request(request_id: int, status: str):
    async with pool().acquire() as conn:
        await conn.execute("UPDATE seller_requests SET status=$1 WHERE id=$2", status, request_id)


async def get_seller_request(request_id: int) -> dict | None:
    async with pool().acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM seller_requests WHERE id=$1", request_id)
        return to_dict(row)


async def has_pending_request(user_id: int) -> bool:
    async with pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM seller_requests WHERE user_id=$1 AND status='pending'", user_id
        )
        return row is not None


# ── Categories ─────────────────────────────────────────
async def create_category(name: str, parent_id: int | None = None) -> int:
    async with pool().acquire() as conn:
        cat_id = await conn.fetchval(
            "INSERT INTO categories (name, parent_id) VALUES ($1,$2) RETURNING id",
            name, parent_id
        )
        return cat_id


async def get_categories(parent_id: int | None = None) -> list[dict]:
    """Get top-level categories (parent_id IS NULL) or subcategories of a parent."""
    async with pool().acquire() as conn:
        if parent_id is None:
            rows = await conn.fetch("SELECT * FROM categories WHERE parent_id IS NULL ORDER BY name")
        else:
            rows = await conn.fetch("SELECT * FROM categories WHERE parent_id=$1 ORDER BY name", parent_id)
        return [dict(r) for r in rows]


async def get_category(cat_id: int) -> dict | None:
    async with pool().acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM categories WHERE id=$1", cat_id)
        return to_dict(row)


async def delete_category(cat_id: int):
    async with pool().acquire() as conn:
        await conn.execute("DELETE FROM categories WHERE id=$1", cat_id)


# ── Products ───────────────────────────────────────────
async def add_product(seller_id: int, name: str, description: str, price: float,
                      category_id: int | None = None) -> int:
    async with pool().acquire() as conn:
        product_id = await conn.fetchval(
            "INSERT INTO products (seller_id,name,description,price,category_id) VALUES ($1,$2,$3,$4,$5) RETURNING id",
            seller_id, name, description, price, category_id
        )
        return product_id


async def update_product(product_id: int, **fields):
    if not fields:
        return
    if "options" in fields:
        fields["options_json"] = json.dumps(fields.pop("options"))

    sets = []
    vals = []
    for i, (k, v) in enumerate(fields.items(), start=1):
        sets.append(f"{k}=${i}")
        vals.append(v)

    vals.append(product_id)
    query = f"UPDATE products SET {', '.join(sets)} WHERE id=${len(vals)}"

    async with pool().acquire() as conn:
        await conn.execute(query, *vals)


async def get_product(product_id: int) -> dict | None:
    async with pool().acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM products WHERE id=$1", product_id)
        return to_dict(row)


async def list_products(page: int = 0, limit: int = 5, seller_id: int | None = None,
                        active_only: bool = True) -> list[dict]:
    q = "SELECT * FROM products WHERE 1=1"
    params = []
    idx = 1
    if active_only:
        q += " AND active=1"
    if seller_id is not None:
        q += f" AND seller_id=${idx}"
        params.append(seller_id)
        idx += 1

    q += f" ORDER BY id DESC LIMIT ${idx} OFFSET ${idx+1}"
    params.extend([limit, page * limit])

    async with pool().acquire() as conn:
        rows = await conn.fetch(q, *params)
        return [dict(r) for r in rows]


async def count_products(seller_id: int | None = None, active_only: bool = True) -> int:
    q = "SELECT COUNT(*) FROM products WHERE 1=1"
    params = []
    idx = 1
    if active_only:
        q += " AND active=1"
    if seller_id is not None:
        q += f" AND seller_id=${idx}"
        params.append(seller_id)
        idx += 1

    async with pool().acquire() as conn:
        return await conn.fetchval(q, *params)


async def deactivate_product(product_id: int):
    async with pool().acquire() as conn:
        await conn.execute("UPDATE products SET active=0 WHERE id=$1", product_id)


# ── Product Images ─────────────────────────────────────
async def add_product_image(product_id: int, file_id: str):
    async with pool().acquire() as conn:
        await conn.execute("INSERT INTO product_images (product_id, file_id) VALUES ($1,$2)", product_id, file_id)


async def get_product_images(product_id: int) -> list[str]:
    async with pool().acquire() as conn:
        rows = await conn.fetch("SELECT file_id FROM product_images WHERE product_id=$1", product_id)
        return [r["file_id"] for r in rows]


# ── Cart ───────────────────────────────────────────────
async def add_to_cart(user_id: int, product_id: int, qty: int = 1, options: dict | None = None):
    async with pool().acquire() as conn:
        options_str = json.dumps(options or {})
        row = await conn.fetchrow(
            "SELECT id, quantity FROM cart_items WHERE user_id=$1 AND product_id=$2 AND selected_options_json=$3",
            user_id, product_id, options_str
        )
        if row:
            await conn.execute("UPDATE cart_items SET quantity=$1 WHERE id=$2", row["quantity"] + qty, row["id"])
        else:
            await conn.execute(
                "INSERT INTO cart_items (user_id, product_id, quantity, selected_options_json) VALUES ($1,$2,$3,$4)",
                user_id, product_id, qty, options_str
            )


async def get_cart(user_id: int) -> list[dict]:
    async with pool().acquire() as conn:
        rows = await conn.fetch(
            """SELECT ci.*, p.name, p.price FROM cart_items ci
               JOIN products p ON ci.product_id=p.id WHERE ci.user_id=$1""",
            user_id
        )
        return [dict(r) for r in rows]


async def remove_cart_item(item_id: int):
    async with pool().acquire() as conn:
        await conn.execute("DELETE FROM cart_items WHERE id=$1", item_id)


async def clear_cart(user_id: int):
    async with pool().acquire() as conn:
        await conn.execute("DELETE FROM cart_items WHERE user_id=$1", user_id)


# ── Addresses ──────────────────────────────────────────
async def add_address(user_id: int, label: str, full_address: str) -> int:
    async with pool().acquire() as conn:
        address_id = await conn.fetchval(
            "INSERT INTO addresses (user_id, label, full_address) VALUES ($1,$2,$3) RETURNING id",
            user_id, label, full_address
        )
        return address_id


async def get_addresses(user_id: int) -> list[dict]:
    async with pool().acquire() as conn:
        rows = await conn.fetch("SELECT * FROM addresses WHERE user_id=$1", user_id)
        return [dict(r) for r in rows]


async def get_address(address_id: int) -> dict | None:
    async with pool().acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM addresses WHERE id=$1", address_id)
        return to_dict(row)


# ── Orders ─────────────────────────────────────────────
async def create_order(user_id: int, address_id: int, total: float,
                       payment_address: str = "", invoice_id: str = "") -> int:
    async with pool().acquire() as conn:
        order_id = await conn.fetchval(
            "INSERT INTO orders (user_id, address_id, total, payment_address, invoice_id) VALUES ($1,$2,$3,$4,$5) RETURNING id",
            user_id, address_id, total, payment_address, invoice_id
        )
        return order_id


async def add_order_item(order_id: int, product_id: int, quantity: int,
                         price: float, options: dict | None = None):
    async with pool().acquire() as conn:
        await conn.execute(
            "INSERT INTO order_items (order_id, product_id, quantity, price, selected_options_json) VALUES ($1,$2,$3,$4,$5)",
            order_id, product_id, quantity, price, json.dumps(options or {})
        )


async def get_order(order_id: int) -> dict | None:
    async with pool().acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM orders WHERE id=$1", order_id)
        return to_dict(row)


async def get_order_items(order_id: int) -> list[dict]:
    async with pool().acquire() as conn:
        rows = await conn.fetch(
            """SELECT oi.*, p.name as product_name FROM order_items oi
               JOIN products p ON oi.product_id=p.id WHERE oi.order_id=$1""",
            order_id
        )
        return [dict(r) for r in rows]


async def get_user_orders(user_id: int, status: str | None = None) -> list[dict]:
    q = "SELECT * FROM orders WHERE user_id=$1"
    params = [user_id]
    if status:
        q += " AND status=$2"
        params.append(status)
    q += " ORDER BY id DESC"

    async with pool().acquire() as conn:
        rows = await conn.fetch(q, *params)
        return [dict(r) for r in rows]


async def get_seller_orders(seller_id: int, status: str | None = None) -> list[dict]:
    q = """SELECT DISTINCT o.* FROM orders o
           JOIN order_items oi ON o.id=oi.order_id
           JOIN products p ON oi.product_id=p.id
           WHERE p.seller_id=$1"""
    params = [seller_id]
    if status:
        q += " AND o.status=$2"
        params.append(status)
    q += " ORDER BY o.id DESC"

    async with pool().acquire() as conn:
        rows = await conn.fetch(q, *params)
        return [dict(r) for r in rows]


async def update_order_status(order_id: int, status: str):
    async with pool().acquire() as conn:
        await conn.execute("UPDATE orders SET status=$1 WHERE id=$2", status, order_id)


async def count_seller_orders(seller_id: int, status: str | None = None) -> int:
    q = """SELECT COUNT(DISTINCT o.id) FROM orders o
           JOIN order_items oi ON o.id=oi.order_id
           JOIN products p ON oi.product_id=p.id
           WHERE p.seller_id=$1"""
    params = [seller_id]
    if status:
        q += " AND o.status=$2"
        params.append(status)

    async with pool().acquire() as conn:
        return await conn.fetchval(q, *params)


# ── Disputes ───────────────────────────────────────────
async def create_dispute(order_id: int, product_id: int, user_id: int,
                         reason: str, message: str = "") -> int:
    async with pool().acquire() as conn:
        dispute_id = await conn.fetchval(
            "INSERT INTO disputes (order_id, product_id, user_id, reason, message) VALUES ($1,$2,$3,$4,$5) RETURNING id",
            order_id, product_id, user_id, reason, message
        )
        return dispute_id


async def get_user_disputes(user_id: int) -> list[dict]:
    async with pool().acquire() as conn:
        rows = await conn.fetch("SELECT * FROM disputes WHERE user_id=$1 ORDER BY id DESC", user_id)
        return [dict(r) for r in rows]


async def get_dispute(dispute_id: int) -> dict | None:
    async with pool().acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM disputes WHERE id=$1", dispute_id)
        return to_dict(row)


async def get_all_disputes(status: str | None = None) -> list[dict]:
    q = "SELECT * FROM disputes"
    params = []
    if status:
        q += " WHERE status=$1"
        params.append(status)
    q += " ORDER BY id DESC"

    async with pool().acquire() as conn:
        rows = await conn.fetch(q, *params)
        return [dict(r) for r in rows]


async def update_dispute_status(dispute_id: int, status: str):
    async with pool().acquire() as conn:
        await conn.execute("UPDATE disputes SET status=$1 WHERE id=$2", status, dispute_id)


# ── Support ────────────────────────────────────────────
async def create_ticket(user_id: int, message: str) -> int:
    async with pool().acquire() as conn:
        ticket_id = await conn.fetchval(
            "INSERT INTO support_tickets (user_id, message) VALUES ($1,$2) RETURNING id",
            user_id, message
        )
        return ticket_id


async def get_open_tickets() -> list[dict]:
    async with pool().acquire() as conn:
        rows = await conn.fetch("SELECT * FROM support_tickets WHERE status='open' ORDER BY id DESC")
        return [dict(r) for r in rows]


async def close_ticket(ticket_id: int, reply: str = ""):
    async with pool().acquire() as conn:
        await conn.execute(
            "UPDATE support_tickets SET status='closed', admin_reply=$1 WHERE id=$2",
            reply, ticket_id
        )


async def get_ticket(ticket_id: int) -> dict | None:
    async with pool().acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM support_tickets WHERE id=$1", ticket_id)
        return to_dict(row)


# ── Wallets ────────────────────────────────────────────
async def get_wallet(user_id: int) -> dict:
    async with pool().acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM wallets WHERE user_id=$1", user_id)
        if row:
            return dict(row)

        await conn.execute("INSERT INTO wallets (user_id) VALUES ($1)", user_id)
        return {"user_id": user_id, "balance": 0.0, "deposit_address": ""}


async def update_wallet_balance(user_id: int, amount: float):
    w = await get_wallet(user_id)
    new_bal = w["balance"] + amount
    async with pool().acquire() as conn:
        await conn.execute("UPDATE wallets SET balance=$1 WHERE user_id=$2", new_bal, user_id)


async def set_wallet_deposit_address(user_id: int, address: str):
    await get_wallet(user_id)
    async with pool().acquire() as conn:
        await conn.execute("UPDATE wallets SET deposit_address=$1 WHERE user_id=$2", address, user_id)


# ── FSM ────────────────────────────────────────────────
async def get_fsm(user_id: int) -> tuple[str, dict]:
    async with pool().acquire() as conn:
        row = await conn.fetchrow("SELECT state, data_json FROM fsm_states WHERE user_id=$1", user_id)
        if row:
            return row["state"], json.loads(row["data_json"])
        return "", {}


async def set_fsm(user_id: int, state: str, data: dict | None = None):
    async with pool().acquire() as conn:
        await conn.execute(
            "INSERT INTO fsm_states (user_id, state, data_json) VALUES ($1,$2,$3) ON CONFLICT (user_id) DO UPDATE SET state=EXCLUDED.state, data_json=EXCLUDED.data_json",
            user_id, state, json.dumps(data or {})
        )


async def clear_fsm(user_id: int):
    async with pool().acquire() as conn:
        await conn.execute("DELETE FROM fsm_states WHERE user_id=$1", user_id)
