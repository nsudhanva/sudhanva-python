import json
import unittest

from sudhanva import APIError, Client
from sudhanva.client import Response


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, method, url, headers, body, timeout):
        self.requests.append((method, url, headers, body, timeout))
        return self.responses.pop(0)


def response(status, payload):
    return Response(status, {"Content-Type": "application/json"}, json.dumps(payload).encode())


class ClientTest(unittest.TestCase):
    def test_posts_encodes_filters_and_identifies_client(self):
        transport = FakeTransport([response(200, {"posts": []})])
        client = Client(base_url="https://example.test/api/v1", transport=transport)

        self.assertEqual(client.posts(limit=5, tag="machine-learning"), {"posts": []})

        method, url, headers, body, timeout = transport.requests[0]
        self.assertEqual(method, "GET")
        self.assertEqual(url, "https://example.test/api/v1/posts?limit=5&tag=machine-learning")
        self.assertEqual(headers["User-Agent"], "sudhanva-python/0.1.0")
        self.assertIsNone(body)
        self.assertEqual(timeout, 10.0)

    def test_profile_insight_sends_idempotency_key(self):
        transport = FakeTransport([response(202, {"job_id": "pi_1", "status": "queued"})])
        client = Client(transport=transport)

        client.create_profile_insight(
            audience="agent",
            focus=["production-ml"],
            idempotency_key="python-test-123",
        )

        method, _, headers, body, _ = transport.requests[0]
        self.assertEqual(method, "POST")
        self.assertEqual(headers["Idempotency-Key"], "python-test-123")
        self.assertEqual(
            json.loads(body),
            {"audience": "agent", "focus": ["production-ml"]},
        )

    def test_wait_stops_at_terminal_state(self):
        transport = FakeTransport([
            response(200, {"status": "running"}),
            response(200, {"status": "succeeded", "result": {"summary": "done"}}),
        ])
        client = Client(transport=transport)

        job = client.wait_for_profile_insight("pi_test", timeout=1, poll_interval=0)

        self.assertEqual(job["status"], "succeeded")
        self.assertEqual(len(transport.requests), 2)

    def test_ask_uses_site_root_instead_of_api_base(self):
        transport = FakeTransport([response(200, {"results": []})])
        client = Client(base_url="https://example.test/api/v1", transport=transport)

        client.ask("Kubernetes", limit=3, mode="summarize")

        _, url, _, body, _ = transport.requests[0]
        self.assertEqual(url, "https://example.test/ask")
        self.assertEqual(json.loads(body)["query"]["limit"], 3)
        self.assertEqual(json.loads(body)["prefer"]["mode"], "summarize")

    def test_structured_errors_are_exposed(self):
        transport = FakeTransport([
            response(404, {"error": {"code": "not_found", "message": "Missing"}})
        ])
        client = Client(transport=transport)

        with self.assertRaises(APIError) as caught:
            client.post("missing")

        self.assertEqual(caught.exception.status, 404)
        self.assertEqual(caught.exception.code, "not_found")


if __name__ == "__main__":
    unittest.main()
