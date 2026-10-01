import json
import re
import unittest
from pathlib import Path

from sudhanva import APIError, Client, __version__
from sudhanva.client import USER_AGENT, Response


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
    def test_package_metadata_and_user_agent_share_one_version(self):
        pyproject = (Path(__file__).parents[1] / "pyproject.toml").read_text()
        project_version = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)

        self.assertIsNotNone(project_version)
        self.assertEqual(project_version.group(1), __version__)
        self.assertEqual(USER_AGENT, f"sudhanva-python/{__version__}")

    def test_posts_encodes_filters_and_identifies_client(self):
        transport = FakeTransport([response(200, {"posts": []})])
        client = Client(base_url="https://example.test/api/v1", transport=transport)

        self.assertEqual(client.posts(limit=5, tag="machine-learning"), {"posts": []})

        method, url, headers, body, timeout = transport.requests[0]
        self.assertEqual(method, "GET")
        self.assertEqual(url, "https://example.test/api/v1/posts?limit=5&tag=machine-learning")
        self.assertEqual(headers["User-Agent"], "sudhanva-python/0.2.0")
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

    def test_error_envelope_keeps_hint_and_docs_url(self):
        envelope = {
            "error": {
                "code": "POST_NOT_FOUND",
                "message": "No published post exists.",
                "hint": "List published posts first.",
                "docs_url": "https://sudhanva.me/developers/",
            }
        }
        client = Client(transport=FakeTransport([response(404, envelope)]))

        with self.assertRaises(APIError) as caught:
            client.post("missing")

        self.assertEqual(caught.exception.code, "POST_NOT_FOUND")
        self.assertEqual(caught.exception.message, "No published post exists.")
        self.assertEqual(caught.exception.hint, "List published posts first.")
        self.assertEqual(caught.exception.docs_url, "https://sudhanva.me/developers/")

    def test_problem_details_are_exposed(self):
        problem = {
            "type": "https://sudhanva.me/docs/profile-insights/#idempotency-key-reuse",
            "title": "Idempotency-Key reused",
            "status": 422,
            "detail": "This key was already used with a different request body.",
            "instance": "/api/v1/profile-insights",
        }
        client = Client(transport=FakeTransport([response(422, problem)]))

        with self.assertRaises(APIError) as caught:
            client.create_profile_insight(audience="agent", idempotency_key="python-test-123")

        self.assertEqual(caught.exception.status, 422)
        self.assertEqual(caught.exception.code, "idempotency-key-reuse")
        self.assertEqual(caught.exception.message, problem["detail"])
        self.assertEqual(caught.exception.body, problem)

    def test_problem_without_detail_falls_back_to_title(self):
        problem = {"type": "about:blank", "title": "Service Unavailable", "status": 503}
        client = Client(transport=FakeTransport([response(503, problem)]))

        with self.assertRaises(APIError) as caught:
            client.profile_insight("pi_test")

        self.assertEqual(caught.exception.code, "Service Unavailable")
        self.assertEqual(caught.exception.message, "Service Unavailable")

    def test_unexpected_error_bodies_still_raise_api_error(self):
        for payload in (["unexpected"], {"error": "Bad gateway"}, "oops", None):
            with self.subTest(payload=payload):
                client = Client(transport=FakeTransport([response(502, payload)]))

                with self.assertRaises(APIError) as caught:
                    client.profile()

                self.assertEqual(caught.exception.status, 502)
                self.assertEqual(caught.exception.code, "api_error")
                self.assertEqual(caught.exception.body, payload)

        client = Client(transport=FakeTransport([response(502, {"error": "Bad gateway"})]))
        with self.assertRaises(APIError) as caught:
            client.profile()
        self.assertEqual(caught.exception.message, "Bad gateway")


if __name__ == "__main__":
    unittest.main()
