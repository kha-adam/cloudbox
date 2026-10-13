
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import RequestBodyLimitMiddleware
from app.routes import router


def create_test_app(max_body_size: int) -> FastAPI:
    test_app = FastAPI()

    test_app.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_size=max_body_size,
    )
    test_app.include_router(router)

    return test_app


def test_real_upload_request_exceeding_limit_returns_413():
    # A tiny limit makes the test fast and avoids a huge payload.
    app = create_test_app(max_body_size=100)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/files",
            files={
                "file": (
                    "test.txt",
                    b"x" * 200,
                    "text/plain",
                )
            },
        )

    assert response.status_code == 413
    assert response.json()["detail"] == "Request body too large"
