import os
import pytest
import shutil
from pathlib import Path
from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv(".env.test", override=True)

from alembic import command
from alembic.config import Config

from pathlib import Path

from app.database import Base, SessionLocal, engine
from app.models import File, User, UploadSession
from app.config import settings
from app.main import app


client = TestClient(app, raise_server_exceptions=False)

def run_migrations():
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")

TEST_STORAGE_DIR = Path(settings.storage_dir)
TEST_STORAGE_DIR.mkdir(exist_ok=True)

def clean_test_data():
    db = SessionLocal()

    try:
        db.query(UploadSession).delete()
        db.query(File).delete()
        db.query(User).delete()
        db.commit()
    finally:
        db.close()

    for path in TEST_STORAGE_DIR.iterdir():
        if path.name == ".gitkeep":
            continue

        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


@pytest.fixture(autouse=True)
def clean_test_data_fixture():
    
    clean_test_data()

    yield

    clean_test_data()