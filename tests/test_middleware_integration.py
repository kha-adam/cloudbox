import asyncio
import json

from fastapi import FastAPI, Request
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


def test_streaming_request_without_content_length_returns_413():
    max_body_size = 100

    test_app = create_test_app(max_body_size=max_body_size)

    @test_app.post("/echo")
    async def echo(request: Request):
        body = await request.body()
        return {"size": len(body)}

    async def run_request():
        # Deliberately omit the Content-Length header.
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/echo",
            "raw_path": b"/echo",
            "query_string": b"",
            "root_path": "",
            "headers": [(b"host", b"testserver")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }

        # Two chunks, each within the limit, but 120 bytes in total.
        chunks = [
            {
                "type": "http.request",
                "body": b"a" * 60,
                "more_body": True,
            },
            {
                "type": "http.request",
                "body": b"b" * 60,
                "more_body": False,
            },
        ]
        chunk_index = 0
        sent_messages = []

        async def receive():
            nonlocal chunk_index

            if chunk_index < len(chunks):
                message = chunks[chunk_index]
                chunk_index += 1
                return message

            return {"type": "http.disconnect"}

        async def send(message):
            sent_messages.append(message)

        await test_app(scope, receive, send)
        return sent_messages

    messages = asyncio.run(run_request())

    response_start = next(
        message for message in messages if message["type"] == "http.response.start"
    )
    response_body = next(
        message for message in messages if message["type"] == "http.response.body"
    )

    assert response_start["status"] == 413
    assert json.loads(response_body["body"]) == {"detail": "Request body too large"}
