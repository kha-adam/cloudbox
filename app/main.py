from fastapi import FastAPI
from sqlalchemy import text

from app.database import Base, engine
from app.models import File
from app.routes import router

app = FastAPI(title="CloudBox")

Base.metadata.create_all(bind=engine)

app.include_router(router)

@app.get("/health")
def health_check():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "database": "ok",
    }