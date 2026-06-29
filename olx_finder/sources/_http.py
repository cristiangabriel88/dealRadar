"""Shared polite-fetching helper used by every marketplace source.

Centralizes the retry/backoff policy (originally inlined in ``OlxSource``) so all
sources hammer no site: exponential backoff on 403/429/5xx and on timeouts /
transport errors, with a hard retry cap. Two thin wrappers are provided —
:func:`get_json` for API endpoints (OLX) and :func:`get_html` for HTML pages
(Publi24, Lajumate, Anuntul).
"""

from __future__ import annotations

import time
from typing import Any

import httpx

import config

# HTTP status codes that warrant a backoff-and-retry rather than a hard failure.
RETRY_STATUSES = {403, 429, 500, 502, 503, 504}

# Default headers; sources may pass extra/overriding headers (e.g. Accept: json).
_BASE_HEADERS = {
    "User-Agent": config.USER_AGENT,
    "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
}


def make_client(extra_headers: dict[str, str] | None = None) -> httpx.Client:
    """An httpx client preconfigured with polite headers and the shared timeout."""
    headers = dict(_BASE_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    return httpx.Client(
        headers=headers,
        timeout=config.REQUEST_TIMEOUT,
        follow_redirects=True,
    )


def _backoff(attempt: int) -> None:
    time.sleep(config.BACKOFF_BASE ** attempt)


def get(
    client: httpx.Client, url: str, params: dict[str, Any] | None = None
) -> httpx.Response | None:
    """GET ``url`` with exponential backoff on 403/429/5xx/timeout.

    Returns the successful response, or ``None`` if every attempt hit a retryable
    condition. Raises ``RuntimeError`` on a non-retryable HTTP status.
    """
    last_exc: Exception | None = None
    for attempt in range(config.MAX_RETRIES):
        try:
            resp = client.get(url, params=params)
            if resp.status_code in RETRY_STATUSES:
                _backoff(attempt)
                continue
            resp.raise_for_status()
            return resp
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
            _backoff(attempt)
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            break  # non-retryable status
    if last_exc is not None:
        raise RuntimeError(f"request to {url} failed after retries: {last_exc}") from last_exc
    return None


def get_json(
    client: httpx.Client, url: str, params: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """GET and decode a JSON response (or ``None`` if it gave up retrying)."""
    resp = get(client, url, params)
    return resp.json() if resp is not None else None


def get_html(
    client: httpx.Client, url: str, params: dict[str, Any] | None = None
) -> str | None:
    """GET and return the response body text (or ``None`` if it gave up retrying)."""
    resp = get(client, url, params)
    return resp.text if resp is not None else None
