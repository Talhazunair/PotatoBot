"""Update dispatcher — routes incoming Potato updates to the correct handler."""
import logging
import potato_api as api
import database as db
from handlers import start, products, cart, orders, addresses, wallet, seller, admin, disputes, support

log = logging.getLogger("router")

# Callback prefix → handler module
CB_HANDLERS = {
    "prod": products,
    "cart": cart,
    "order": orders,
    "addr": addresses,
    "wal": wallet,
    "sell": seller,
    "adm": admin,
    "disp": disputes,
    "supp": support,
}

# FSM state prefix → handler module (for text input routing)
FSM_TEXT_HANDLERS = {
    "addr_": addresses,
    "sell_": seller,
    "edit_": seller,
    "withdraw_": wallet,
    "support_": support,
    "dispute_": disputes,
    "admin_": admin,
    "checkout_": cart,
}


async def dispatch(update: dict):
    """Route a single Potato update to the correct handler."""
    try:
        # ── Callback Query ─────────────────────────────
        cb = update.get("callback_query")
        if cb:
            await _handle_callback(cb)
            return

        # ── Message ────────────────────────────────────
        msg = update.get("message")
        if msg:
            await _handle_message(msg)
            return

    except Exception:
        log.exception("Error dispatching update %s", update.get("update_id"))


async def _handle_callback(cb: dict):
    user = cb.get("from", {})
    # In Potato private chats, chat.id can be the bot's own ID
    # Always use from.id for sending responses in private chats
    user_id = user.get("id")
    chat_id = user_id
    msg_id = cb.get("message_id", 0)
    data = cb.get("data", "")

    if not chat_id or not data:
        return

    # Answer the callback immediately to remove loading indicator
    inline_msg_id = cb.get("inline_message_id", str(msg_id))
    await api.answer_callback(inline_msg_id)

    # menu:main is handled here directly
    if data == "menu:main":
        await _delete_and_show_menu(chat_id, user_id, msg_id)
        return

    prefix = data.split(":")[0]
    handler = CB_HANDLERS.get(prefix)
    if handler:
        await handler.handle_callback(chat_id, user_id, data, msg_id)
    else:
        log.warning("No handler for callback prefix '%s'", prefix)


async def _handle_message(msg: dict):
    chat = msg.get("chat", {})
    user = msg.get("from", {})
    chat_id = chat.get("id") or user.get("id")
    user_id = user.get("id")
    msg_id = msg.get("message_id", 0)
    text = msg.get("text", "")

    if not chat_id:
        return

    # ── Photo upload ───────────────────────────────
    photo = msg.get("photo")
    document = msg.get("document")
    if photo or document:
        file_id = ""
        if photo and isinstance(photo, dict):
            file_id = photo.get("file_id", "")
        elif photo and isinstance(photo, list):
            file_id = photo[-1].get("file_id", "") if photo else ""
        elif document and isinstance(document, dict):
            file_id = document.get("file_id", "")

        if file_id:
            st, _ = await db.get_fsm(user_id)
            if st == "sell_image":
                await seller.handle_photo(chat_id, user_id, file_id, msg_id)
                return

    if not text:
        return

    # ── Commands ───────────────────────────────────
    if text.startswith("/start"):
        first_name = user.get("first_name", "")
        # Delete user's /start message to keep chat clean
        await api.delete_message(chat_id, msg_id)
        await start.handle_start(chat_id, user_id, first_name, text, msg_id)
        return

    if text.strip() == "/done":
        st, _ = await db.get_fsm(user_id)
        if st == "sell_image":
            await api.delete_message(chat_id, msg_id)
            await seller.handle_done(chat_id, user_id, msg_id)
            return

    # ── FSM text routing ───────────────────────────
    state, _ = await db.get_fsm(user_id)
    if state:
        for prefix, handler in FSM_TEXT_HANDLERS.items():
            if state.startswith(prefix):
                # Delete user's text message to keep chat clean
                await api.delete_message(chat_id, msg_id)
                await handler.handle_text(chat_id, user_id, text, msg_id)
                return


async def _delete_and_show_menu(chat_id: int, user_id: int, msg_id: int):
    await api.delete_message(chat_id, msg_id)
    await start.show_main_menu(chat_id, user_id)
