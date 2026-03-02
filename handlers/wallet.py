"""Wallet — balance, deposit, withdraw."""
import potato_api as api
import database as db
import keyboards as kb
import coinremitter


async def handle_callback(chat_id: int, user_id: int, data: str, msg_id: int):
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "view":
        await view_wallet(chat_id, user_id, msg_id)
    elif action == "deposit":
        await deposit(chat_id, user_id, msg_id)
    elif action == "withdraw":
        await start_withdraw(chat_id, user_id, msg_id)
    elif action == "confirm_withdraw":
        await confirm_withdraw(chat_id, user_id, msg_id)


async def view_wallet(chat_id: int, user_id: int, msg_id: int):
    user = await db.get_user(user_id)
    wallet = await db.get_wallet(user["id"])

    await api.delete_message(chat_id, msg_id)
    text = (
        f"💰 *My Wallet*\n\n"
        f"Balance: *${wallet['balance']:.2f} USDT*\n"
    )
    if wallet.get("deposit_address"):
        text += f"\nDeposit Address:\n`{wallet['deposit_address']}`"

    await api.send_message(chat_id, text, kb.wallet_kb())


async def deposit(chat_id: int, user_id: int, msg_id: int):
    user = await db.get_user(user_id)
    wallet = await db.get_wallet(user["id"])

    await api.delete_message(chat_id, msg_id)

    if wallet.get("deposit_address"):
        text = f"📥 *Deposit USDT*\n\nSend USDT to:\n`{wallet['deposit_address']}`"
    else:
        result = await coinremitter.create_address(label=f"user_{user_id}")
        if result.get("success"):
            addr = result["data"]["address"]
            await db.set_wallet_deposit_address(user["id"], addr)
            text = f"📥 *Deposit USDT*\n\nSend USDT to:\n`{addr}`"
        else:
            text = "❌ Could not generate deposit address. Please try again later."

    await api.send_message(chat_id, text, kb.back_kb("wal:view"))


async def start_withdraw(chat_id: int, user_id: int, msg_id: int):
    user = await db.get_user(user_id)
    wallet = await db.get_wallet(user["id"])

    await api.delete_message(chat_id, msg_id)

    if wallet["balance"] <= 0:
        await api.send_message(chat_id, "❌ Insufficient balance.", kb.back_kb("wal:view"))
        return

    await db.set_fsm(user_id, "withdraw_address", {"balance": wallet["balance"]})
    await api.send_message(
        chat_id,
        f"📤 *Withdraw USDT*\n\nAvailable: *${wallet['balance']:.2f}*\n\nEnter the USDT address to withdraw to:",
    )


async def handle_text(chat_id: int, user_id: int, text: str, msg_id: int):
    state, fdata = await db.get_fsm(user_id)

    if state == "withdraw_address":
        fdata["address"] = text.strip()
        await db.set_fsm(user_id, "withdraw_amount", fdata)
        await api.send_message(
            chat_id,
            f"💰 Enter the amount to withdraw (max ${fdata['balance']:.2f}):",
        )
    elif state == "withdraw_amount":
        try:
            amount = float(text.strip())
        except ValueError:
            await api.send_message(chat_id, "❌ Invalid amount. Enter a number:")
            return

        if amount <= 0 or amount > fdata.get("balance", 0):
            await api.send_message(chat_id, f"❌ Amount must be between 0 and ${fdata['balance']:.2f}:")
            return

        fdata["amount"] = amount
        await db.set_fsm(user_id, "withdraw_confirm", fdata)
        await api.send_message(
            chat_id,
            f"📤 *Confirm Withdrawal*\n\n"
            f"Address: `{fdata['address']}`\n"
            f"Amount: *${amount:.2f} USDT*\n\n"
            f"Confirm?",
            kb._inline_kb([
                [kb._btn("✅ Confirm", "wal:confirm_withdraw")],
                [kb._btn("❌ Cancel", "wal:view")],
            ]),
        )


async def confirm_withdraw(chat_id: int, user_id: int, msg_id: int):
    state, fdata = await db.get_fsm(user_id)
    if state != "withdraw_confirm":
        await api.answer_callback(str(msg_id), "❌ Invalid state.")
        return

    user = await db.get_user(user_id)
    address = fdata["address"]
    amount = fdata["amount"]

    result = await coinremitter.withdraw(address, amount)

    await api.delete_message(chat_id, msg_id)

    if result.get("success"):
        await db.update_wallet_balance(user["id"], -amount)
        await db.clear_fsm(user_id)
        await api.send_message(
            chat_id,
            f"✅ Withdrawal of *${amount:.2f} USDT* sent to `{address}`!",
            kb.back_kb("wal:view"),
        )
    else:
        await db.clear_fsm(user_id)
        await api.send_message(
            chat_id,
            "❌ Withdrawal failed. Please try again later.",
            kb.back_kb("wal:view"),
        )
