"""Environment-driven settings. Everything has a workable demo default."""

import os

# Moderator queue login (HTTP Basic). Change these via env vars before any
# real deployment — the defaults exist only so the demo runs out of the box.
MODERATOR_USERNAME = os.environ.get("MODERATOR_USERNAME", "moderator")
MODERATOR_PASSWORD = os.environ.get("MODERATOR_PASSWORD", "somfound-demo")

# Africa's Talking (SMS gateway). Sandbox is free — https://account.africastalking.com/ .
# Leave unset to still accept/parse inbound SMS; outbound confirmation replies
# are simply skipped (logged) rather than failing the request.
AT_USERNAME = os.environ.get("AT_USERNAME", "sandbox")
AT_API_KEY = os.environ.get("AT_API_KEY", "")
AT_BASE_URL = os.environ.get(
    "AT_BASE_URL",
    "https://api.sandbox.africastalking.com" if AT_USERNAME == "sandbox" else "https://api.africastalking.com",
)
