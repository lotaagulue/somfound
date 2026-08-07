"""Absolute paths to static/template assets — computed from this file's own
location rather than the process's cwd, since that's not reliable on every
host (notably Vercel's serverless functions)."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
