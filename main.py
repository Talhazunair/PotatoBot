"""FastAPI entry point — webhook receiver + long-polling fallback."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import database as db
import potato_api as api
import coinremitter
from config import BOT_TOKEN, WEBHOOK_URL
import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ────────────────────────────────────
    await db.init_db()
    log.info("Database initialized")

    if WEBHOOK_URL:
        url = f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}"
        result = await api.set_webhook(url)
        log.info("Webhook set: %s", result)
    else:
        await api.del_webhook()
        app.state.polling = True
        asyncio.create_task(_poll_loop())
        log.info("Long-polling started")

    yield

    # ── Shutdown ───────────────────────────────────
    app.state.polling = False


app = FastAPI(title="Potato Marketplace Bot", lifespan=lifespan)


# ── Health check ──────────────────────────────────────
@app.get("/")
async def health():
    return {"status": "ok"}


# ── Webhook endpoint ──────────────────────────────────
@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    if token != BOT_TOKEN:
        return JSONResponse({"error": "invalid token"}, status_code=403)
    try:
        import json as _json
        body = await request.body()
        log.info("Webhook received: %s", body[:500])
        payload = _json.loads(body)
        # Potato sends updates as a JSON array
        updates = payload if isinstance(payload, list) else [payload]
        for update in updates:
            asyncio.create_task(router.dispatch(update))
    except Exception:
        log.exception("Error processing webhook")
    return {"ok": True}



# ── CoinRemitter payment notification ─────────────────
@app.post("/payment-notify")
async def payment_notify(request: Request):
    """Receive payment notifications from CoinRemitter."""
    data = await request.json()
    log.info("Payment notification: %s", data)

    invoice_id = str(data.get("id", data.get("invoice_id", "")))
    status = data.get("status", "")

    if not invoice_id:
        return {"ok": False}

    # Find order by invoice_id
    conn = db.db()
    cur = await conn.execute("SELECT * FROM orders WHERE invoice_id=?", (invoice_id,))
    order = await cur.fetchone()

    if not order:
        log.warning("No order found for invoice %s", invoice_id)
        return {"ok": False}

    order = dict(order)

    if status in ("Paid", "paid", "confirmed"):
        await db.update_order_status(order["id"], "preparing")
        # Notify buyer
        await api.send_message(
            order["user_id"],
            f"✅ *Payment confirmed for Order #{order['id']}!*\n\n"
            f"Your order is now being prepared.",
        )
        log.info("Order #%d marked as preparing", order["id"])

    return {"ok": True}


# ── Long-polling loop ─────────────────────────────────
async def _poll_loop():
    offset = None
    while getattr(app.state, "polling", False):
        try:
            updates = await api.get_updates(offset)
            for u in updates:
                offset = u["update_id"] + 1
                asyncio.create_task(router.dispatch(u))
        except Exception:
            log.exception("Polling error")
            await asyncio.sleep(2)
        await asyncio.sleep(0.5)


# ── Run directly ──────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
