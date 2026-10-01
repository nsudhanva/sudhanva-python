# sudhanva for Python

Minimal, dependency-free Python client for the public
[sudhanva.me API](https://sudhanva.me/openapi.json). It retrieves published profile and article
metadata, performs bounded batch reads, searches the published site, and creates or polls temporary
profile-insight jobs.

The API is public and requires no credentials. Do not send private data.

## Install

```bash
python -m pip install sudhanva==0.2.0
```

## Use

```python
from sudhanva import Client

client = Client()

profile = client.profile()
posts = client.posts(limit=5, tag="kubernetes")
article = client.post("making-your-site-agent-friendly")

job = client.create_profile_insight(
    audience="hiring-manager",
    focus=["production-ml", "inference"],
    idempotency_key="my-workflow-2026-08-23",
)
result = client.wait_for_profile_insight(job["job_id"])
```

All methods return decoded JSON dictionaries. Non-success responses raise `sudhanva.APIError` with
`status`, `code`, `message`, and the decoded response body.

## API coverage

- `profile()`
- `posts()` and `post()`
- `batch()`
- `create_profile_insight()`, `profile_insight()`, and `wait_for_profile_insight()`
- `ask()` for NLWeb conversational search

The client follows the stable `/api/v1` contract. See the
[developer documentation](https://sudhanva.me/developers/sdks/) and
[versioning policy](https://sudhanva.me/developers/versioning/).

## Development

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m build
```

The test suite uses an injected transport and never calls production.

## License

MIT
