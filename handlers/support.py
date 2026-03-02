"""Support system — send request in a single message, admin reviews."""
import potato_api as api
import database as db
import keyboards as kb


async def handle_callback(chat_id: int, user_id: int, data: str, msg_id: int):
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "start":
        await start_support(chat_id, user_id, msg_id)


async def start_support(chat_id: int, user_id: int, msg_id: int):
    await db.set_fsm(user_id, "support_message", {})
    await api.delete_message(chat_id, msg_id)
    await api.send_message(
        chat_id,
        "📞 *Support*\n\n"
        "Please send your request in a single message!\n"
        "An admin will process your request as quickly as possible.",
    )


async def handle_text(chat_id: int, user_id: int, text: str, msg_id: int):
    """FSM handler for support message input."""
    state, fdata = await db.get_fsm(user_id)
    if state == "support_message":
        user = await db.get_user(user_id)
        ticket_id = await db.create_ticket(user["id"], text)
        await db.clear_fsm(user_id)
        await api.send_message(
            chat_id,
            f"✅ Your request has been received (Ticket #{ticket_id}).\n"
            f"You will receive a response as soon as possible!",
            kb.back_kb("menu:main"),
        )
