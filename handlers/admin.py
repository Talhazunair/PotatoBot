"""Admin panel — manage sellers, products, support tickets, disputes."""
import potato_api as api
import database as db
import keyboards as kb
from config import ADMIN_IDS, PRODUCTS_PER_PAGE


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def handle_callback(chat_id: int, user_id: int, data: str, msg_id: int):
    if not is_admin(user_id):
        await api.answer_callback(str(msg_id), "⛔ Access denied.")
        return

    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "menu":
        await admin_menu(chat_id, msg_id)
    elif action == "add_seller":
        await start_add_seller(chat_id, user_id, msg_id)
    elif action == "sellers":
        await list_sellers(chat_id, msg_id)
    elif action == "rm_seller":
        potato_id = int(parts[2])
        await remove_seller(chat_id, msg_id, potato_id)
    elif action == "seller_requests":
        await list_seller_requests(chat_id, msg_id)
    elif action == "review_req":
        req_id = int(parts[2])
        await review_seller_request(chat_id, msg_id, req_id)
    elif action == "approve_req":
        req_id = int(parts[2])
        await approve_seller_request(chat_id, msg_id, req_id)
    elif action == "reject_req":
        req_id = int(parts[2])
        await reject_seller_request(chat_id, msg_id, req_id)
    elif action == "products":
        page = int(parts[2]) if len(parts) > 2 else 0
        await list_all_products(chat_id, msg_id, page)
    elif action == "rm_prod":
        product_id = int(parts[2])
        await remove_product(chat_id, msg_id, product_id)
    elif action == "support":
        await list_tickets(chat_id, msg_id)
    elif action == "ticket":
        ticket_id = int(parts[2])
        await view_ticket(chat_id, msg_id, ticket_id)
    elif action == "close_ticket":
        ticket_id = int(parts[2])
        await close_ticket(chat_id, user_id, msg_id, ticket_id)
    elif action == "disputes":
        await list_disputes(chat_id, msg_id)
    elif action == "dispute_view":
        dispute_id = int(parts[2])
        await view_dispute(chat_id, msg_id, dispute_id)
    elif action == "resolve_dispute":
        dispute_id = int(parts[2])
        await resolve_dispute(chat_id, msg_id, dispute_id)


async def admin_menu(chat_id: int, msg_id: int):
    await api.delete_message(chat_id, msg_id)
    await api.send_message(chat_id, "🔧 *Admin Panel*", kb.admin_menu_kb())


async def start_add_seller(chat_id: int, user_id: int, msg_id: int):
    await db.set_fsm(user_id, "admin_add_seller", {})
    await api.delete_message(chat_id, msg_id)
    await api.send_message(chat_id, "Enter the Potato user ID of the new seller:")


async def list_sellers(chat_id: int, msg_id: int):
    sellers = await db.get_sellers()
    await api.delete_message(chat_id, msg_id)
    if not sellers:
        await api.send_message(chat_id, "No sellers registered.", kb.back_kb("adm:menu"))
        return
    await api.send_message(chat_id, "👥 *Sellers* (tap to remove)", kb.admin_sellers_kb(sellers))


async def remove_seller(chat_id: int, msg_id: int, potato_id: int):
    await db.set_user_role(potato_id, "buyer")
    await api.delete_message(chat_id, msg_id)
    await api.send_message(chat_id, f"✅ User {potato_id} removed as seller.", kb.back_kb("adm:sellers"))


# ── Seller Requests ────────────────────────────────────
async def list_seller_requests(chat_id: int, msg_id: int):
    requests = await db.get_pending_seller_requests()
    await api.delete_message(chat_id, msg_id)
    if not requests:
        await api.send_message(chat_id, "📝 No pending seller requests.", kb.back_kb("adm:menu"))
        return
    await api.send_message(
        chat_id,
        f"📝 *Pending Seller Requests* ({len(requests)})\n\nTap to review:",
        kb.admin_seller_requests_kb(requests),
    )


