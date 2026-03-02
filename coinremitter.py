import httpx
import logging
from config import COINREMITTER_API_KEY, COINREMITTER_API_PASSWORD, COINREMITTER_BASE

log = logging.getLogger("coinremitter")

_client: httpx.AsyncClient | None = None

HEADERS = {
    "x-api-key": COINREMITTER_API_KEY,
    "x-api-password": COINREMITTER_API_PASSWORD,
    "Accept": "application/json",
}


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30, headers=HEADERS)
    return _client


async def _post(endpoint: str, data: dict | None = None) -> dict:
    url = f"{COINREMITTER_BASE}{endpoint}"
    resp = await client().post(url, data=data or {})
    result = resp.json()
    if not result.get("success"):
        log.error("CoinRemitter error %s: %s", endpoint, result)
    return result


async def create_address(label: str = "") -> dict:
    return await _post("/wallet/address/create", {"label": label} if label else {})


async def create_invoice(amount: float, description: str = "",
                         notify_url: str = "", expiry_minutes: int = 1440) -> dict:
    payload: dict = {"amount": str(amount)}
    if description:
        payload["description"] = description
    if notify_url:
        payload["notify_url"] = notify_url
    if expiry_minutes != 1440:
        payload["expiry_time_in_minutes"] = str(expiry_minutes)
    return await _post("/invoice/create", payload)


async def get_invoice(invoice_id: str) -> dict:
    return await _post("/invoice/get", {"invoice_id": invoice_id})


async def get_balance() -> dict:
    return await _post("/wallet/balance")


async def withdraw(address: str, amount: float) -> dict:
    return await _post("/wallet/withdraw", {"address": address, "amount": str(amount)})


async def get_transaction(tx_id: str) -> dict:
    return await _post("/wallet/transaction/get", {"id": tx_id})
