"""Reusable inline keyboard builders for Potato Bot."""
import json


def _inline_kb(rows: list[list[dict]]) -> dict:
    """Build a Potato inline keyboard reply_markup."""
    return {
        "type": 4,
        "inline_keyboard": [{"buttons": row} for row in rows],
    }


def _btn(text: str, data: str) -> dict:
    return {"text": text, "callback_data": data}


# ── Menus ──────────────────────────────────────────────
def main_menu_kb() -> dict:
    return _inline_kb([
        [_btn("🛍 Browse Products", "prod:list:0")],
        [_btn("🛒 My Cart", "cart:view"), _btn("📦 My Orders", "order:list")],
        [_btn("📍 My Addresses", "addr:list"), _btn("💰 My Wallet", "wal:view")],
        [_btn("⚠️ My Disputes", "disp:list"), _btn("📞 Support", "supp:start")],
        [_btn("🏪 Become a Seller", "sell:apply")],
    ])


def main_menu_with_seller_kb() -> dict:
    return _inline_kb([
        [_btn("🛍 Browse Products", "prod:list:0")],
        [_btn("🛒 My Cart", "cart:view"), _btn("📦 My Orders", "order:list")],
        [_btn("📍 My Addresses", "addr:list"), _btn("💰 My Wallet", "wal:view")],
        [_btn("⚠️ My Disputes", "disp:list"), _btn("📞 Support", "supp:start")],
        [_btn("🏪 Seller Dashboard", "sell:menu")],
    ])


def main_menu_with_admin_kb() -> dict:
    return _inline_kb([
        [_btn("🛍 Browse Products", "prod:list:0")],
        [_btn("🛒 My Cart", "cart:view"), _btn("📦 My Orders", "order:list")],
        [_btn("📍 My Addresses", "addr:list"), _btn("💰 My Wallet", "wal:view")],
        [_btn("⚠️ My Disputes", "disp:list"), _btn("📞 Support", "supp:start")],
        [_btn("🏪 Seller Dashboard", "sell:menu")],
        [_btn("🔧 Admin Panel", "adm:menu")],
    ])


def back_kb(callback: str = "menu:main") -> dict:
    return _inline_kb([[_btn("◀️ Back", callback)]])


