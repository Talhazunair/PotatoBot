"""Product browsing and viewing — with category support."""
import logging
import potato_api as api
import database as db
import keyboards as kb
from config import PRODUCTS_PER_PAGE

log = logging.getLogger("products")


async def handle_callback(chat_id: int, user_id: int, data: str, msg_id: int):
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "browse":
        await browse_categories(chat_id, msg_id)
    elif action == "cat":
        cat_id = int(parts[2])
        await browse_category(chat_id, msg_id, cat_id)
    elif action == "subcat":
        subcat_id = int(parts[2])
        await browse_subcategory(chat_id, msg_id, subcat_id)
    elif action == "cat_all":
        cat_id = int(parts[2])
        await list_products_by_category(chat_id, msg_id, cat_id, 0)
    elif action == "list":
        page = int(parts[2]) if len(parts) > 2 else 0
        await list_products(chat_id, msg_id, page)
    elif action == "page":
        page = int(parts[2]) if len(parts) > 2 else 0
        # Retrieve current filter from FSM
        state, fdata = await db.get_fsm(user_id)
        cat_filter = fdata.get("browse_cat_id") if state == "browsing" else None
        await list_products(chat_id, msg_id, page, category_id=cat_filter)
    elif action == "view":
        product_id = int(parts[2])
        await view_product(chat_id, user_id, msg_id, product_id)


async def browse_categories(chat_id: int, msg_id: int):
    """Show category list for browsing. If no categories exist, show all products."""
    categories = await db.get_categories(parent_id=None)
    await api.delete_message(chat_id, msg_id)

    if not categories:
        # No categories — go straight to all products
        await _show_products(chat_id, 0)
        return

    await api.send_message(
        chat_id,
        "📁 *Browse by Category*\n\nSelect a category or view all products:",
        kb.buyer_categories_kb(categories),
    )


async def browse_category(chat_id: int, msg_id: int, cat_id: int):
    """User tapped a category — show subcategories if any, otherwise list products."""
    cat = await db.get_category(cat_id)
    await api.delete_message(chat_id, msg_id)

    if not cat:
        await api.send_message(chat_id, "❌ Category not found.", kb.back_kb("prod:browse"))
        return

    subcategories = await db.get_categories(parent_id=cat_id)
    if subcategories:
        await api.send_message(
            chat_id,
            f"📂 *{cat['name']}*\n\nSelect a subcategory:",
            kb.buyer_subcategories_kb(subcategories, cat_id),
        )
    else:
        # No subcategories — list products in this category
        await list_products_by_category(chat_id, None, cat_id, 0)


async def browse_subcategory(chat_id: int, msg_id: int, subcat_id: int):
    """List products in a subcategory."""
    await api.delete_message(chat_id, msg_id)
    await list_products_by_category(chat_id, None, subcat_id, 0)


async def list_products_by_category(chat_id: int, msg_id: int | None, cat_id: int, page: int):
    """List products filtered by category_id."""
    if msg_id:
        await api.delete_message(chat_id, msg_id)

    # Get all subcategory IDs so we include products in subcategories too
    cat_ids = [cat_id]
    subcats = await db.get_categories(parent_id=cat_id)
    for s in subcats:
        cat_ids.append(s["id"])

    # For now, use a single category_id filter. If there are subcategories,
    # we list from the selected one only.
    await _show_products(chat_id, page, category_id=cat_id)


async def list_products(chat_id: int, msg_id: int, page: int = 0, category_id: int | None = None):
    """List all products (no filter)."""
    await api.delete_message(chat_id, msg_id)
    await _show_products(chat_id, page, category_id=category_id)


async def _show_products(chat_id: int, page: int, category_id: int | None = None):
    """Internal helper to show paginated product list."""
    products = await db.list_products(page=page, limit=PRODUCTS_PER_PAGE, category_id=category_id)
    total = await db.count_products(category_id=category_id)

    if not products:
        text = "📭 No products available in this category."
        keyboard = kb.back_kb("prod:browse")
    else:
        cat_label = ""
        if category_id:
            cat = await db.get_category(category_id)
            if cat:
                cat_label = f" — {cat['name']}"
        text = f"🛍 *Products{cat_label}* (Page {page + 1})\n\nSelect a product:"
        keyboard = kb.products_kb(products, page, total, PRODUCTS_PER_PAGE, back_cb="prod:browse")

    await api.send_message(chat_id, text, keyboard)


async def view_product(chat_id: int, user_id: int, msg_id: int, product_id: int):
    product = await db.get_product(product_id)
    if not product:
        await api.delete_message(chat_id, msg_id)
        await api.send_message(chat_id, "❌ Product not found.", kb.back_kb("prod:browse"))
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
