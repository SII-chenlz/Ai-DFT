"""REST input-card domain: catalogs, renderer and independent validator."""

import sys

# tomllib is part of the standard library since Python 3.11; on older
# interpreters the API-compatible tomli backport is used instead. mypy only
# checks the branch matching its target python_version.
if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python < 3.11
    import tomli as tomllib

__all__ = ["tomllib"]