async def review_seller_request(chat_id: int, msg_id: int, req_id: int):
    req = await db.get_seller_request(req_id)
    if not req:
        await api.delete_message(chat_id, msg_id)
        await api.send_message(chat_id, "❌ Request not found.", kb.back_kb("adm:seller_requests"))
        return

    user = await db.get_user(req["potato_id"])
    name = user["first_name"] if user else "Unknown"

    text = (
        f"📝 *Seller Request #{req_id}*\n\n"
        f"👤 User: {name}\n"
        f"🆔 Potato ID: {req['potato_id']}\n"
        f"📅 Submitted: {req['created_at']}\n"
        f"Status: {req['status']}"
    )
    await api.delete_message(chat_id, msg_id)
    await api.send_message(chat_id, text, kb.admin_review_request_kb(req_id))


async def approve_seller_request(chat_id: int, msg_id: int, req_id: int):
    req = await db.get_seller_request(req_id)
    if not req:
        await api.delete_message(chat_id, msg_id)
        await api.send_message(chat_id, "❌ Request not found.", kb.back_kb("adm:seller_requests"))
        return

    await db.update_seller_request(req_id, "approved")
    await db.set_user_role(req["potato_id"], "seller")
    await api.delete_message(chat_id, msg_id)
    await api.send_message(
        chat_id,
        f"✅ User {req['potato_id']} approved as seller!",
        kb.back_kb("adm:seller_requests"),
    )

    # Notify the user
    await api.send_message(
        req["potato_id"],
        "🎉 *Congratulations!*\n\n"
        "Your seller application has been *approved!*\n"
        "You now have access to the Seller Dashboard.\n\n"
        "Send /start to see your updated menu!",
    )


async def reject_seller_request(chat_id: int, msg_id: int, req_id: int):
    req = await db.get_seller_request(req_id)
    if not req:
        await api.delete_message(chat_id, msg_id)
        await api.send_message(chat_id, "❌ Request not found.", kb.back_kb("adm:seller_requests"))
        return

    await db.update_seller_request(req_id, "rejected")
    await api.delete_message(chat_id, msg_id)
    await api.send_message(
        chat_id,
        f"❌ User {req['potato_id']} rejected.",
        kb.back_kb("adm:seller_requests"),
    )

    # Notify the user
    await api.send_message(
        req["potato_id"],
        "❌ Your seller application has been *rejected*.\n"
        "Contact support if you have questions.",
        kb.back_kb("menu:main"),
    )


async def list_all_products(chat_id: int, msg_id: int, page: int = 0):
    products = await db.list_products(page=page, limit=PRODUCTS_PER_PAGE, active_only=False)
    total = await db.count_products(active_only=False)
    await api.delete_message(chat_id, msg_id)
    if not products:
        await api.send_message(chat_id, "No products.", kb.back_kb("adm:menu"))
        return
    await api.send_message(
        chat_id,
        f"🗑 *Products* (Page {page + 1}) — tap to remove",
        kb.admin_products_kb(products, page, total),
    )


async def remove_product(chat_id: int, msg_id: int, product_id: int):
    await db.deactivate_product(product_id)
    await api.delete_message(chat_id, msg_id)
    await api.send_message(chat_id, f"✅ Product #{product_id} removed.", kb.back_kb("adm:products:0"))


async def list_tickets(chat_id: int, msg_id: int):
    tickets = await db.get_open_tickets()
    await api.delete_message(chat_id, msg_id)
    if not tickets:
        await api.send_message(chat_id, "📨 No open support tickets.", kb.back_kb("adm:menu"))
        return
    await api.send_message(chat_id, "📨 *Open Support Tickets*", kb.admin_tickets_kb(tickets))