# ── Products ───────────────────────────────────────────
def products_kb(products: list[dict], page: int, total: int, per_page: int = 5) -> dict:
    rows: list[list[dict]] = []
    for p in products:
        rows.append([_btn(f"{p['name']} — ${p['price']:.2f}", f"prod:view:{p['id']}")])
    nav: list[dict] = []
    if page > 0:
        nav.append(_btn("⬅️ Prev", f"prod:list:{page - 1}"))
    if (page + 1) * per_page < total:
        nav.append(_btn("Next ➡️", f"prod:list:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([_btn("◀️ Main Menu", "menu:main")])
    return _inline_kb(rows)


def product_detail_kb(product: dict, options: list | None = None) -> dict:
    rows: list[list[dict]] = []
    if options:
        for opt in options:
            opt_name = opt.get("name", "Option")
            for val in opt.get("values", []):
                rows.append([_btn(f"{opt_name}: {val}", f"prod:opt:{product['id']}:{opt_name}:{val}")])
    rows.append([_btn("🛒 Add to Cart", f"cart:add:{product['id']}")])
    rows.append([_btn("◀️ Back to Products", "prod:list:0")])
    return _inline_kb(rows)


# ── Cart ───────────────────────────────────────────────
def cart_kb(items: list[dict]) -> dict:
    rows: list[list[dict]] = []
    for item in items:
        rows.append([
            _btn(f"❌ {item['name']} x{item['quantity']}", f"cart:remove:{item['id']}"),
        ])
    if items:
        rows.append([_btn("✅ Checkout", "cart:checkout")])
    rows.append([_btn("◀️ Main Menu", "menu:main")])
    return _inline_kb(rows)


def confirm_order_kb() -> dict:
    return _inline_kb([
        [_btn("✅ Confirm Order", "cart:confirm")],
        [_btn("❌ Cancel", "menu:main")],
    ])


def address_select_kb(addresses: list[dict]) -> dict:
    rows = [[_btn(f"📍 {a['label']}: {a['full_address'][:30]}", f"addr:select:{a['id']}")] for a in addresses]
    rows.append([_btn("➕ Add New Address", "addr:add")])
    rows.append([_btn("◀️ Back", "cart:view")])
    return _inline_kb(rows)


# ── Orders ─────────────────────────────────────────────
def orders_kb(orders: list[dict]) -> dict:
    rows = [[_btn(f"Order #{o['id']} — {o['status']}", f"order:view:{o['id']}")] for o in orders]
    rows.append([_btn("◀️ Main Menu", "menu:main")])
    return _inline_kb(rows)


def order_detail_kb(order: dict) -> dict:
    rows: list[list[dict]] = []
    if order["status"] in ("pending_payment", "preparing"):
        rows.append([_btn("❌ Cancel Order", f"order:cancel:{order['id']}")])
    rows.append([_btn("◀️ My Orders", "order:list")])
    return _inline_kb(rows)


def seller_orders_kb() -> dict:
    return _inline_kb([
        [_btn("📋 My Sales History", "order:sales:all")],
        [_btn("📦 In Preparation", "order:sales:preparing")],
        [_btn("❌ Order Cancelled", "order:sales:cancelled")],
        [_btn("◀️ Back", "sell:menu")],
    ])


# ── Addresses ──────────────────────────────────────────
def addresses_kb(addresses: list[dict]) -> dict:
    rows = [[_btn(f"📍 {a['label']}: {a['full_address'][:30]}", f"addr:view:{a['id']}")] for a in addresses]
    rows.append([_btn("➕ Add Address", "addr:add")])
    rows.append([_btn("◀️ Main Menu", "menu:main")])
    return _inline_kb(rows)


# ── Wallet ─────────────────────────────────────────────
def wallet_kb() -> dict:
    return _inline_kb([
        [_btn("📥 Deposit", "wal:deposit"), _btn("📤 Withdraw", "wal:withdraw")],
        [_btn("◀️ Main Menu", "menu:main")],
    ])


# ── Seller ─────────────────────────────────────────────
def seller_menu_kb() -> dict:
    return _inline_kb([
        [_btn("➕ Add Product", "sell:add")],
        [_btn("📋 My Products", "sell:list:0")],
        [_btn("📦 My Orders", "sell:orders")],
        [_btn("◀️ Main Menu", "menu:main")],
    ])


def seller_products_kb(products: list[dict], page: int, total: int) -> dict:
    rows: list[list[dict]] = []
    for p in products:
        status = "✅" if p["active"] else "❌"
        rows.append([_btn(f"{status} {p['name']} — ${p['price']:.2f}", f"sell:edit:{p['id']}")])
    nav: list[dict] = []
    if page > 0:
        nav.append(_btn("⬅️ Prev", f"sell:list:{page - 1}"))
    if (page + 1) * 5 < total:
        nav.append(_btn("Next ➡️", f"sell:list:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([_btn("◀️ Seller Menu", "sell:menu")])
    return _inline_kb(rows)


def edit_product_kb(product: dict) -> dict:
    pid = product["id"]
    return _inline_kb([
        [_btn("✏️ Edit Name", f"sell:field:{pid}:name"), _btn("✏️ Edit Price", f"sell:field:{pid}:price")],
        [_btn("✏️ Edit Description", f"sell:field:{pid}:description")],
        [_btn("✏️ Edit Options", f"sell:field:{pid}:options")],
        [_btn("📷 Upload Images", f"sell:img:{pid}")],
        [_btn("🗑 Deactivate", f"sell:deactivate:{pid}")],
        [_btn("◀️ Back", "sell:list:0")],
    ])


# ── Admin ──────────────────────────────────────────────
def admin_menu_kb() -> dict:
    return _inline_kb([
        [_btn("➕ Add Seller", "adm:add_seller")],
        [_btn("📋 Manage Sellers", "adm:sellers")],
        [_btn("📝 Seller Requests", "adm:seller_requests")],
        [_btn("🗑 Remove Product", "adm:products:0")],
        [_btn("📨 Support Tickets", "adm:support")],
        [_btn("⚠️ Disputes", "adm:disputes")],
        [_btn("◀️ Main Menu", "menu:main")],
    ])


def admin_seller_requests_kb(requests: list[dict]) -> dict:
    rows = [[_btn(
        f"👤 {r['first_name']} (ID:{r['potato_id']})",
        f"adm:review_req:{r['id']}"
    )] for r in requests]
    rows.append([_btn("◀️ Admin Menu", "adm:menu")])
    return _inline_kb(rows)


def admin_review_request_kb(request_id: int) -> dict:
    return _inline_kb([
        [_btn("✅ Approve", f"adm:approve_req:{request_id}")],
        [_btn("❌ Reject", f"adm:reject_req:{request_id}")],
        [_btn("◀️ Back", "adm:seller_requests")],
    ])


def admin_sellers_kb(sellers: list[dict]) -> dict:
    rows = [[_btn(f"👤 {s['first_name']} (ID:{s['potato_id']})", f"adm:rm_seller:{s['potato_id']}")] for s in sellers]
    rows.append([_btn("◀️ Admin Menu", "adm:menu")])
    return _inline_kb(rows)


def admin_products_kb(products: list[dict], page: int, total: int) -> dict:
    rows = [[_btn(f"🗑 {p['name']}", f"adm:rm_prod:{p['id']}")] for p in products]
    nav: list[dict] = []
    if page > 0:
        nav.append(_btn("⬅️ Prev", f"adm:products:{page - 1}"))
    if (page + 1) * 5 < total:
        nav.append(_btn("Next ➡️", f"adm:products:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([_btn("◀️ Admin Menu", "adm:menu")])
    return _inline_kb(rows)


def admin_tickets_kb(tickets: list[dict]) -> dict:
    rows = [[_btn(f"🎫 #{t['id']} from user {t['user_id']}", f"adm:ticket:{t['id']}")] for t in tickets]
    rows.append([_btn("◀️ Admin Menu", "adm:menu")])
    return _inline_kb(rows)


def admin_ticket_detail_kb(ticket_id: int) -> dict:
    return _inline_kb([
        [_btn("✅ Mark Completed", f"adm:close_ticket:{ticket_id}")],
        [_btn("◀️ Back", "adm:support")],
    ])


def admin_disputes_kb(disputes: list[dict]) -> dict:
    rows = [[_btn(f"⚠️ #{d['id']} — {d['reason'][:20]}", f"adm:dispute_view:{d['id']}")] for d in disputes]
    rows.append([_btn("◀️ Admin Menu", "adm:menu")])
    return _inline_kb(rows)


def admin_dispute_detail_kb(dispute_id: int) -> dict:
    return _inline_kb([
        [_btn("✅ Resolve", f"adm:resolve_dispute:{dispute_id}")],
        [_btn("◀️ Back", "adm:disputes")],
    ])


# ── Disputes (user) ───────────────────────────────────
def dispute_orders_kb(orders: list[dict]) -> dict:
    rows = [[_btn(f"Order #{o['id']}", f"disp:order:{o['id']}")] for o in orders]
    rows.append([_btn("◀️ Main Menu", "menu:main")])
    return _inline_kb(rows)


def dispute_products_kb(items: list[dict], order_id: int) -> dict:
    rows = [[_btn(f"{it['product_name']} — ${it['price']:.2f} x{it['quantity']}",
                  f"disp:product:{order_id}:{it['product_id']}")] for it in items]
    rows.append([_btn("◀️ Back", "disp:open")])
    return _inline_kb(rows)


def dispute_reasons_kb(order_id: int, product_id: int) -> dict:
    prefix = f"disp:reason:{order_id}:{product_id}"
    return _inline_kb([
        [_btn("📦 Product not received", f"{prefix}:not_received")],
        [_btn("🔧 Defective product", f"{prefix}:defective")],
        [_btn("❓ Product does not match description", f"{prefix}:mismatch")],
        [_btn("📝 Other (describe)", f"{prefix}:other")],
    ])


def user_disputes_kb(disputes: list[dict]) -> dict:
    rows = [[_btn(f"⚠️ #{d['id']} — {d['reason'][:20]} ({d['status']})",
                  f"disp:view:{d['id']}")] for d in disputes]
    rows.append([_btn("➕ Open Dispute", "disp:open")])
    rows.append([_btn("◀️ Main Menu", "menu:main")])
    return _inline_kb(rows)
