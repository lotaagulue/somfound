"""HTTP Basic auth guard for the moderator queue — deliberately minimal for
an MVP demo (single shared credential, no user accounts/roles yet)."""

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from somfound.config import MODERATOR_PASSWORD, MODERATOR_USERNAME

_security = HTTPBasic()


def require_moderator(credentials: HTTPBasicCredentials = Depends(_security)) -> str:
    valid_user = secrets.compare_digest(credentials.username, MODERATOR_USERNAME)
    valid_pass = secrets.compare_digest(credentials.password, MODERATOR_PASSWORD)
    if not (valid_user and valid_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid moderator credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
