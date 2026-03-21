import shutil
import uuid
from pathlib import Path

import pytest


@pytest.fixture
def tmp_path() -> Path:
    root = Path.cwd() / ".tmp_test_cli"
    root.mkdir(exist_ok=True)
    path = root / uuid.uuid4().hex
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
