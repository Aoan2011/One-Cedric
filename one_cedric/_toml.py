"""Single import point for TOML parsing on every supported interpreter.

Python 3.11 moved ``tomllib`` into the stdlib; on 3.10 the pure-Python
backport ``tomli`` (declared in requirements.txt) takes its place.
Before this shim existed, every module rolled its own
``tomllib = None`` fallback and silently no-op'd every TOML read - on
py3.10 a config round trip then dropped all custom values, which is
exactly what CI caught.

The ``None`` exit remains only as a safety net for environments that
skip requirements.txt entirely; missing optional packages are not
fatal in this app.
"""

try:  # Python >= 3.11 (stdlib)
    import tomllib
except ModuleNotFoundError:  # Python 3.10: the backport
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None
