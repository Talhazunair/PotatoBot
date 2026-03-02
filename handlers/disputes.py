"""Dispute system — Open Dispute → Select Order → Select Product → Reason → Message."""
import potato_api as api
import database as db
import keyboards as kb


async def handle_callback(chat_id: int, user_id: int, data: str, msg_id: int):
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "list":
        await list_disputes(chat_id, user_id, msg_id)
    elif action == "open":
        await open_dispute(chat_id, user_id, msg_id)
    elif action == "order":
        order_id = int(parts[2])
        await select_order(chat_id, user_id, msg_id, order_id)
    elif action == "product":
        order_id = int(parts[2])
        product_id = int(parts[3])
        await select_product(chat_id, user_id, msg_id, order_id, product_id)
    elif action == "reason":
        order_id = int(parts[2])
        product_id = int(parts[3])
        reason = parts[4]
        await select_reason(chat_id, user_id, msg_id, order_id, product_id, reason)
    elif action == "view":
        dispute_id = int(parts[2])
        await view_dispute(chat_id, user_id, msg_id, dispute_id)


async def list_disputes(chat_id: int, user_id: int, msg_id: int):
    user = await db.get_user(user_id)
    disputes = await db.get_user_disputes(user["id"])

    await api.delete_message(chat_id, msg_id)
    await api.send_message(chat_id, "⚠️ *My Disputes*", kb.user_disputes_kb(disputes))


async def open_dispute(chat_id: int, user_id: int, msg_id: int):
    user = await db.get_user(user_id)
    orders = await db.get_user_orders(user["id"])

    await api.delete_message(chat_id, msg_id)

    if not orders:
        await api.send_message(chat_id, "You have no orders to dispute.", kb.back_kb("menu:main"))
        return

    await api.send_message(
        chat_id,
        "⚠️ *Open a Dispute*\n\nSelect the order:",
        kb.dispute_orders_kb(orders),
    )


async def select_order(chat_id: int, user_id: int, msg_id: int, order_id: int):
    items = await db.get_order_items(order_id)

    await api.delete_message(chat_id, msg_id)

    if not items:
        await api.send_message(chat_id, "No items in this order.", kb.back_kb("disp:open"))
        return

    text = (
        f"You want to open a dispute for:\n"
        f"*Order #{order_id}*\n\n"
    )
    for it in items:
        text += f"{it['product_name']} | ${it['price']:.2f} | Qty: {it['quantity']}\n"
    text += "\nSelect the product:"

    await api.send_message(chat_id, text, kb.dispute_products_kb(items, order_id))


async def select_product(chat_id: int, user_id: int, msg_id: int,
                         order_id: int, product_id: int):
    await api.delete_message(chat_id, msg_id)

    product = await db.get_product(product_id)
    product_name = product["name"] if product else "Unknown"

    text = (
        f"⚠️ Dispute for *Order #{order_id}*\n"
        f"Product: *{product_name}*\n\n"
        f"Select the reason:"
    )
    await api.send_message(chat_id, text, kb.dispute_reasons_kb(order_id, product_id))


async def select_reason(chat_id: int, user_id: int, msg_id: int,
                        order_id: int, product_id: int, reason: str):
    reason_labels = {
        "not_received": "Product not received",
        "defective": "Defective product",
        "mismatch": "Product does not match description",
        "other": "Other",
    }
    label = reason_labels.get(reason, reason)

    await api.delete_message(chat_id, msg_id)

    if reason == "other":
        # Ask user to describe
        await db.set_fsm(user_id, "dispute_message", {
            "order_id": order_id,
            "product_id": product_id,
            "reason": label,
        })
        await api.send_message(chat_id, "📝 Please describe the issue in a single message:")
        return

    # Create dispute directly
    user = await db.get_user(user_id)
    dispute_id = await db.create_dispute(order_id, product_id, user["id"], label)
    await api.send_message(
        chat_id,
        f"✅ Dispute #{dispute_id} opened!\n\n"
        f"Order #{order_id}\nReason: {label}\n\n"
        f"An admin will review your dispute shortly.",
        kb.back_kb("disp:list"),
    )


async def view_dispute(chat_id: int, user_id: int, msg_id: int, dispute_id: int):
    dispute = await db.get_dispute(dispute_id)
    if not dispute:
        await api.delete_message(chat_id, msg_id)
        await api.send_message(chat_id, "❌ Dispute not found.", kb.back_kb("disp:list"))
        return

    product = await db.get_product(dispute["product_id"])
    product_name = product["name"] if product else "Unknown"

    text = (
        f"⚠️ *Dispute #{dispute_id}*\n\n"
        f"Order: #{dispute['order_id']}\n"
        f"Product: {product_name}\n"
        f"Reason: {dispute['reason']}\n"
        f"Status: {dispute['status']}\n"
    )
    if dispute["message"]:
        text += f"\nMessage: {dispute['message']}"

    await api.delete_message(chat_id, msg_id)
    await api.send_message(chat_id, text, kb.back_kb("disp:list"))


async def handle_text(chat_id: int, user_id: int, text: str, msg_id: int):
    """FSM handler for dispute 'other' reason description."""
    state, fdata = await db.get_fsm(user_id)
    if state == "dispute_message":
        user = await db.get_user(user_id)
        dispute_id = await db.create_dispute(
            fdata["order_id"], fdata["product_id"], user["id"],
            fdata["reason"], message=text,
        )
        await db.clear_fsm(user_id)
        await api.send_message(
            chat_id,
            f"✅ Dispute #{dispute_id} opened!\n\n"
            f"Order #{fdata['order_id']}\nReason: {fdata['reason']}\n"
            f"Your message has been recorded.\n\n"
            f"An admin will review your dispute shortly.",
            kb.back_kb("disp:list"),
        )
