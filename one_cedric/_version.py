"""Single source of truth for the project version.

This module intentionally has **no imports** so that any other module
(including ``config`` and ``__init__``) can read the version without
creating an import cycle, and so that ``setuptools`` can resolve it
statically at build time.

Keep ``__version__`` in sync with the release; ``pyproject.toml`` reads it
via ``[tool.setuptools.dynamic]``.
"""
from __future__ import annotations

#: PEP 440 version reported by ``python -m one_cedric --version`` and
#: published to PyPI.
__version__ = "0.17.0"

#: Human-facing release name shown in the UI and the banner.
__release_name__ = "Public Beta I"

__all__ = ["__version__", "__release_name__"]
