"""One Cedric - An AI agent for beginners（由 Aoan2011 主持开发，GPL-3.0）。"""
from .cli import main
from .config import (
    PROJECT_AUTHOR, PROJECT_LICENSE, PROJECT_NAME, PROJECT_REPO,
)

__version__ = "0.17.0"
__author__ = PROJECT_AUTHOR
__license__ = PROJECT_LICENSE
__all__ = ["main", "__version__", "__author__", "__license__"]