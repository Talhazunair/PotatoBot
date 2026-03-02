import httpx
import logging
from config import API_BASE

log = logging.getLogger("potato_api")

_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30, verify=False)
    return _client


async def _post(method: str, payload: dict | None = None) -> dict:
    url = f"{API_BASE}/{method}"
    resp = await client().post(url, json=payload or {})
    data = resp.json()
    if not data.get("ok"):
        log.error("API error %s: %s", method, data.get("description", data))
    return data


async def _post_form(method: str, files: dict, data: dict | None = None) -> dict:
    url = f"{API_BASE}/{method}"
    resp = await client().post(url, data=data or {}, files=files)
    result = resp.json()
    if not result.get("ok"):
        log.error("API error %s: %s", method, result.get("description", result))
    return result


# ── Core Methods ───────────────────────────────────────
async def send_message(chat_id: int, text: str, reply_markup: dict | None = None) -> dict:
    payload: dict = {"chat_type": 1, "chat_id": chat_id, "text": text, "markdown": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return await _post("sendTextMessage", payload)


async def send_photo(chat_id: int, photo_bytes: bytes, filename: str = "photo.jpg",
                     caption: str = "", reply_markup: dict | None = None) -> dict:
    data: dict = {"chat_type": "1", "chat_id": str(chat_id)}
    if caption:
        data["caption"] = caption
    if reply_markup:
        import json
        data["reply_markup"] = json.dumps(reply_markup)
    files = {"photo": (filename, photo_bytes, "image/jpeg")}
    return await _post_form("sendPhoto", files=files, data=data)


async def send_photo_by_id(chat_id: int, file_id: str, caption: str = "",
                           reply_markup: dict | None = None) -> dict:
    payload: dict = {"chat_type": 1, "chat_id": chat_id, "photo": file_id}
    if caption:
        payload["caption"] = caption
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return await _post("sendPhoto", payload)


async def edit_message(chat_id: int, message_id: int, text: str,
                       reply_markup: dict | None = None) -> dict:
    payload: dict = {"chat_type": 1, "chat_id": chat_id,
                     "message_id": message_id, "text": text, "markdown": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return await _post("editMessageText", payload)


async def delete_message(chat_id: int, message_id: int) -> dict:
    return await _post("deleteMessage", {
        "chat_type": 1, "chat_id": chat_id, "message_id": message_id,
    })


async def answer_callback(callback_id: str, text: str = "", show_alert: bool = False) -> dict:
    payload: dict = {"inline_message_id": callback_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = show_alert
    return await _post("answerCallbackQuery", payload)


async def get_updates(offset: int | None = None) -> list[dict]:
    payload: dict = {}
    if offset is not None:
        payload["offset"] = offset
    data = await _post("getUpdates", payload)
    return data.get("result", [])


async def set_webhook(url: str) -> dict:
    return await _post("setWebhook", {"url": url})


async def del_webhook() -> dict:
    resp = await client().get(f"{API_BASE}/delWebhook")
    return resp.json()
