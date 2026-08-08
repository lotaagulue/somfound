from fastapi.testclient import TestClient

from somfound.main import app
from somfound.vercel_compat import RestoreOriginalPathMiddleware

wrapped_client = TestClient(RestoreOriginalPathMiddleware(app))


def test_original_path_query_param_is_restored():
    # Simulates exactly what Vercel's rewrite delivers: every request lands
    # at the function's own address with the real path tacked on as a query param.
    response = wrapped_client.get("/api/index", params={"__path": "/report"})
    assert response.status_code == 200
    assert "Report something" in response.text


def test_other_query_params_survive_alongside_path_restoration():
    response = wrapped_client.get(
        "/api/index", params={"__path": "/api/reports", "urgency": "critical"}
    )
    assert response.status_code == 200
    reports = response.json()
    assert all(r["urgency"] == "critical" for r in reports)


def test_missing_path_param_falls_through_unchanged():
    # No __path param at all: behaves like the unwrapped app would for
    # whatever path was actually requested (local dev / Render never hit
    # through this middleware in the first place, but this proves it's a
    # no-op rather than breaking normal requests).
    response = wrapped_client.get("/api/index")
    assert response.status_code == 404
