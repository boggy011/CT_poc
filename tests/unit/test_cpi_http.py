from typing import Any

import pytest

from retpack_jobs.cpi_dispatch import CpiRejectedError, CpiTransientError
from retpack_jobs.cpi_http import HttpCpiClient


class Resp:
    def __init__(self, status: int, body: Any = None, text: str = "") -> None:
        self.status_code = status
        self._body = body
        self.text = text

    def json(self) -> Any:
        return self._body


class Session:
    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, *, json: Any, headers: dict[str, str], timeout: float) -> Resp:
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def client(outcome: Any) -> tuple[HttpCpiClient, Session]:
    session = Session(outcome)
    return HttpCpiClient("https://cpi.example/returns", bearer_token="secret", session=session, timeout_s=5), session


def test_success_sends_idempotency_key_and_reads_reference():
    c, s = client(Resp(201, {"returnOrderNumber": "RO-123"}))
    result = c.create_return_order(idempotency_key="k1", payload={"a": 1})
    assert result.reference == "RO-123"
    call = s.calls[0]
    assert call["headers"]["Idempotency-Key"] == "k1" and call["headers"]["Authorization"] == "Bearer secret"
    assert call["json"] == {"a": 1} and call["timeout"] == 5


@pytest.mark.parametrize("status", [500, 502, 504])
def test_5xx_is_transient(status: int):
    c, _ = client(Resp(status, text="gateway"))
    with pytest.raises(CpiTransientError):
        c.create_return_order(idempotency_key="k", payload={})


@pytest.mark.parametrize("status", [400, 404, 422])
def test_4xx_is_rejection(status: int):
    c, _ = client(Resp(status, text="bad sold-to"))
    with pytest.raises(CpiRejectedError, match="bad sold-to"):
        c.create_return_order(idempotency_key="k", payload={})


def test_network_error_is_transient():
    c, _ = client(ConnectionError("reset"))
    with pytest.raises(CpiTransientError):
        c.create_return_order(idempotency_key="k", payload={})


def test_missing_reference_is_rejection():
    c, _ = client(Resp(200, {"other": 1}))
    with pytest.raises(CpiRejectedError):
        c.create_return_order(idempotency_key="k", payload={})
