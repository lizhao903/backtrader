"""Shared pytest configuration and fixtures for backtrader tests.

Provides a `datapath` fixture for resolving sample data file paths relative
to the repository-level ``datas/`` directory, so that newly authored tests
don't have to reimplement the legacy ``testcommon.getdata`` glue.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATAS_DIR = PROJECT_ROOT / "datas"

# Ensure ``backtrader`` (repo root) is importable when pytest runs from any cwd.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def datapath():
    """Return a callable that resolves filenames under ``datas/`` to abs paths."""

    def _inner(filename: str) -> str:
        return str(DATAS_DIR / filename)

    return _inner
