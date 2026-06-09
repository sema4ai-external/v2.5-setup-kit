"""Reference MCP server for Sema4.ai platform features.

Shows the three things a migrated MCP most often needs from the Sema4.ai
agent: the per-request invocation context, thread dataframes, and thread
files. Every tool reads its identity from `X-Tool-Invocation-Context` and
calls back into the Agent Server public API through `sema4ai-api-client`.

Flat module layout (module-level `mcp`, no `create_app()` wrapper) to match
the rest of this guide — see the worked SharePoint migration.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request
from mcp.types import ToolAnnotations

from sema4ai_api_client.api.agents import (
    get_conversation_data_frame_agents_aid_conversations_cid_data_frames_data_frame_name_get,
    get_conversation_data_frames_agents_aid_conversations_cid_data_frames_get,
    get_conversation_files_agents_aid_conversations_cid_files_get,
)
from sema4ai_api_client.models.error_envelope import ErrorEnvelope
from sema4ai_api_client.models.get_conversation_data_frame_agents_aid_conversations_cid_data_frames_data_frame_name_get_output_format import (
    GetConversationDataFrameAgentsAidConversationsCidDataFramesDataFrameNameGetOutputFormat,
)

from agent_server_context import (
    bind_request_headers,
    current_client_agent_and_thread_id,
    current_invocation_data,
    reset_request_headers,
)
from agent_server_helper import attach_file_content, get_file_content

HTTP_PORT = 8067

mcp = FastMCP("Agent Server Example")


def _raise_for_error_envelope(operation: str, response: Any) -> None:
    if isinstance(response, ErrorEnvelope):
        raise RuntimeError(
            f"{operation} failed with {response.error.code}: {response.error.message}"
        )


@contextmanager
def _bind_request_context() -> Iterator[None]:
    """Bind the incoming request headers for the duration of a tool call.

    Wrap every tool body that reads the invocation context or calls the
    Agent Server. The binding clears on exit so it stays correct under
    concurrent requests.
    """
    request = get_http_request()
    if request is None:
        raise RuntimeError("No HTTP request context available")
    token = bind_request_headers(request.headers)
    try:
        yield
    finally:
        reset_request_headers(token)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
def get_bound_context() -> dict[str, str]:
    """Return the invocation-context fields bound to this request. For debugging wiring."""
    with _bind_request_context():
        return current_invocation_data()


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
def list_thread_data_frames(num_samples: int = 5) -> list[dict[str, Any]]:
    """List the dataframes available on the current thread, with a small sample of rows each."""
    with _bind_request_context():
        client, agent_id, thread_id = current_client_agent_and_thread_id()
        result = get_conversation_data_frames_agents_aid_conversations_cid_data_frames_get.sync(
            aid=agent_id,
            cid=thread_id,
            client=client,
            num_samples=num_samples,
        )
        _raise_for_error_envelope("list_thread_data_frames", result)
        if not isinstance(result, list):
            raise RuntimeError(
                "list_thread_data_frames returned an unexpected response type"
            )
        return [item.to_dict() for item in result]


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
def get_thread_data_frame(
    data_frame_name: str,
    offset: int = 0,
    limit: int = 1000,
    column_names: str | None = None,
    order_by: str | None = None,
    output_format: str = "json",
) -> Any:
    """Fetch rows of a single named dataframe from the current thread."""
    with _bind_request_context():
        client, agent_id, thread_id = current_client_agent_and_thread_id()
        if output_format.lower() != "json":
            raise ValueError("Only output_format=json is supported by this example")

        result = get_conversation_data_frame_agents_aid_conversations_cid_data_frames_data_frame_name_get.sync(
            aid=agent_id,
            cid=thread_id,
            data_frame_name=data_frame_name,
            client=client,
            offset=offset,
            limit=limit,
            column_names=column_names,
            output_format=GetConversationDataFrameAgentsAidConversationsCidDataFramesDataFrameNameGetOutputFormat.JSON,
            order_by=order_by,
        )
        _raise_for_error_envelope("get_thread_data_frame", result)
        return result


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
def list_thread_files() -> list[dict[str, Any]]:
    """List the files attached to the current thread."""
    with _bind_request_context():
        client, agent_id, thread_id = current_client_agent_and_thread_id()
        result = get_conversation_files_agents_aid_conversations_cid_files_get.sync(
            aid=agent_id,
            cid=thread_id,
            client=client,
        )
        _raise_for_error_envelope("list_thread_files", result)
        if not isinstance(result, list):
            raise RuntimeError("list_thread_files returned an unexpected response type")
        return [item.to_dict() for item in result]


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True))
def upload_text_to_thread_file(
    name: str,
    content: str,
    content_type: str = "text/plain",
) -> list[dict[str, Any]]:
    """Upload text content as a new file on the current thread."""
    with _bind_request_context():
        return attach_file_content(
            name=name,
            data=content.encode("utf-8"),
            content_type=content_type,
        )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
def download_thread_file_text(file_ref: str, encoding: str = "utf-8") -> str:
    """Download a thread file by its file_ref and decode it as text."""
    with _bind_request_context():
        content = get_file_content(file_ref)
        return content.decode(encoding)


if __name__ == "__main__":
    port = int(os.environ.get("MCP_HTTP_PORT", str(HTTP_PORT)))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
