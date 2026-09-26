import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("BID_DATABASE_URL", f"sqlite:///{DATA_DIR / 'app.db'}")

SECRET_KEY = os.getenv("BID_SECRET_KEY", "bid-system-dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8

PROJECT_STATUSES = ["draft", "published", "bidding", "evaluating", "awarded", "closed"]
SECTION_STATUSES = ["draft", "announced", "bidding", "evaluating", "awarded", "failed", "closed"]
BID_STATUSES = ["draft", "submitted", "under_review", "qualified", "disqualified", "won", "lost"]
ESCROW_STATUSES = ["unpaid", "paid", "returned", "forfeited"]
