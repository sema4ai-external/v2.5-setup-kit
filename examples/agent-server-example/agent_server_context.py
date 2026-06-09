"""Per-request Sema4.ai platform-context binding for tool handlers.

Decodes `X-Tool-Invocation-Context`, validates the load-bearing fields,
and builds an authenticated Agent Server API client. The header dict is
held in a ContextVar so helpers deep in the call stack reach it without
explicit parameter threading — bind it once per request (see
`_bind_request_context` in server.py).
"""
import base64
import json
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse

import httpx

_INVOCATION_CONTEXT_HEADER = "x-tool-invocation-context"
_REQUEST_HEADERS: ContextVar[dict[str, str] | None] = ContextVar(
    "agent_server_example_request_headers",
    default=None,
)


@dataclass(frozen=True)
class _InvocationContext:
    base_url: str
    api_auth: str
    invocation_data: dict[str, str]

    @property
    def thread_id(self) -> str | None:
        return self.invocation_data.get("thread_id")


def _get_header_case_insensitive(headers: Mapping[str, str], key: str) -> str | None:
    for header_key, value in headers.items():
        if header_key.lower() == key:
            return value
    return None


def _parse_invocation_data(raw_header: str | None) -> dict[str, str]:
    if not raw_header:
        return {}
    try:
        decoded = base64.b64decode(raw_header).decode("utf-8")
        loaded = json.loads(decoded)
    except Exception as exc:
        raise ValueError("Invalid X-Tool-Invocation-Context header") from exc
    try:
        return {str(key): "" if value is None else str(value) for key, value in loaded.items()}
    except Exception as exc:
        raise ValueError("X-Tool-Invocation-Context must decode to an object") from exc


def _validate_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Invalid agent_server_api_url")
    return base_url.rstrip("/")


def _parse_invocation_context(headers: Mapping[str, str]) -> _InvocationContext:
    invocation_context_raw = _get_header_case_insensitive(headers, _INVOCATION_CONTEXT_HEADER)
    if not invocation_context_raw:
        raise ValueError("Missing X-Tool-Invocation-Context header")

    invocation_data = _parse_invocation_data(invocation_context_raw)
    api_auth = (invocation_data.get("agent_server_api_token") or "").strip()
    if not api_auth:
        raise ValueError("Missing agent_server_api_token in X-Tool-Invocation-Context")

    base_url = (invocation_data.get("agent_server_api_url") or "").strip()
    if not base_url:
        raise ValueError("Missing agent_server_api_url in X-Tool-Invocation-Context")

    return _InvocationContext(
        base_url=_validate_base_url(base_url),
        api_auth=api_auth,
        invocation_data=invocation_data,
    )


def _create_authenticated_client(context: _InvocationContext) -> Any:
    from sema4ai_api_client.client import AuthenticatedClient

    token = context.api_auth.strip()
    return AuthenticatedClient(
        base_url=context.base_url,
        token=token,
        timeout=httpx.Timeout(30.0),
        verify_ssl=True,
        follow_redirects=True,
    )


def bind_request_headers(headers: Mapping[str, str]) -> Token[dict[str, str] | None]:
    normalized = {str(key): str(value) for key, value in headers.items()}
    return _REQUEST_HEADERS.set(normalized)


def reset_request_headers(token: Token[dict[str, str] | None]) -> None:
    _REQUEST_HEADERS.reset(token)


def _current_headers() -> dict[str, str]:
    headers = _REQUEST_HEADERS.get()
    if not headers:
        raise RuntimeError("No request headers bound for Agent Server file operations")
    return headers


def current_client_agent_and_thread_id() -> tuple[Any, str, str]:
    context = _parse_invocation_context(_current_headers())
    thread_id = (context.thread_id or "").strip()
    if not thread_id:
        raise ValueError("Missing thread_id in X-Tool-Invocation-Context")

    agent_id = (context.invocation_data.get("agent_id") or "").strip()
    if not agent_id:
        raise ValueError("Missing agent_id in X-Tool-Invocation-Context")

    return _create_authenticated_client(context), agent_id, thread_id


def current_invocation_data() -> dict[str, str]:
    context = _parse_invocation_context(_current_headers())
    return context.invocation_data
