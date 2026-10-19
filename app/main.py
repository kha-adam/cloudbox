from fastapi import FastAPI
from sqlalchemy import text

from app.database import engine
from app.middleware import RequestBodyLimitMiddleware
from app.routes import router
from app.schemas import HealthResponse

app = FastAPI(title="CloudBox")

app.add_middleware(RequestBodyLimitMiddleware, max_body_size=105 * 1024 * 1024)

app.include_router(router)


@app.get("/health", response_model=HealthResponse)
def health_check():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "database": "ok",
    }
