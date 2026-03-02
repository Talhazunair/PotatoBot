"""Address management — add/view delivery addresses."""
import potato_api as api
import database as db
import keyboards as kb


async def handle_callback(chat_id: int, user_id: int, data: str, msg_id: int):
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "list":
        await list_addresses(chat_id, user_id, msg_id)
    elif action == "add":
        await start_add_address(chat_id, user_id, msg_id)
    elif action == "view":
        addr_id = int(parts[2])
        await view_address(chat_id, user_id, msg_id, addr_id)
    elif action == "select":
        addr_id = int(parts[2])
        await select_address(chat_id, user_id, msg_id, addr_id)


async def list_addresses(chat_id: int, user_id: int, msg_id: int):
    user = await db.get_user(user_id)
    addresses = await db.get_addresses(user["id"])

    await api.delete_message(chat_id, msg_id)

    if not addresses:
        await api.send_message(
            chat_id, "📍 You have no saved addresses.",
            kb._inline_kb([
                [kb._btn("➕ Add Address", "addr:add")],
                [kb._btn("◀️ Main Menu", "menu:main")],
            ]),
        )
        return

    await api.send_message(chat_id, "📍 *My Addresses*", kb.addresses_kb(addresses))


async def view_address(chat_id: int, user_id: int, msg_id: int, addr_id: int):
    addr = await db.get_address(addr_id)
    if not addr:
        await api.delete_message(chat_id, msg_id)
        await api.send_message(chat_id, "❌ Address not found.", kb.back_kb("addr:list"))
        return

    await api.delete_message(chat_id, msg_id)
    await api.send_message(
        chat_id,
        f"📍 *{addr['label']}*\n\n{addr['full_address']}",
        kb.back_kb("addr:list"),
    )


async def start_add_address(chat_id: int, user_id: int, msg_id: int):
    await db.set_fsm(user_id, "addr_label", {})
    await api.delete_message(chat_id, msg_id)
    await api.send_message(chat_id, "📍 Enter a label for this address (e.g. Home, Office):")


async def handle_text(chat_id: int, user_id: int, text: str, msg_id: int):
    """Handle FSM text input for address creation."""
    state, fdata = await db.get_fsm(user_id)

    if state == "addr_label":
        fdata["label"] = text
        await db.set_fsm(user_id, "addr_full", fdata)
        await api.send_message(chat_id, "📍 Now enter the full delivery address:")
    elif state == "addr_full":
        user = await db.get_user(user_id)
        await db.add_address(user["id"], fdata.get("label", ""), text)
        await db.clear_fsm(user_id)
        await api.send_message(
            chat_id,
            "✅ Address saved successfully!",
            kb.back_kb("addr:list"),
        )


async def select_address(chat_id: int, user_id: int, msg_id: int, addr_id: int):
    """Select address during checkout flow."""
    state, fdata = await db.get_fsm(user_id)
    if state == "checkout_address":
        fdata["address_id"] = addr_id
        await db.set_fsm(user_id, "checkout_confirm", fdata)

        addr = await db.get_address(addr_id)
        user = await db.get_user(user_id)
        items = await db.get_cart(user["id"])

        total = sum(i["price"] * i["quantity"] for i in items)

        summary = (
            f"📋 *Order Summary*\n\n"
            f"👤 Name: {user.get('first_name', 'N/A')}\n"
            f"📍 Delivery Address: {addr['full_address']}\n\n"
            f"*Items:*\n"
        )
        for it in items:
            summary += f"  • {it['name']} x{it['quantity']} — ${it['price'] * it['quantity']:.2f}\n"
        summary += f"\n💰 *Total: ${total:.2f}*"

        await api.delete_message(chat_id, msg_id)
        await api.send_message(chat_id, summary, kb.confirm_order_kb())
    else:
        await api.answer_callback(str(msg_id), "Address selected!")
