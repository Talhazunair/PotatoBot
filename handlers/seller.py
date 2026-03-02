"""Seller dashboard — add/edit products, upload images."""
import json
import potato_api as api
import database as db
import keyboards as kb


async def handle_callback(chat_id: int, user_id: int, data: str, msg_id: int):
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "apply":
        await apply_seller(chat_id, user_id, msg_id)
    elif action == "menu":
        await seller_menu(chat_id, user_id, msg_id)
    elif action == "add":
        await start_add_product(chat_id, user_id, msg_id)
    elif action == "list":
        page = int(parts[2]) if len(parts) > 2 else 0
        await list_products(chat_id, user_id, msg_id, page)
    elif action == "edit":
        product_id = int(parts[2])
        await edit_product(chat_id, user_id, msg_id, product_id)
    elif action == "field":
        product_id = int(parts[2])
        field = parts[3]
        await start_edit_field(chat_id, user_id, msg_id, product_id, field)
    elif action == "img":
        product_id = int(parts[2])
        await start_image_upload(chat_id, user_id, msg_id, product_id)
    elif action == "deactivate":
        product_id = int(parts[2])
        await deactivate(chat_id, user_id, msg_id, product_id)
    elif action == "orders":
        await seller_orders(chat_id, user_id, msg_id)


async def apply_seller(chat_id: int, user_id: int, msg_id: int):
    """Buyer requests to become a seller."""
    user = await db.get_user(user_id)
    if not user:
        user = await db.create_user(user_id)

    if user["role"] == "seller":
        await api.delete_message(chat_id, msg_id)
        await api.send_message(chat_id, "✅ You are already a seller!", kb.back_kb("sell:menu"))
        return

    has_pending = await db.has_pending_request(user["id"])
    if has_pending:
        await api.delete_message(chat_id, msg_id)
        await api.send_message(
            chat_id,
            "⏳ You already have a pending seller request.\nAn admin will review it shortly!",
            kb.back_kb("menu:main"),
        )
        return

    await db.create_seller_request(user["id"], user_id)
    await api.delete_message(chat_id, msg_id)
    await api.send_message(
        chat_id,
        "✅ *Seller application submitted!*\n\n"
        "An admin will review your request.\n"
        "You will be notified once approved!",
        kb.back_kb("menu:main"),
    )


async def seller_menu(chat_id: int, user_id: int, msg_id: int):
    await api.delete_message(chat_id, msg_id)
    await api.send_message(chat_id, "🏪 *Seller Dashboard*", kb.seller_menu_kb())


async def list_products(chat_id: int, user_id: int, msg_id: int, page: int = 0):
    user = await db.get_user(user_id)
    products = await db.list_products(page=page, seller_id=user["id"], active_only=False)
    total = await db.count_products(seller_id=user["id"], active_only=False)

    await api.delete_message(chat_id, msg_id)

    if not products:
        await api.send_message(chat_id, "📋 You have no products yet.", kb.back_kb("sell:menu"))
        return

    await api.send_message(
        chat_id,
        f"📋 *My Products* (Page {page + 1})",
        kb.seller_products_kb(products, page, total),
    )


async def edit_product(chat_id: int, user_id: int, msg_id: int, product_id: int):
    product = await db.get_product(product_id)
    if not product:
        await api.delete_message(chat_id, msg_id)
        await api.send_message(chat_id, "❌ Product not found.", kb.back_kb("sell:list:0"))
        return

    options = json.loads(product.get("options_json", "[]"))
    text = (
        f"✏️ *Edit Product*\n\n"
        f"Name: {product['name']}\n"
        f"Price: ${product['price']:.2f}\n"
        f"Description: {product['description'][:100]}\n"
        f"Status: {'Active' if product['active'] else 'Inactive'}\n"
    )
    if options:
        text += "Options: " + ", ".join(o.get("name", "") for o in options)

    images = await db.get_product_images(product_id)
    text += f"\nImages: {len(images)}"

    await api.delete_message(chat_id, msg_id)
    await api.send_message(chat_id, text, kb.edit_product_kb(product))


async def start_edit_field(chat_id: int, user_id: int, msg_id: int, product_id: int, field: str):
    prompts = {
        "name": "Enter the new product name:",
        "price": "Enter the new price (number):",
        "description": "Enter the new description:",
        "options": 'Enter options as JSON, e.g. [{"name":"Size","values":["S","M","L"]}]:',
    }
    prompt = prompts.get(field, "Enter new value:")
    await db.set_fsm(user_id, f"edit_{field}", {"product_id": product_id})
    await api.delete_message(chat_id, msg_id)
    await api.send_message(chat_id, prompt)


async def start_add_product(chat_id: int, user_id: int, msg_id: int):
    await db.set_fsm(user_id, "sell_name", {})
    await api.delete_message(chat_id, msg_id)
    await api.send_message(chat_id, "📦 Enter the product *name*:")


async def start_image_upload(chat_id: int, user_id: int, msg_id: int, product_id: int):
    await db.set_fsm(user_id, "sell_image", {"product_id": product_id, "count": 0})
    await api.delete_message(chat_id, msg_id)
    await api.send_message(
        chat_id,
        "📷 Send product images (up to 5). Send /done when finished.",
    )


