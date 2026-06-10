"""Tests for agent_server_context — invocation-context parsing + binding.

This overlay treats the four Agent Server callback fields as load-bearing:
it raises (rather than returning an empty dict) when they're missing, so a
misconfigured call fails loudly instead of silently no-op'ing.
"""
from __future__ import annotations

import base64
import json

import pytest

from agent_server_context import (
    bind_request_headers,
    current_client_agent_and_thread_id,
    current_invocation_data,
    reset_request_headers,
)


def _encoded_context(**fields: str) -> str:
    return base64.b64encode(json.dumps(fields).encode("utf-8")).decode("ascii")


def test_current_invocation_data_returns_dict_from_valid_header() -> None:
    headers = {
        "X-Tool-Invocation-Context": _encoded_context(
            agent_id="agent-123",
            thread_id="thread-456",
            agent_server_api_url="https://agent-server.example.com",
            agent_server_api_token="sat_test",
        )
    }
    token = bind_request_headers(headers)
    try:
        data = current_invocation_data()
        assert data["agent_id"] == "agent-123"
        assert data["thread_id"] == "thread-456"
    finally:
        reset_request_headers(token)


def test_current_invocation_data_raises_when_no_headers_bound() -> None:
    with pytest.raises(RuntimeError, match="No request headers bound"):
        current_invocation_data()


def test_malformed_header_raises_value_error() -> None:
    token = bind_request_headers({"X-Tool-Invocation-Context": "not-base64!@#"})
    try:
        with pytest.raises(ValueError, match="Invalid X-Tool-Invocation-Context header"):
            current_invocation_data()
    finally:
        reset_request_headers(token)


def test_missing_api_token_raises() -> None:
    headers = {
        "X-Tool-Invocation-Context": _encoded_context(
            agent_id="agent-123",
            thread_id="thread-456",
            agent_server_api_url="https://agent-server.example.com",
            # agent_server_api_token intentionally missing
        )
    }
    token = bind_request_headers(headers)
    try:
        with pytest.raises(ValueError, match="agent_server_api_token"):
            current_invocation_data()
    finally:
        reset_request_headers(token)


def test_missing_thread_id_raises_before_client_creation() -> None:
    headers = {
        "X-Tool-Invocation-Context": _encoded_context(
            agent_id="agent-123",
            agent_server_api_url="https://agent-server.example.com",
            agent_server_api_token="sat_test",
            # thread_id intentionally missing
        )
    }
    token = bind_request_headers(headers)
    try:
        with pytest.raises(ValueError, match="Missing thread_id"):
            current_client_agent_and_thread_id()
    finally:
        reset_request_headers(token)


def test_missing_agent_id_raises_before_client_creation() -> None:
    headers = {
        "X-Tool-Invocation-Context": _encoded_context(
            thread_id="thread-456",
            agent_server_api_url="https://agent-server.example.com",
            agent_server_api_token="sat_test",
            # agent_id intentionally missing
        )
    }
    token = bind_request_headers(headers)
    try:
        with pytest.raises(ValueError, match="Missing agent_id"):
            current_client_agent_and_thread_id()
    finally:
        reset_request_headers(token)
