"""Optional outbound SMS via Africa's Talking — for a real deployment only.
The demo doesn't need this at all (see /sms/simulate); it exists so a real
pilot can wire up actual confirmation replies later with production
credentials. If no API key is configured, or the call fails, we just log it
and move on rather than failing the inbound webhook.
"""

import logging

import httpx

from somfound.config import AT_API_KEY, AT_BASE_URL, AT_USERNAME

logger = logging.getLogger("somfound.sms")


def send_confirmation(to_phone: str, message: str) -> bool:
    if not AT_API_KEY:
        logger.info("AT_API_KEY not set — skipping outbound SMS to %s: %s", to_phone, message)
        return False

    try:
        response = httpx.post(
            f"{AT_BASE_URL}/version1/messaging",
            headers={
                "apiKey": AT_API_KEY,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            data={"username": AT_USERNAME, "to": to_phone, "message": message},
            timeout=10,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPError:
        logger.exception("Failed to send SMS confirmation to %s", to_phone)
        return False
