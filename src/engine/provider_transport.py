import queue
import threading
from dataclasses import asdict, dataclass

import requests


class ProviderRequestCancelled(Exception):
    pass


@dataclass(frozen=True)
class ProviderFailure:
    provider: str
    code: str
    retryable: bool = False
    status_code: int | None = None
    request_id: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def failure_from_response(provider: str, response) -> ProviderFailure:
    status = response.status_code
    if status in (401, 403):
        code = "authentication"
    elif status == 429:
        code = "rate_limited"
    elif status >= 500:
        code = "server_error"
    else:
        code = "request_rejected"
    request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
    return ProviderFailure(provider, code, status == 429 or status >= 500, status, request_id)


def failure_from_exception(provider: str, error: Exception) -> ProviderFailure:
    status = getattr(error, "status_code", None)
    request_id = getattr(error, "request_id", None)
    if isinstance(error, (requests.Timeout, TimeoutError)):
        return ProviderFailure(provider, "timeout", True, status, request_id)
    if isinstance(error, requests.RequestException):
        return ProviderFailure(provider, "network_error", True, status, request_id)
    if status in (401, 403):
        code = "authentication"
    elif status == 429:
        code = "rate_limited"
    elif isinstance(status, int) and status >= 500:
        code = "server_error"
    else:
        code = "provider_error"
    return ProviderFailure(provider, code, status == 429 or isinstance(status, int) and status >= 500, status, request_id)


def run_cancellable(request, cancel_check=None, poll_seconds: float = 0.05):
    """Return promptly on cooperative cancellation and discard a late HTTP result."""
    if not cancel_check:
        return request()
    if cancel_check():
        raise ProviderRequestCancelled()

    results = queue.Queue(maxsize=1)

    def execute():
        try:
            results.put((True, request()))
        except BaseException as error:
            results.put((False, error))

    threading.Thread(target=execute, daemon=True, name="ProviderRequest").start()
    while True:
        if cancel_check():
            raise ProviderRequestCancelled()
        try:
            succeeded, value = results.get(timeout=poll_seconds)
        except queue.Empty:
            continue
        if succeeded:
            return value
        raise value
