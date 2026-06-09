"""Thread-file upload / download helpers — wraps sema4ai-api-client.

These call back into the Agent Server public API, scoped by the agent_id
and thread_id from the bound invocation context. The generated endpoint
function names track the installed `sema4ai-api-client` version — if they
drift, check the package and adjust.
"""
from __future__ import annotations

from http import HTTPStatus
from io import BytesIO
from typing import Any

from sema4ai_api_client.api.agents import (
    download_conversation_file_agents_aid_conversations_cid_files_download_get,
    upload_conversation_files_agents_aid_conversations_cid_files_post,
)
from sema4ai_api_client.models.body_upload_conversation_files_agents_aid_conversations_cid_files_post import (
    BodyUploadConversationFilesAgentsAidConversationsCidFilesPost,
)
from sema4ai_api_client.types import File

from agent_server_context import current_client_agent_and_thread_id


def _raise_on_non_ok_response(operation: str, response: Any) -> None:
    if response.status_code == HTTPStatus.OK:
        return

    parsed = response.parsed
    if parsed is not None:
        raise RuntimeError(
            f"Agent Server {operation} failed with HTTP {response.status_code}: "
            f"{parsed.error.code} ({parsed.error.message})"
        )

    response_text = response.content.decode("utf-8", errors="replace").strip()
    details = f": {response_text}" if response_text else ""
    raise RuntimeError(
        f"Agent Server {operation} failed with HTTP {response.status_code}{details}"
    )


def attach_file_content(
    name: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> list[dict[str, Any]]:
    """Upload bytes as a thread file. Returns the Agent Server's file descriptor list."""
    client, agent_id, thread_id = current_client_agent_and_thread_id()
    payload = BodyUploadConversationFilesAgentsAidConversationsCidFilesPost(
        files=[
            File(
                payload=BytesIO(data),
                file_name=name,
                mime_type=content_type,
            )
        ]
    )
    response = upload_conversation_files_agents_aid_conversations_cid_files_post.sync_detailed(
        aid=agent_id,
        cid=thread_id,
        client=client,
        body=payload,
    )
    _raise_on_non_ok_response("upload_thread_files", response)
    parsed = response.parsed
    if not isinstance(parsed, list):
        return []
    return [item.to_dict() for item in parsed]


def get_file_content(file_ref: str) -> bytes:
    """Download a thread file by reference."""
    client, agent_id, thread_id = current_client_agent_and_thread_id()
    response = download_conversation_file_agents_aid_conversations_cid_files_download_get.sync_detailed(
        aid=agent_id,
        cid=thread_id,
        client=client,
        file_ref=file_ref,
    )
    _raise_on_non_ok_response("download_file_by_ref", response)
    parsed = response.parsed
    if parsed is None:
        return b""
    return parsed.payload.read()
