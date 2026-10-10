"""Pytest shared test fixtures and configuration."""

import os
from pathlib import Path
from typing import Generator

# Ensure SQLite is used during test suite execution BEFORE app modules load
os.environ["DATABASE_URL"] = "sqlite:///test_suite.db"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
import app.database as db_module
from app.database import Base, engine as db_engine, get_db
from app.main import create_app
from app.models import Certificate, Job


@pytest.fixture(scope="session")
def engine():
    """Session-scoped database engine: creates tables once, drops at end."""
    Base.metadata.drop_all(bind=db_engine)
    Base.metadata.create_all(bind=db_engine)
    yield db_engine
    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()
    db_path = Path("test_suite.db")
    if db_path.exists():
        try:
            db_path.unlink()
        except OSError:
            pass


@pytest.fixture(scope="session")
def _session_factory(engine):
    """Session-scoped sessionmaker bound to the test engine."""
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


@pytest.fixture
def db(_session_factory) -> Generator[Session, None, None]:
    """Function-scoped database session with automatic teardown after each test."""
    session = _session_factory()
    try:
        yield session
    finally:
        session.rollback()
        # Clean tables after each test so tests stay isolated
        session.query(Certificate).delete()
        session.query(Job).delete()
        session.commit()
        session.close()


@pytest.fixture
def client(_session_factory, db, tmp_path) -> Generator[TestClient, None, None]:
    """TestClient fixture with isolated database and throwaway file storage."""
    # Point certificate storage to pytest's tmp_path
    original_storage = settings.storage_dir
    settings.storage_dir = str(tmp_path)

    app = create_app()

    def override_get_db():
        session = _session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    # Restore originals
    app.dependency_overrides.clear()
    settings.storage_dir = original_storage
