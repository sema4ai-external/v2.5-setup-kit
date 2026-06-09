"""Shared fixtures for the Agent Server example tests."""
from __future__ import annotations

import base64
import json
from collections.abc import Iterator

import pytest


def encode_context(**fields: str) -> str:
    """Base64-encode an X-Tool-Invocation-Context payload."""
    return base64.b64encode(json.dumps(fields).encode("utf-8")).decode("ascii")


@pytest.fixture
def bound_headers() -> Iterator[None]:
    """Bind a fully-populated invocation context for the test body."""
    from agent_server_context import bind_request_headers, reset_request_headers

    headers = {
        "X-Tool-Invocation-Context": encode_context(
            agent_id="agent-123",
            thread_id="thread-456",
            agent_server_api_url="https://agent-server.example.com",
            agent_server_api_token="sat_test",
        )
    }
    token = bind_request_headers(headers)
    try:
        yield
    finally:
        reset_request_headers(token)
