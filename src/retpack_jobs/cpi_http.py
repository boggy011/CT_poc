"""HTTP ``CpiClient`` for the existing CPI endpoint. Shape of URL, auth and body are ABI input 5."""

from collections.abc import Mapping
from typing import Any, Protocol

from retpack_jobs.cpi_dispatch import CpiRejectedError, CpiResult, CpiTransientError


class _Response(Protocol):
    @property
    def status_code(self) -> int: ...

    @property
    def text(self) -> str: ...

    def json(self) -> Any: ...


class _Session(Protocol):
    def post(self, url: str, *, json: Any, headers: Mapping[str, str], timeout: float) -> _Response: ...


class HttpCpiClient:
    """POSTs JSON with an ``Idempotency-Key`` header; 5xx and network errors are transient, 4xx is rejection."""

    def __init__(
        self, url: str, *, bearer_token: str, session: _Session | None = None, timeout_s: float = 30.0, reference_field: str = "returnOrderNumber"
    ) -> None:
        self._url = url
        self._headers = {"Authorization": f"Bearer {bearer_token}", "Content-Type": "application/json"}
        self._session = session or _requests_session()
        self._timeout = timeout_s
        self._reference_field = reference_field

    def create_return_order(self, *, idempotency_key: str, payload: Mapping[str, Any]) -> CpiResult:
        """See ``CpiClient.create_return_order``."""
        try:
            response = self._session.post(self._url, json=dict(payload), headers={**self._headers, "Idempotency-Key": idempotency_key}, timeout=self._timeout)
        except Exception as exc:  # requests raises a family of connection/timeout errors
            raise CpiTransientError(f"{type(exc).__name__}: {exc}") from exc
        if response.status_code >= 500:
            raise CpiTransientError(f"CPI {response.status_code}: {response.text[:200]}")
        if response.status_code >= 400:
            raise CpiRejectedError(f"CPI {response.status_code}: {response.text[:200]}")
        body = response.json()
        reference = body.get(self._reference_field) if isinstance(body, dict) else None
        if not reference:
            raise CpiRejectedError(f"CPI response lacks {self._reference_field!r}")
        return CpiResult(reference=str(reference))


class _RequestsSession:
    """Adapter narrowing ``requests.Session`` to the calls the client makes."""

    def __init__(self) -> None:
        import requests

        self._session = requests.Session()

    def post(self, url: str, *, json: Any, headers: Mapping[str, str], timeout: float) -> _Response:
        response: _Response = self._session.post(url, json=json, headers=dict(headers), timeout=timeout)
        return response


def _requests_session() -> _Session:
    return _RequestsSession()
