"""ASGI bearer-token middleware tests; no network server is started."""
import unittest

from neoos_mcp import BearerTokenMiddleware


TOKEN = "test-token-value-that-is-long-enough-123456"


class BearerTokenMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def run_request(self, authorization=None):
        calls = []
        messages = []
        async def app(scope, receive, send):
            calls.append("app")
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [],
            })
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = BearerTokenMiddleware(app, TOKEN)
        headers = []
        if authorization is not None:
            headers.append((b"authorization", authorization))
        scope = {"type": "http", "headers": headers}
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        async def send(message):
            messages.append(message)

        await middleware(scope, receive, send)
        return calls, messages

    async def test_missing_token_is_unauthorized(self):
        calls, messages = await self.run_request()
        self.assertEqual(calls, [])
        self.assertEqual(messages[0]["status"], 401)
        self.assertIn(b"unauthorized", messages[1]["body"])

    async def test_malformed_authorization_is_unauthorized(self):
        for value in (b"Basic abc", b"Bearer", b"Bearer ", b"Bearer\t" + TOKEN.encode(), b"Bearer \xff"):
            with self.subTest(value=value):
                calls, messages = await self.run_request(value)
                self.assertEqual(calls, [])
                self.assertEqual(messages[0]["status"], 401)

    async def test_wrong_token_is_unauthorized(self):
        calls, messages = await self.run_request(b"Bearer definitely-wrong")
        self.assertEqual(calls, [])
        self.assertEqual(messages[0]["status"], 401)

    async def test_correct_token_is_accepted_case_insensitive_scheme(self):
        calls, messages = await self.run_request(b"bearer " + TOKEN.encode())
        self.assertEqual(calls, ["app"])
        self.assertEqual(messages[0]["status"], 200)

    async def test_non_http_scope_passes_through(self):
        calls = []
        async def app(scope, receive, send):
            calls.append(scope["type"])
        middleware = BearerTokenMiddleware(app, TOKEN)
        async def receive():
            return {}
        async def send(message):
            pass

        await middleware({"type": "lifespan", "headers": []}, receive, send)
        self.assertEqual(calls, ["lifespan"])


if __name__ == "__main__":
    unittest.main()
