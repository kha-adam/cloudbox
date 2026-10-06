import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_TEST_URL", (
    f"postgresql+psycopg://"
    f"{os.environ["POSTGRES_USER"]}:"
    f"{os.environ["POSTGRES_PASSWORD"]}@"
    f"localhost:5432/"
    f"{os.environ["POSTGRES_DB"]}"
    ),
)   

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)
class Base(DeclarativeBase):
    pass