"""Entry point for Vercel's Python runtime.

Vercel builds each file under /api into its own serverless function and, for
Python, auto-wraps a module-level `app` ASGI callable. `vercel.json` rewrites
every path to this one function (with the original path passed through as a
query param — see `somfound.vercel_compat` for why that's necessary) so the
whole FastAPI app (routing, static files, templates) is served from a single
deployment.
"""

import sys
from pathlib import Path

# The `somfound` package lives under src/, which isn't on sys.path by default
# in Vercel's build — add it explicitly rather than relying on an install step.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from somfound.main import app as _app  # noqa: E402
from somfound.vercel_compat import RestoreOriginalPathMiddleware  # noqa: E402

app = RestoreOriginalPathMiddleware(_app)