async def deactivate(chat_id: int, user_id: int, msg_id: int, product_id: int):
    await db.deactivate_product(product_id)
    await api.delete_message(chat_id, msg_id)
    await api.send_message(chat_id, "🗑 Product deactivated.", kb.back_kb("sell:list:0"))


async def seller_orders(chat_id: int, user_id: int, msg_id: int):
    await api.delete_message(chat_id, msg_id)
    await api.send_message(chat_id, "📦 *My Orders*", kb.seller_orders_kb())


async def handle_text(chat_id: int, user_id: int, text: str, msg_id: int):
    """FSM handler for seller text inputs."""
    state, fdata = await db.get_fsm(user_id)

    if state == "sell_name":
        fdata["name"] = text
        await db.set_fsm(user_id, "sell_desc", fdata)
        await api.send_message(chat_id, "📝 Enter the product *description*:")

    elif state == "sell_desc":
        fdata["description"] = text
        await db.set_fsm(user_id, "sell_price", fdata)
        await api.send_message(chat_id, "💰 Enter the product *price* (number):")

    elif state == "sell_price":
        try:
            price = float(text.strip())
        except ValueError:
            await api.send_message(chat_id, "❌ Invalid price. Enter a number:")
            return
        fdata["price"] = price
        await db.set_fsm(user_id, "sell_category", fdata)
        await api.send_message(chat_id, "📁 Enter the product *category* (or type 'skip'):")

    elif state == "sell_category":
        fdata["category"] = "" if text.strip().lower() == "skip" else text.strip()
        await db.set_fsm(user_id, "sell_options", fdata)
        await api.send_message(
            chat_id,
            '⚙️ Enter product *options* as JSON (or type "skip"):\nExample: [{"name":"Size","values":["S","M","L"]}]',
        )

    elif state == "sell_options":
        options = []
        if text.strip().lower() != "skip":
            try:
                options = json.loads(text)
            except json.JSONDecodeError:
                await api.send_message(chat_id, "❌ Invalid JSON. Try again or type 'skip':")
                return

        user = await db.get_user(user_id)
        product_id = await db.add_product(
            seller_id=user["id"],
            name=fdata["name"],
            description=fdata["description"],
            price=fdata["price"],
            category=fdata.get("category", ""),
            options=options,
        )
        await db.clear_fsm(user_id)
        await api.send_message(
            chat_id,
            f"✅ Product *{fdata['name']}* created (ID: {product_id})!\n\nWant to upload images?",
            kb._inline_kb([
                [kb._btn("📷 Upload Images", f"sell:img:{product_id}")],
                [kb._btn("◀️ Seller Menu", "sell:menu")],
            ]),
        )

    # Edit fields
    elif state == "edit_name":
        await db.update_product(fdata["product_id"], name=text)
        await db.clear_fsm(user_id)
        await api.send_message(chat_id, "✅ Name updated!", kb.back_kb(f"sell:edit:{fdata['product_id']}"))

    elif state == "edit_price":
        try:
            price = float(text.strip())
        except ValueError:
            await api.send_message(chat_id, "❌ Invalid price. Enter a number:")
            return
        await db.update_product(fdata["product_id"], price=price)
        await db.clear_fsm(user_id)
        await api.send_message(chat_id, "✅ Price updated!", kb.back_kb(f"sell:edit:{fdata['product_id']}"))

    elif state == "edit_description":
        await db.update_product(fdata["product_id"], description=text)
        await db.clear_fsm(user_id)
        await api.send_message(chat_id, "✅ Description updated!", kb.back_kb(f"sell:edit:{fdata['product_id']}"))

    elif state == "edit_options":
        try:
            options = json.loads(text)
        except json.JSONDecodeError:
            await api.send_message(chat_id, "❌ Invalid JSON:")
            return
        await db.update_product(fdata["product_id"], options=options)
        await db.clear_fsm(user_id)
        await api.send_message(chat_id, "✅ Options updated!", kb.back_kb(f"sell:edit:{fdata['product_id']}"))


async def handle_photo(chat_id: int, user_id: int, file_id: str, msg_id: int):
    """Handle photo uploads during sell_image FSM state."""
    state, fdata = await db.get_fsm(user_id)
    if state != "sell_image":
        return

    product_id = fdata["product_id"]
    count = fdata.get("count", 0)

    if count >= 5:
        await api.send_message(chat_id, "⚠️ Maximum 5 images. Send /done to finish.")
        return

    await db.add_product_image(product_id, file_id)
    fdata["count"] = count + 1
    await db.set_fsm(user_id, "sell_image", fdata)
    await api.send_message(chat_id, f"📷 Image {count + 1}/5 saved. Send more or /done.")


async def handle_done(chat_id: int, user_id: int, msg_id: int):
    """Finish image upload."""
    state, fdata = await db.get_fsm(user_id)
    if state == "sell_image":
        await db.clear_fsm(user_id)
        await api.send_message(
            chat_id,
            f"✅ Images uploaded for product #{fdata['product_id']}!",
            kb.back_kb("sell:menu"),
        )
