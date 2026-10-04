"""Shared accessibility preferences for terminal UI components."""
from __future__ import annotations

import os


def motion_enabled(console) -> bool:
    setting = os.environ.get("ONE_CEDRIC_REDUCED_MOTION", "").strip().lower()
    if setting in {"1", "true", "yes", "on"}:
        return False
    if setting in {"0", "false", "no", "off"}:
        return bool(console.is_terminal)
    return bool(console.is_terminal)
