import os
import tempfile
from pathlib import Path

_TEST_DB = Path(tempfile.mkdtemp(prefix="bid_test_")) / "test.db"
os.environ["BID_DATABASE_URL"] = f"sqlite:///{_TEST_DB}"

import pytest

import app.models  # noqa: F401  确保所有模型注册到 Base.metadata
from app.core.database import Base, SessionLocal, engine


@pytest.fixture(autouse=True)
def _fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db(_fresh_db):
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