async def view_ticket(chat_id: int, msg_id: int, ticket_id: int):
    ticket = await db.get_ticket(ticket_id)
    if not ticket:
        await api.delete_message(chat_id, msg_id)
        await api.send_message(chat_id, "❌ Ticket not found.", kb.back_kb("adm:support"))
        return

    await api.delete_message(chat_id, msg_id)
    text = (
        f"🎫 *Ticket #{ticket_id}*\n\n"
        f"From user: {ticket['user_id']}\n"
        f"Status: {ticket['status']}\n"
        f"Created: {ticket['created_at']}\n\n"
        f"Message:\n{ticket['message']}"
    )
    await api.send_message(chat_id, text, kb.admin_ticket_detail_kb(ticket_id))


async def close_ticket(chat_id: int, user_id: int, msg_id: int, ticket_id: int):
    ticket = await db.get_ticket(ticket_id)
    await db.close_ticket(ticket_id, reply="Completed by admin")
    await api.delete_message(chat_id, msg_id)
    await api.send_message(chat_id, f"✅ Ticket #{ticket_id} marked as completed.", kb.back_kb("adm:support"))

    # Notify the user
    if ticket:
        await api.send_message(
            ticket["user_id"],
            f"✅ Your support ticket #{ticket_id} has been resolved!",
            kb.back_kb("menu:main"),
        )


async def list_disputes(chat_id: int, msg_id: int):
    disputes = await db.get_all_disputes(status="open")
    await api.delete_message(chat_id, msg_id)
    if not disputes:
        await api.send_message(chat_id, "⚠️ No open disputes.", kb.back_kb("adm:menu"))
        return
    await api.send_message(chat_id, "⚠️ *Open Disputes*", kb.admin_disputes_kb(disputes))


async def view_dispute(chat_id: int, msg_id: int, dispute_id: int):
    dispute = await db.get_dispute(dispute_id)
    if not dispute:
        await api.delete_message(chat_id, msg_id)
        await api.send_message(chat_id, "❌ Dispute not found.", kb.back_kb("adm:disputes"))
        return

    product = await db.get_product(dispute["product_id"])
    product_name = product["name"] if product else "Unknown"

    text = (
        f"⚠️ *Dispute #{dispute_id}*\n\n"
        f"Order: #{dispute['order_id']}\n"
        f"Product: {product_name}\n"
        f"Reason: {dispute['reason']}\n"
        f"User: {dispute['user_id']}\n"
        f"Status: {dispute['status']}\n"
    )
    if dispute['message']:
        text += f"\nMessage:\n{dispute['message']}"

    await api.delete_message(chat_id, msg_id)
    await api.send_message(chat_id, text, kb.admin_dispute_detail_kb(dispute_id))


async def resolve_dispute(chat_id: int, msg_id: int, dispute_id: int):
    dispute = await db.get_dispute(dispute_id)
    await db.update_dispute_status(dispute_id, "resolved")
    await api.delete_message(chat_id, msg_id)
    await api.send_message(chat_id, f"✅ Dispute #{dispute_id} resolved.", kb.back_kb("adm:disputes"))

    # Notify user
    if dispute:
        await api.send_message(
            dispute["user_id"],
            f"✅ Your dispute #{dispute_id} has been resolved!",
            kb.back_kb("menu:main"),
        )


async def handle_text(chat_id: int, user_id: int, text: str, msg_id: int):
    """FSM handler for admin add-seller."""
    if not is_admin(user_id):
        return

    state, fdata = await db.get_fsm(user_id)
    if state == "admin_add_seller":
        try:
            target_id = int(text.strip())
        except ValueError:
            await api.send_message(chat_id, "❌ Invalid user ID. Enter a number:")
            return

        user = await db.get_user(target_id)
        if not user:
            await db.create_user(target_id, first_name="Seller")
        await db.set_user_role(target_id, "seller")
        await db.clear_fsm(user_id)
        await api.send_message(
            chat_id,
            f"✅ User {target_id} is now a seller!",
            kb.back_kb("adm:menu"),
        )
