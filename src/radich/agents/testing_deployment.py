"""Explicitly opt-in M17.5 simulated A01 on an isolated testing deployment.

This is NOT the production app, does not enable external tools or LLMs,
and does not change radich.deployment:build_app (the M15 demo).
"""
from __future__ import annotations

import os

from .service import build_m17_app


def build_app():
    """ASGI factory enabled only by the dedicated Compose testing profile."""
    if os.environ.get("RADICH_A01_TESTING_ENABLED") != "yes":
        raise RuntimeError("A01 testing deployment is disabled by default")

    dsn = os.environ.get("DATABASE_URL", "")
    api_key = os.environ.get("RADICH_API_KEY", "")
    if not dsn or not api_key:
        raise RuntimeError("DATABASE_URL and RADICH_API_KEY are required")

    # This grant is server-side and limited to the offline text.normalize skill.
    # HTTP callers cannot choose an agent, grant permission or invoke other tools.
    return build_m17_app(dsn=dsn, api_key=api_key, grant_skill=True)
