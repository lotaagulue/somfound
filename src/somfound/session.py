"""A lightweight, login-free anonymous session — just enough identity to
stop the same browser from spamming the confirm button on a report, without
any account system. Not tied to a phone number or anything identifying;
unlike `reporter_ref` (a hash of something the reporter typed), this is a
hash of a random token the server handed out, so it can't be linked back to
a person even in principle.
"""

import hashlib
import secrets

from fastapi import Request, Response

SESSION_COOKIE = "sf_session"
_COOKIE_MAX_AGE = 60 * 60 * 24 * 365 * 2  # 2 years


def get_session_hash(request: Request, response: Response) -> str:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        raw = secrets.token_urlsafe(24)
        response.set_cookie(
            SESSION_COOKIE,
            raw,
            max_age=_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
        )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
