from __future__ import annotations

import base64
import json

from starlette.requests import Request


def build_request(headers: dict[str, str] | None = None) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "headers": raw})


def invocation_header(**overrides: str) -> str:
    """Base64-encoded X-Tool-Invocation-Context payload with sane defaults."""
    data = {
        "agent_id": "agent-1",
        "thread_id": "thread-1",
        "tenant_id": "tenant-1",
        "invoked_on_behalf_of_user_id": "user-1",
        "agent_server_api_url": "https://api.example.com",
        "agent_server_api_token": "tok-123",
    }
    data.update(overrides)
    return base64.b64encode(json.dumps(data).encode("utf-8")).decode("utf-8")


def text_msg(role: str, text: str, *, message_id: str, complete: bool = True) -> dict:
    return {
        "role": role,
        "message_id": message_id,
        "complete": complete,
        "content": [{"kind": "text", "text": text, "complete": True}],
    }


def user_msg_with_file(text: str, *, message_id: str, name: str, mime: str, uri: str) -> dict:
    return {
        "role": "user",
        "message_id": message_id,
        "complete": True,
        "content": [
            {"kind": "text", "text": text, "complete": True},
            {"kind": "attachment", "name": name, "mime_type": mime, "uri": uri, "complete": True},
        ],
    }
