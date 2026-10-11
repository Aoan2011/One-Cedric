"""One Cedric - An AI agent for beginners（由 Aoan2011 主持开发，GPL-3.0）。"""
from ._version import __release_name__, __version__
from .cli import main
from .config import (
    PROJECT_AUTHOR, PROJECT_LICENSE, PROJECT_NAME, PROJECT_REPO,
)

__author__ = PROJECT_AUTHOR
__license__ = PROJECT_LICENSE
__all__ = ["main", "__version__", "__release_name__", "__author__", "__license__"]
