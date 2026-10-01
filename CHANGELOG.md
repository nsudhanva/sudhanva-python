# Changelog

## 0.2.0 — 2026-10-01

- Requires Python 3.10 or newer. Tested on Python 3.10 through 3.14 and the 3.15 release candidate.
- Error responses in RFC 9457 problem format, which the profile-insight endpoints return, now report their `detail` and `type` instead of a generic "Request failed".
- `APIError` exposes `hint` and `docs_url` from the standard error envelope.
- Unexpected error bodies, such as a JSON array or a string `error`, raise `APIError` instead of `AttributeError`.
- `sudhanva.__version__`, the package metadata, and the `User-Agent` header report the same version.
- Releases publish to PyPI from GitHub Actions through trusted publishing.

## 0.1.0 — 2026-08-24

- First release: profile, articles, search, batch reads, and profile-insight jobs.
