import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "portal.db")

SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")
PORT = int(os.environ.get("PORT", 5000))

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-me")

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:5000").rstrip("/")
VENUE_NAME = os.environ.get("VENUE_NAME", "nosplash.dog")

NDS_ENABLE_LIVE_GRANT = os.environ.get("NDS_ENABLE_LIVE_GRANT", "false").lower() == "true"
NDSCTL_PATH = os.environ.get("NDSCTL_PATH", "/usr/bin/ndsctl")

# ---------------------------------------------------------------------------
# Access tiers. Durations are in minutes for ndsctl; kbits/s for rate limits.
# Edit prices/durations/throttle rates here — nowhere else in the codebase.
# ---------------------------------------------------------------------------
TIERS = {
    1: {
        "key": "code",
        "label": "Tag 1 — Access Code",
        "subtitle": "Promo, staff, or private access",
        "price_cents": 0,
        "default_duration_minutes": 4 * 60,   # fallback if a code has no duration set
        "download_kbits": 4000,
        "upload_kbits": 1000,
        "requires_code": True,
        "requires_payment": False,
    },
    2: {
        "key": "half_day",
        "label": "Tag 2 — 12 Hour Pass",
        "subtitle": "A half day on the network",
        "price_cents": 1000,
        "default_duration_minutes": 12 * 60,
        "download_kbits": 4000,
        "upload_kbits": 1000,
        "requires_code": False,
        "requires_payment": True,
    },
    3: {
        "key": "full_stay",
        "label": "Tag 3 — 72 Hour Pass",
        "subtitle": "The full three-day run",
        "price_cents": 3500,
        "default_duration_minutes": 72 * 60,
        "download_kbits": 4000,
        "upload_kbits": 1000,
        "requires_code": False,
        "requires_payment": True,
    },
}

# Bandwidth caps above are deliberately modest (≈4 Mbps down / 1 Mbps up).
# This is a blunt instrument, not stream detection — see README "About the
# throttling" section for what this does and doesn't do, and for the optional
# DNS-blackhole approach to knock out major streaming domains outright.

MIN_AGE = 13  # adjust to your venue's policy; see README legal notes
