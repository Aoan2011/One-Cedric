"""Packaging, version and dependency-declaration invariants.

These catch the class of bug that previously shipped: the project declared
``docx``/``pptx``/``bs4``/``readability`` (wrong PyPI distribution names),
mixed lint tools into the runtime requirements, and reported two different
versions from ``pyproject.toml`` and the package.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]

PYPROJECT = REPO_ROOT / "pyproject.toml"
REQUIREMENTS = REPO_ROOT / "requirements.txt"
REQUIREMENTS_DEV = REPO_ROOT / "requirements-dev.txt"

#: Distribution names that are either the wrong package or actively conflict
#: with the correct one. Import name -> correct distribution.
FORBIDDEN_DISTRIBUTIONS = {
    "docx": "python-docx",          # legacy package shadows python-docx's module
    "pptx": "python-pptx",
    "bs4": "beautifulsoup4",        # bs4 is an empty stub on PyPI
    "readability": "readability-lxml",
    "msoffcrypto": "msoffcrypto-tool",
    "opencv-python": "opencv-contrib-python",  # both ship cv2
    "pygetwindow-legacy": "PyGetWindow",
    "opencc": "OpenCC",
    "PyYAML": "PyYAML",             # canonical capitalisation
}

#: Tools that must never be a runtime dependency.
DEV_ONLY = {"pytest", "pytest-cov", "ruff", "mypy", "black", "twine", "build"}


def _load_pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _requirement_names(path: Path) -> set[str]:
    """Extract the bare distribution names from a requirements file."""
    names: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name = re.split(r"[<>=!~\[;]", line, maxsplit=1)[0].strip()
        if name:
            names.add(name)
    return names


def test_pyproject_parses():
    data = _load_pyproject()
    assert data["project"]["name"] == "one-cedric"
    assert data["project"]["requires-python"].startswith(">=3.10")


def test_version_has_a_single_source():
    """pyproject must read the version from the package, not duplicate it."""
    data = _load_pyproject()
    assert "version" not in data["project"], (
        "pyproject.toml declares a static version; it must use "
        "[tool.setuptools.dynamic] so _version.py stays the single source")
    assert data["project"]["dynamic"] == ["version"]
    attr = data["tool"]["setuptools"]["dynamic"]["version"]["attr"]
    assert attr == "one_cedric._version.__version__"

    from one_cedric import __version__ as pkg_version
    from one_cedric import config
    from one_cedric._version import __release_name__
    from one_cedric._version import __version__ as leaf_version

    assert leaf_version, "_version.__version__ must not be empty"
    assert pkg_version == leaf_version
    assert leaf_version == config.PROJECT_VERSION
    assert __release_name__ == config.BETA_VERSION


def test_version_module_has_no_imports():
    """_version.py must stay import-free so it can be read without cycles."""
    import ast

    source = (REPO_ROOT / "one_cedric" / "_version.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module in {"__future__"}, (
                f"_version.py must not import {node.module}; it has to be "
                f"readable by setuptools and by config.py without cycles")
        elif isinstance(node, ast.Import):
            names = ", ".join(a.name for a in node.names)
            raise AssertionError(f"_version.py must not import {names}")


def test_declared_packages_exist_on_disk():
    data = _load_pyproject()
    for pkg in data["tool"]["setuptools"]["packages"]:
        path = REPO_ROOT / Path(*pkg.split("."))
        assert path.is_dir(), f"declared package {pkg} has no directory"
        assert (path / "__init__.py").is_file(), f"{pkg} lacks __init__.py"


def test_runtime_requirements_avoid_wrong_distributions():
    names = _requirement_names(REQUIREMENTS)
    wrong = {n for n in names if n in FORBIDDEN_DISTRIBUTIONS
             and FORBIDDEN_DISTRIBUTIONS[n] != n}
    assert not wrong, (
        f"requirements.txt declares the wrong distribution name(s) {sorted(wrong)}; "
        f"use {[FORBIDDEN_DISTRIBUTIONS[n] for n in sorted(wrong)]}")


def test_runtime_requirements_exclude_dev_tools():
    names = _requirement_names(REQUIREMENTS)
    leaked = names & DEV_ONLY
    assert not leaked, f"dev-only tools in runtime requirements: {sorted(leaked)}"


def test_dev_requirements_contain_test_tooling():
    names = _requirement_names(REQUIREMENTS_DEV)
    assert {"pytest", "ruff"} <= names


def test_all_extra_covers_core_runtime():
    """`pip install -e .[all]` must include everything requirements.txt lists."""
    data = _load_pyproject()
    all_extra = {re.split(r"[<>=!~\[]", d, maxsplit=1)[0].lower()
                 for d in data["project"]["optional-dependencies"]["all"]}
    runtime = {n.lower() for n in _requirement_names(REQUIREMENTS)}
    # Core deps live in `dependencies`, not in `all`, so only compare the
    # optional ones that are declared in both places.
    missing = {
        n for n in runtime - all_extra
        if n not in {"requests", "rich", "readchar", "alive-progress",
                     "fastapi", "uvicorn"}
    }
    assert not missing, f"optional deps missing from the [all] extra: {sorted(missing)}"


@pytest.mark.parametrize("module", [
    "one_cedric",
    "one_cedric._version",
    "one_cedric.config",
    "one_cedric.tools",
    "one_cedric.tools.schema",
    "one_cedric.storage",
])
def test_core_modules_import(module):
    __import__(module)
    assert module in sys.modules
