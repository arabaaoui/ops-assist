import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # lets tests import contract.py


@pytest.fixture
def incidents_dir() -> Path:
    return ROOT / "src" / "ops_assist" / "data" / "incidents"
