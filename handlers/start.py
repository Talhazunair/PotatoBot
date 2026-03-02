"""Start handler — /start command, affiliate deep-links, main menu."""
import potato_api as api
import database as db
from config import ADMIN_IDS, BOT_USERNAME
import keyboards as kb


async def handle_start(chat_id: int, user_id: int, first_name: str, text: str, msg_id: int):
    """Process /start with optional affiliate code."""
    referred_by = None
    if " " in text:
        param = text.split(" ", 1)[1].strip()
        if param.isdigit():
            referred_by = int(param)

    user = await db.create_user(user_id, first_name, referred_by)
    await show_main_menu(chat_id, user_id, user)


async def show_main_menu(chat_id: int, user_id: int, user: dict | None = None):
    if user is None:
        user = await db.get_user(user_id)
    if user is None:
        user = await db.create_user(user_id)

    role = user.get("role", "buyer")
    if user_id in ADMIN_IDS:
        keyboard = kb.main_menu_with_admin_kb()
    elif role == "seller":
        keyboard = kb.main_menu_with_seller_kb()
    else:
        keyboard = kb.main_menu_kb()

    affiliate_link = f"https://potato.im/{BOT_USERNAME}?start={user_id}"
    text = (
        f"👋 *Welcome to the Marketplace!*\n\n"
        f"Your affiliate link:\n{affiliate_link}\n\n"
        f"Choose an option below:"
    )
    await api.send_message(chat_id, text, keyboard)
