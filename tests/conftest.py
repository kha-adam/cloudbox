import os
from dotenv import load_dotenv

load_dotenv()

os.environ["STORAGE_DIR"] = "test_storage"
os.environ["DATABASE_TEST_URL"] = (
    "postgresql+psycopg://"
    f"{os.environ["POSTGRES_USER"]}:"
    f"{os.environ["POSTGRES_PASSWORD"]}"
    f"@localhost:5432/"
    f"{os.environ["POSTGRES_TEST_DB"]}"
)

from pathlib import Path

from app.database import Base, SessionLocal, engine
from app.models import File
import pytest

Base.metadata.create_all(bind=engine)

TEST_STORAGE_DIR = Path("test_storage")
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