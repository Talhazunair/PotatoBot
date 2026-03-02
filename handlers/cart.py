"""Cart and checkout flow."""
import json
import potato_api as api
import database as db
import keyboards as kb
import coinremitter


async def handle_callback(chat_id: int, user_id: int, data: str, msg_id: int):
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "add":
        product_id = int(parts[2])
        await add_to_cart(chat_id, user_id, product_id, msg_id)
    elif action == "view":
        await view_cart(chat_id, user_id, msg_id)
    elif action == "remove":
        item_id = int(parts[2])
        await remove_item(chat_id, user_id, item_id, msg_id)
    elif action == "checkout":
        await checkout(chat_id, user_id, msg_id)
    elif action == "confirm":
        await confirm_order(chat_id, user_id, msg_id)


async def add_to_cart(chat_id: int, user_id: int, product_id: int, msg_id: int):
    product = await db.get_product(product_id)
    if not product:
        await api.answer_callback(str(msg_id), "❌ Product not found.")
        return

    # Get selected options from FSM if any
    state, fdata = await db.get_fsm(user_id)
    options = fdata.get("selected_options", {}) if state == "selecting_options" else {}
    await db.clear_fsm(user_id)

    user = await db.get_user(user_id)
    await db.add_to_cart(user["id"], product_id, qty=1, options=options)

    await api.delete_message(chat_id, msg_id)

    # Check if user has an address
    addresses = await db.get_addresses(user["id"])
    if not addresses:
        text = (
            f"✅ *{product['name']}* added to cart!\n\n"
            f"⚠️ You don't have a delivery address yet."
        )
        keyboard = kb._inline_kb([
            [kb._btn("📍 Add Address", "addr:add")],
            [kb._btn("🛒 View Cart", "cart:view")],
            [kb._btn("◀️ Main Menu", "menu:main")],
        ])
    else:
        text = f"✅ *{product['name']}* added to cart!"
        keyboard = kb._inline_kb([
            [kb._btn("🛒 View Cart", "cart:view")],
            [kb._btn("🛍 Continue Shopping", "prod:list:0")],
            [kb._btn("◀️ Main Menu", "menu:main")],
        ])
    await api.send_message(chat_id, text, keyboard)


async def view_cart(chat_id: int, user_id: int, msg_id: int):
    user = await db.get_user(user_id)
    items = await db.get_cart(user["id"])

    await api.delete_message(chat_id, msg_id)

    if not items:
        await api.send_message(chat_id, "🛒 Your cart is empty.", kb.back_kb("menu:main"))
        return

    total = sum(i["price"] * i["quantity"] for i in items)
    lines = ["🛒 *Your Cart*\n"]
    for i, item in enumerate(items, 1):
        opts = json.loads(item.get("selected_options_json", "{}"))
        opt_str = " | ".join(f"{k}: {v}" for k, v in opts.items()) if opts else ""
        lines.append(f"{i}. {item['name']} x{item['quantity']} — ${item['price'] * item['quantity']:.2f}")
        if opt_str:
            lines.append(f"   _{opt_str}_")

    lines.append(f"\n💰 *Total: ${total:.2f}*")
    await api.send_message(chat_id, "\n".join(lines), kb.cart_kb(items))


async def remove_item(chat_id: int, user_id: int, item_id: int, msg_id: int):
    await db.remove_cart_item(item_id)
    await view_cart(chat_id, user_id, msg_id)


async def checkout(chat_id: int, user_id: int, msg_id: int):
    user = await db.get_user(user_id)
    addresses = await db.get_addresses(user["id"])

    await api.delete_message(chat_id, msg_id)

    if not addresses:
        await api.send_message(
            chat_id,
            "📍 You need a delivery address before checkout.",
            kb._inline_kb([
                [kb._btn("📍 Add Address", "addr:add")],
                [kb._btn("◀️ Back to Cart", "cart:view")],
            ]),
        )
        return

    # Store checkout state — user picks address next
    await db.set_fsm(user_id, "checkout_address", {})
    await api.send_message(
        chat_id,
        "📍 Select a delivery address for this order:",
        kb.address_select_kb(addresses),
    )


async def confirm_order(chat_id: int, user_id: int, msg_id: int):
    """Final order confirmation — create order + CoinRemitter invoice."""
    user = await db.get_user(user_id)
    state, fdata = await db.get_fsm(user_id)

    address_id = fdata.get("address_id")
    if not address_id:
        await api.delete_message(chat_id, msg_id)
        await api.send_message(chat_id, "❌ No address selected.", kb.back_kb("cart:view"))
        return

    items = await db.get_cart(user["id"])
    if not items:
        await api.delete_message(chat_id, msg_id)
        await api.send_message(chat_id, "❌ Cart is empty.", kb.back_kb("menu:main"))
        return

    total = sum(i["price"] * i["quantity"] for i in items)
    address = await db.get_address(address_id)

    # Create CoinRemitter invoice
    inv_result = await coinremitter.create_invoice(
        amount=total,
        description=f"Marketplace Order — {len(items)} items",
        notify_url="",  # set if you have a public webhook
    )

    payment_address = ""
    invoice_id = ""
    if inv_result.get("success"):
        inv_data = inv_result.get("data", {})
        payment_address = inv_data.get("address", "")
        invoice_id = inv_data.get("invoice_id", inv_data.get("id", ""))

    # Create order
    order_id = await db.create_order(
        user["id"], address_id, total, payment_address, str(invoice_id),
    )
    for item in items:
        opts = json.loads(item.get("selected_options_json", "{}"))
        await db.add_order_item(order_id, item["product_id"], item["quantity"], item["price"], opts)

    await db.clear_cart(user["id"])
    await db.clear_fsm(user_id)

    await api.delete_message(chat_id, msg_id)

    summary = (
        f"✅ *Order #{order_id} Created!*\n\n"
        f"📍 *Delivery Address:* {address['full_address']}\n"
        f"💰 *Total:* ${total:.2f}\n\n"
    )
    if payment_address:
        summary += (
            f"💳 *Payment Address (USDT):*\n`{payment_address}`\n\n"
            f"Send exactly *${total:.2f}* in USDT to complete your order.\n"
            f"You will be notified once payment is confirmed."
        )
    else:
        summary += "⏳ Payment processing — please check back shortly."

    await api.send_message(chat_id, summary, kb.back_kb("menu:main"))
