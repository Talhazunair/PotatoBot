"""Product browsing and viewing."""
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

    # Get category name
    cat_name = "N/A"
    if product.get("category_id"):
        cat = await db.get_category(product["category_id"])
        if cat:
            cat_name = cat["name"]
            if cat.get("parent_id"):
                parent = await db.get_category(cat["parent_id"])
                if parent:
                    cat_name = f"{parent['name']} > {cat['name']}"

    text = (
        f"📦 *{product['name']}*\n\n"
        f"{product['description']}\n\n"
        f"💰 Price: *${product['price']:.2f}*\n"
        f"📁 Category: {cat_name}\n"
    )

    await api.delete_message(chat_id, msg_id)

    # Send product images first
    if images:
        for fid in images[:5]:
            await api.send_photo_by_id(chat_id, fid)

    keyboard = kb.product_detail_kb(product)
    await api.send_message(chat_id, text, keyboard)

