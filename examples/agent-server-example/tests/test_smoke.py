"""Smoke test — import the server, list tools, assert the expected registry."""
from __future__ import annotations

import server


EXPECTED_TOOLS = {
    "get_bound_context",
    "list_thread_data_frames",
    "get_thread_data_frame",
    "list_thread_files",
    "upload_text_to_thread_file",
    "download_thread_file_text",
}


def _registered_tool_names() -> set[str]:
    # Internal API — fragile across fastmcp versions. If this breaks, check
    # the current fastmcp tool-registry accessor and adjust.
    return {tool.name for tool in server.mcp._tool_manager._tools.values()}


def test_all_expected_tools_registered() -> None:
    names = _registered_tool_names()
    missing = EXPECTED_TOOLS - names
    extra = names - EXPECTED_TOOLS
    assert not missing, f"Missing tools: {missing}"
    assert not extra, f"Unexpected tools: {extra}"


def test_tool_count() -> None:
    assert len(_registered_tool_names()) == 6
