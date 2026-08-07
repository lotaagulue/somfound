"""Environment must be configured *before* anything under somfound is
imported, since db.py/config.py read env vars at import time."""

import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mktemp(suffix='.db')}")
os.environ.setdefault("MODERATOR_USERNAME", "moderator")
os.environ.setdefault("MODERATOR_PASSWORD", "test-pass")

import pytest
from fastapi.testclient import TestClient

from somfound.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def moderator_auth():
    return (os.environ["MODERATOR_USERNAME"], os.environ["MODERATOR_PASSWORD"])
