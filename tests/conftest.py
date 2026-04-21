from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.database import db
from backend.main import app


@pytest.fixture
def temp_db(tmp_path: Path, monkeypatch):
    test_db_path = tmp_path / "test_attendance.db"
    monkeypatch.setattr(db, "DB_PATH", str(test_db_path))
    return test_db_path


@pytest.fixture
def client(temp_db):
    with TestClient(app) as c:
        yield c
