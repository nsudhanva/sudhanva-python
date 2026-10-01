"""Dependency-free client for the public sudhanva.me API."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence

DEFAULT_BASE_URL = "https://sudhanva.me/api/v1"
USER_AGENT = "sudhanva-python/0.2.0"


@dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]
    body: bytes


Transport = Callable[[str, str, Mapping[str, str], Optional[bytes], float], Response]


class APIError(RuntimeError):
    """An error response returned by the sudhanva.me API."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        body: Any,
        *,
        hint: Optional[str] = None,
        docs_url: Optional[str] = None,
    ) -> None:
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.body = body
        self.hint = hint
        self.docs_url = docs_url


def _text(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value else None


def _problem_code(problem_type: Optional[str]) -> Optional[str]:
    """Return the last fragment or path segment of an RFC 9457 problem type."""
    if problem_type is None or problem_type == "about:blank":
        return None
    base, _, fragment = problem_type.partition("#")
    return _text(fragment) or _text(base.rstrip("/").rsplit("/", 1)[-1])


def _api_error(status: int, payload: Any) -> APIError:
    """Build an APIError from the standard envelope or an RFC 9457 problem."""
    body = payload if isinstance(payload, dict) else {}
    nested = body.get("error")
    error = nested if isinstance(nested, dict) else body

    code = _text(error.get("code")) or _text(body.get("code"))
    message = _text(error.get("message")) or _text(body.get("message"))
    if code is None and message is None:
        title = _text(body.get("title"))
        code = _problem_code(_text(body.get("type"))) or title
        message = _text(body.get("detail")) or title
    if message is None and isinstance(nested, str):
        message = nested

    return APIError(
        status,
        code or "api_error",
        message or "Request failed",
        payload,
        hint=_text(error.get("hint")),
        docs_url=_text(error.get("docs_url")),
    )


class Client:
    """Small synchronous client for every stable public API operation."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        transport: Optional[Transport] = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.base_url = base_url.rstrip("/")
        parsed = urllib.parse.urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        self.site_url = f"{parsed.scheme}://{parsed.netloc}"
        self.timeout = timeout
        self._transport = transport or self._default_transport

    def profile(self, *, locale: str = "en") -> dict[str, Any]:
        return self._request("GET", "/profile", query={"locale": locale})

    def posts(
        self,
        *,
        limit: int = 20,
        tag: Optional[str] = None,
        cursor: Optional[str] = None,
    ) -> dict[str, Any]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        return self._request(
            "GET",
            "/posts",
            query={"limit": limit, "tag": tag, "cursor": cursor},
        )

    def post(self, slug: str) -> dict[str, Any]:
        if not slug:
            raise ValueError("slug is required")
        return self._request("GET", f"/posts/{urllib.parse.quote(slug, safe='')}")

    def batch(self, operations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        if not 1 <= len(operations) <= 20:
            raise ValueError("operations must contain between 1 and 20 items")
        return self._request("POST", "/batch", json_body={"operations": list(operations)})

    def create_profile_insight(
        self,
        *,
        audience: str,
        idempotency_key: str,
        focus: Optional[Sequence[str]] = None,
    ) -> dict[str, Any]:
        if not idempotency_key:
            raise ValueError("idempotency_key is required")
        body: dict[str, Any] = {"audience": audience}
        if focus is not None:
            body["focus"] = list(focus)
        return self._request(
            "POST",
            "/profile-insights",
            headers={"Idempotency-Key": idempotency_key},
            json_body=body,
        )

    def profile_insight(self, job_id: str) -> dict[str, Any]:
        if not job_id:
            raise ValueError("job_id is required")
        return self._request(
            "GET", f"/profile-insights/{urllib.parse.quote(job_id, safe='')}"
        )

    def wait_for_profile_insight(
        self,
        job_id: str,
        *,
        timeout: float = 30.0,
        poll_interval: float = 1.0,
    ) -> dict[str, Any]:
        if timeout <= 0 or poll_interval < 0:
            raise ValueError("timeout must be positive and poll_interval cannot be negative")
        deadline = time.monotonic() + timeout
        while True:
            job = self.profile_insight(job_id)
            if job.get("status") in {"succeeded", "failed"}:
                return job
            if time.monotonic() >= deadline:
                raise TimeoutError(f"profile insight {job_id} did not finish within {timeout}s")
            time.sleep(poll_interval)

    def ask(
        self,
        text: str,
        *,
        limit: int = 10,
        mode: str = "list",
    ) -> dict[str, Any]:
        if not text:
            raise ValueError("text is required")
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")
        return self._request(
            "POST",
            "/ask",
            absolute_base=self.site_url,
            json_body={
                "query": {"text": text, "site": self.site_url, "limit": limit},
                "prefer": {"streaming": False, "response_format": "conversational_search", "mode": mode},
                "meta": {"version": "0.55"},
            },
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
        json_body: Optional[Mapping[str, Any]] = None,
        absolute_base: Optional[str] = None,
    ) -> dict[str, Any]:
        pairs = [] if query is None else [(key, value) for key, value in query.items() if value is not None]
        query_string = urllib.parse.urlencode(pairs)
        url = f"{(absolute_base or self.base_url).rstrip('/')}/{path.lstrip('/')}"
        if query_string:
            url = f"{url}?{query_string}"

        request_headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        request_headers.update(headers or {})
        body = None
        if json_body is not None:
            body = json.dumps(json_body, separators=(",", ":")).encode("utf-8")
            request_headers["Content-Type"] = "application/json"

        response = self._transport(method, url, request_headers, body, self.timeout)
        try:
            payload = json.loads(response.body.decode("utf-8")) if response.body else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise APIError(response.status, "invalid_response", "API returned invalid JSON", None) from exc

        if not 200 <= response.status < 300:
            raise _api_error(response.status, payload)
        if not isinstance(payload, dict):
            raise APIError(response.status, "invalid_response", "API returned a non-object response", payload)
        return payload

    @staticmethod
    def _default_transport(
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: Optional[bytes],
        timeout: float,
    ) -> Response:
        request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as result:
                return Response(result.status, dict(result.headers.items()), result.read())
        except urllib.error.HTTPError as error:
            return Response(error.code, dict(error.headers.items()), error.read())
