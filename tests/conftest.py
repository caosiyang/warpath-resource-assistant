from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TEST_DIR = Path(tempfile.mkdtemp(prefix="warpath-test-"))
os.environ["WARPATH_DB"] = str(_TEST_DIR / "test.db")
os.environ["WARPATH_SEED"] = "0"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client


def pytest_sessionfinish(session, exitstatus):  # noqa: ANN001
    import shutil

    shutil.rmtree(_TEST_DIR, ignore_errors=True)
