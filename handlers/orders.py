"""Order management — buyer & seller views."""
import json
import potato_api as api
import database as db
import keyboards as kb


async def handle_callback(chat_id: int, user_id: int, data: str, msg_id: int):
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "list":
        await list_orders(chat_id, user_id, msg_id)
    elif action == "view":
        order_id = int(parts[2])
        await view_order(chat_id, user_id, msg_id, order_id)
    elif action == "cancel":
        order_id = int(parts[2])
        await cancel_order(chat_id, user_id, msg_id, order_id)
    elif action == "sales":
        status_filter = parts[2] if len(parts) > 2 else "all"
        await seller_sales(chat_id, user_id, msg_id, status_filter)
    elif action == "sales_view":
        order_id = int(parts[2])
        await seller_view_order(chat_id, user_id, msg_id, order_id)
    elif action == "ship":
        order_id = int(parts[2])
        await ship_order(chat_id, user_id, msg_id, order_id)


async def list_orders(chat_id: int, user_id: int, msg_id: int):
    user = await db.get_user(user_id)
    orders = await db.get_user_orders(user["id"])

    await api.delete_message(chat_id, msg_id)

    if not orders:
        await api.send_message(chat_id, "📦 You have no orders yet.", kb.back_kb("menu:main"))
        return

    await api.send_message(chat_id, "📦 *My Orders*\n\nSelect an order to view:", kb.orders_kb(orders))


async def view_order(chat_id: int, user_id: int, msg_id: int, order_id: int):
    order = await db.get_order(order_id)
    if not order:
        await api.delete_message(chat_id, msg_id)
        await api.send_message(chat_id, "❌ Order not found.", kb.back_kb("order:list"))
        return

    items = await db.get_order_items(order_id)
    address = await db.get_address(order["address_id"]) if order["address_id"] else None

    lines = [f"📦 *Order #{order_id}*\n", f"Status: *{order['status']}*"]
    if address:
        lines.append(f"📍 Address: {address['full_address']}")
    lines.append("")
    for it in items:
        opts = json.loads(it.get("selected_options_json", "{}"))
        opt_str = " | ".join(f"{k}:{v}" for k, v in opts.items())
        lines.append(f"• {it['product_name']} x{it['quantity']} — ${it['price'] * it['quantity']:.2f}")
        if opt_str:
            lines.append(f"  _{opt_str}_")
    lines.append(f"\n💰 *Total: ${order['total']:.2f}*")

    if order.get("payment_address"):
        lines.append(f"\n💳 Payment address: `{order['payment_address']}`")

    await api.delete_message(chat_id, msg_id)
    await api.send_message(chat_id, "\n".join(lines), kb.order_detail_kb(order))


async def cancel_order(chat_id: int, user_id: int, msg_id: int, order_id: int):
    order = await db.get_order(order_id)
    if not order or order["status"] not in ("pending_payment", "preparing"):
        await api.answer_callback(str(msg_id), "❌ Cannot cancel this order.")
        return

    await db.update_order_status(order_id, "cancelled")
    await api.delete_message(chat_id, msg_id)
    await api.send_message(chat_id, f"❌ Order #{order_id} has been cancelled.", kb.back_kb("order:list"))


# ── Seller Sales ───────────────────────────────────────
async def seller_sales(chat_id: int, user_id: int, msg_id: int, status_filter: str):
    user = await db.get_user(user_id)

    status_map = {"all": None, "preparing": "preparing", "cancelled": "cancelled"}
    status = status_map.get(status_filter)
    orders = await db.get_seller_orders(user["id"], status)

    # Count per status for button labels
    prep_count = await db.count_seller_orders(user["id"], "preparing")
    cancel_count = await db.count_seller_orders(user["id"], "cancelled")

    await api.delete_message(chat_id, msg_id)

    if not orders:
        text = "📦 No orders found."
    else:
        lines = [f"📦 *Sales History* ({status_filter})\n"]
        for o in orders[:20]:
            lines.append(f"• Order #{o['id']} — {o['status']} — ${o['total']:.2f}")
        text = "\n".join(lines)

    sale_kb = kb._inline_kb([
        [kb._btn("📋 My Sales History", "order:sales:all")],
        [kb._btn(f"📦 In Preparation ({prep_count})", "order:sales:preparing")],
        [kb._btn(f"❌ Order Cancelled ({cancel_count})", "order:sales:cancelled")],
        [kb._btn("◀️ Back", "sell:menu")],
    ])
    await api.send_message(chat_id, text, sale_kb)


async def seller_view_order(chat_id: int, user_id: int, msg_id: int, order_id: int):
    order = await db.get_order(order_id)
    if not order:
        await api.delete_message(chat_id, msg_id)
        await api.send_message(chat_id, "❌ Order not found.", kb.back_kb("sell:orders"))
        return

    items = await db.get_order_items(order_id)
    address = await db.get_address(order["address_id"]) if order["address_id"] else None

    lines = [f"📦 *Order #{order_id}*\n", f"Status: *{order['status']}*"]
    if address:
        lines.append(f"📍 Delivery: {address['full_address']}")
    for it in items:
        lines.append(f"• {it['product_name']} x{it['quantity']} — ${it['price']:.2f}")
    lines.append(f"\n💰 Total: ${order['total']:.2f}")

    btns: list[list[dict]] = []
    if order["status"] == "preparing":
        btns.append([kb._btn("🚚 Mark as Shipped", f"order:ship:{order_id}")])
    btns.append([kb._btn("◀️ Back", "order:sales:all")])

    await api.delete_message(chat_id, msg_id)
    await api.send_message(chat_id, "\n".join(lines), kb._inline_kb(btns))


async def ship_order(chat_id: int, user_id: int, msg_id: int, order_id: int):
    await db.update_order_status(order_id, "shipped")
    await api.delete_message(chat_id, msg_id)
    await api.send_message(chat_id, f"🚚 Order #{order_id} marked as shipped!", kb.back_kb("order:sales:all"))
