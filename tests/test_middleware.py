import asyncio

from app.middleware import RequestBodyLimitMiddleware

MAX_BODY_SIZE = 5


def make_scope(headers=None):
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/upload",
        "raw_path": b"/upload",
        "query_string": b"",
        "headers": headers or [],
        "server": ("testserver", 80),
        "client": ("testclient", 1234),
    }


async def fake_app(scope, receive, send):
    # Consume the request body, as a real application might.
    while True:
        message = await receive()

        if message["type"] == "http.disconnect":
            return

        if not message.get("more_body", False):
            break

    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": b"OK",
        }
    )


def run_middleware(headers, body_messages):
    async def run():
        scope = make_scope(headers)
        sent_messages = []
        remaining_messages = list(body_messages)

        async def receive():
            if remaining_messages:
                return remaining_messages.pop(0)
            return {"type": "http.disconnect"}

        async def send(message):
            sent_messages.append(message)

        middleware = RequestBodyLimitMiddleware(
            fake_app,
            max_body_size=MAX_BODY_SIZE,
        )

        await middleware(scope, receive, send)
        return sent_messages

    return asyncio.run(run())


def response_status(messages):
    return next(
        message["status"]
        for message in messages
        if message["type"] == "http.response.start"
    )


def test_rejects_declared_oversized_body():
    messages = run_middleware(
        headers=[(b"content-length", b"6")],
        body_messages=[],
    )

    assert response_status(messages) == 413


def test_rejects_oversized_body_without_content_length():
    messages = run_middleware(
        headers=[],
        body_messages=[
            {
                "type": "http.request",
                "body": b"abc",
                "more_body": True,
            },
            {
                "type": "http.request",
                "body": b"def",
                "more_body": False,
            },
        ],
    )

    assert response_status(messages) == 413


def test_allows_body_within_limit():
    messages = run_middleware(
        headers=[],
        body_messages=[
            {
                "type": "http.request",
                "body": b"abc",
                "more_body": True,
            },
            {
                "type": "http.request",
                "body": b"de",
                "more_body": False,
            },
        ],
    )

    assert response_status(messages) == 200
