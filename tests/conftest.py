import os
from pathlib import Path
import pytest
from dotenv import load_dotenv

load_dotenv(".env.test", override=True)

from alembic import command
from alembic.config import Config

from pathlib import Path

from app.database import Base, SessionLocal, engine
from app.models import File
from app.config import settings

def run_migrations():
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")

TEST_STORAGE_DIR = Path(settings.storage_dir)
TEST_STORAGE_DIR.mkdir(exist_ok=True)

def clean_test_data():
    db = SessionLocal()

    try:
        db.query(File).delete()
        db.commit()
    finally:
        db.close()

    for path in TEST_STORAGE_DIR.iterdir():
        if path.name != ".gitkeep" and path.is_file():
            path.unlink()


@pytest.fixture(autouse=True)
def clean_test_data_fixture():
    
    clean_test_data()

    yield

    clean_test_data()