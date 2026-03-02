import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
API_BASE: str = f"https://api.rct2008.com:8443/{BOT_TOKEN}"

COINREMITTER_API_KEY: str = os.getenv("COINREMITTER_API_KEY", "")
COINREMITTER_API_PASSWORD: str = os.getenv("COINREMITTER_API_PASSWORD", "")
COINREMITTER_BASE: str = "https://api.coinremitter.com/v1"

ADMIN_IDS: list[int] = [int(i) for i in os.getenv("ADMIN_IDS", "").split(",") if i.strip()]

WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "").strip().rstrip("/")
DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/bot")

PRODUCTS_PER_PAGE: int = 5
BOT_USERNAME: str = "marketplacebot"
