"""Environment-driven settings. Everything has a workable demo default."""

import os

# Moderator queue login (HTTP Basic). Change these via env vars before any
# real deployment — the defaults exist only so the demo runs out of the box.
MODERATOR_USERNAME = os.environ.get("MODERATOR_USERNAME", "moderator")
MODERATOR_PASSWORD = os.environ.get("MODERATOR_PASSWORD", "somfound-demo")

# Africa's Talking (SMS gateway) — for a real deployment only, not the demo.
# Their free sandbox has been deprecated, so the demo no longer depends on it
# at all (see /sms/simulate). Leave these unset to still accept/parse inbound
# SMS at /sms/inbound; outbound confirmation replies are simply skipped
# (logged) rather than failing the request. Fill in real production
# credentials here only once there's an actual pilot deployment.
AT_USERNAME = os.environ.get("AT_USERNAME", "")
AT_API_KEY = os.environ.get("AT_API_KEY", "")
AT_BASE_URL = os.environ.get("AT_BASE_URL", "https://api.africastalking.com")
