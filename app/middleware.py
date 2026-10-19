class RequestBodyTooLarge(Exception):
    pass


class RequestBodyLimitMiddleware:
    def __init__(self, app, max_body_size: int):
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")

        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                await self._reject(send)
                return

            if declared_size < 0 or declared_size > self.max_body_size:
                await self._reject(send)
                return

        received_size = 0
        rejected = False
        response_started = False

        async def limited_receive():
            nonlocal received_size, rejected

            message = await receive()

            if message["type"] == "http.request":
                received_size += len(message.get("body", b""))

                if received_size > self.max_body_size:
                    rejected = True

                    if not response_started:
                        await self._reject(send)

                    raise RequestBodyTooLarge()

            return message

        async def guarded_send(message):
            nonlocal response_started

            if rejected:
                return

            if message["type"] == "http.response.start":
                response_started = True

            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except RequestBodyTooLarge:
            if response_started:
                raise

    async def _reject(self, send):
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b'{"detail":"Request body too large"}',
            }
        )
