"""Product browsing and viewing."""
import json
import potato_api as api
import database as db
import keyboards as kb
from config import PRODUCTS_PER_PAGE


async def handle_callback(chat_id: int, user_id: int, data: str, msg_id: int):
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "list":
        page = int(parts[2]) if len(parts) > 2 else 0
        await list_products(chat_id, msg_id, page)
    elif action == "view":
        product_id = int(parts[2])
        await view_product(chat_id, user_id, msg_id, product_id)
    elif action == "opt":
        product_id = int(parts[2])
        opt_name = parts[3]
        opt_val = parts[4]
        await select_option(chat_id, user_id, product_id, opt_name, opt_val, msg_id)


async def list_products(chat_id: int, msg_id: int, page: int = 0):
    products = await db.list_products(page=page, limit=PRODUCTS_PER_PAGE)
    total = await db.count_products()

    if not products:
        text = "📭 No products available at the moment."
        keyboard = kb.back_kb("menu:main")
    else:
        text = f"🛍 *Products* (Page {page + 1})\n\nSelect a product to view details:"
        keyboard = kb.products_kb(products, page, total, PRODUCTS_PER_PAGE)

    await api.delete_message(chat_id, msg_id)
    await api.send_message(chat_id, text, keyboard)


async def view_product(chat_id: int, user_id: int, msg_id: int, product_id: int):
    product = await db.get_product(product_id)
    if not product:
        await api.delete_message(chat_id, msg_id)
        await api.send_message(chat_id, "❌ Product not found.", kb.back_kb("prod:list:0"))
        return

    images = await db.get_product_images(product_id)
    options = json.loads(product.get("options_json", "[]"))

    text = (
        f"📦 *{product['name']}*\n\n"
        f"{product['description']}\n\n"
        f"💰 Price: *${product['price']:.2f}*\n"
        f"📁 Category: {product['category'] or 'N/A'}\n"
    )

    if options:
        text += "\n*Options:*\n"
        for opt in options:
            text += f"  • {opt.get('name', 'Option')}: {', '.join(opt.get('values', []))}\n"

    await api.delete_message(chat_id, msg_id)

    # Send product images first
    if images:
        for fid in images[:5]:
            await api.send_photo_by_id(chat_id, fid)

    keyboard = kb.product_detail_kb(product, options)
    await api.send_message(chat_id, text, keyboard)


async def select_option(chat_id: int, user_id: int, product_id: int,
                        opt_name: str, opt_val: str, msg_id: int):
    """Store selected option in FSM and acknowledge."""
    state, fdata = await db.get_fsm(user_id)
    selected = fdata.get("selected_options", {})
    selected[opt_name] = opt_val
    await db.set_fsm(user_id, "selecting_options", {**fdata, "selected_options": selected, "product_id": product_id})
    await api.answer_callback(str(msg_id), f"✅ {opt_name}: {opt_val}")
