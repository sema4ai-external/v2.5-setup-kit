from __future__ import annotations

import pytest
from conftest import (
    build_request,
    invocation_header,
    text_msg,
    user_msg_with_file,
)
from fastmcp import Client

import server
from server import (
    _as_dict,
    build_pg_url_from_config,
    normalize_thumb,
    parse_invocation_context,
    parse_invocation_data,
    pick_data_connection,
    select_feedback_context,
)


# --- normalize_thumb ------------------------------------------------------- #
@pytest.mark.parametrize("value", ["up", "UP", " Up ", "👍", "thumbs_up", "positive"])
def test_normalize_thumb_up(value: str) -> None:
    assert normalize_thumb(value) == "up"


@pytest.mark.parametrize("value", ["down", "DOWN", "👎", "thumbs_down", "negative"])
def test_normalize_thumb_down(value: str) -> None:
    assert normalize_thumb(value) == "down"


@pytest.mark.parametrize("value", ["", "maybe", "sideways", None])
def test_normalize_thumb_invalid(value) -> None:
    with pytest.raises(ValueError):
        normalize_thumb(value)


# --- invocation context ---------------------------------------------------- #
def test_parse_invocation_data_roundtrip() -> None:
    data = parse_invocation_data(invocation_header(thread_id="t9"))
    assert data["thread_id"] == "t9"
    assert data["agent_server_api_token"] == "tok-123"


def test_parse_invocation_data_missing() -> None:
    with pytest.raises(ValueError):
        parse_invocation_data(None)


def test_parse_invocation_data_invalid() -> None:
    with pytest.raises(ValueError):
        parse_invocation_data("not-base64-json!!!")


def test_parse_invocation_context_requires_token() -> None:
    req = build_request({"x-tool-invocation-context": invocation_header(agent_server_api_token="")})
    with pytest.raises(ValueError):
        parse_invocation_context(req.headers)


def test_parse_invocation_context_ok() -> None:
    req = build_request({"x-tool-invocation-context": invocation_header()})
    ctx = parse_invocation_context(req.headers)
    assert ctx.agent_id == "agent-1"
    assert ctx.thread_id == "thread-1"
    assert ctx.base_url == "https://api.example.com"


# --- select_feedback_context ----------------------------------------------- #
def test_select_picks_rated_suggestion_and_preceding_input() -> None:
    # oldest -> newest: user input, agent suggestion, user click
    messages = [
        text_msg("user", "make me 3 media placements", message_id="m1"),
        text_msg("agent", "Here are 3 suggested media placements: ...", message_id="m2"),
        text_msg("user", "feedback: 👍", message_id="m3"),
    ]
    out = select_feedback_context(messages)
    assert out["rated_message_id"] == "m2"
    assert "suggested media placements" in out["rated_agent_message"]
    assert out["preceding_user_message"] == "make me 3 media placements"
    assert out["input_file_refs"] == []


def test_select_skips_incomplete_current_turn() -> None:
    # an in-progress agent turn (the one calling this tool) must be ignored
    messages = [
        text_msg("user", "input", message_id="m1"),
        text_msg("agent", "the suggestion", message_id="m2"),
        text_msg("user", "feedback: 👎", message_id="m3"),
        text_msg("agent", "", message_id="m4", complete=False),
    ]
    out = select_feedback_context(messages)
    assert out["rated_message_id"] == "m2"
    assert out["rated_agent_message"] == "the suggestion"


def test_select_captures_input_file_refs() -> None:
    messages = [
        user_msg_with_file(
            "rate this deck",
            message_id="m1",
            name="deck.pdf",
            mime="application/pdf",
            uri="agent-server-file://abc",
        ),
        text_msg("agent", "my review of the deck", message_id="m2"),
        text_msg("user", "feedback: 👍", message_id="m3"),
    ]
    out = select_feedback_context(messages)
    assert out["preceding_user_message"] == "rate this deck"
    assert out["input_file_refs"] == [
        {"name": "deck.pdf", "mime_type": "application/pdf", "uri": "agent-server-file://abc"}
    ]


def test_select_empty() -> None:
    out = select_feedback_context([])
    assert out["rated_message_id"] is None
    assert out["input_file_refs"] == []


# --- end-to-end tool wiring (FastMCP in-memory client) --------------------- #
async def test_record_user_feedback_tool_inserts_row() -> None:
    messages = [
        text_msg("user", "make 3 placements", message_id="m1"),
        text_msg("agent", "suggested media placements here", message_id="m2"),
        text_msg("user", "feedback: 👎", message_id="m3"),
    ]
    captured: dict = {}

    def fake_fetch(ctx) -> list[dict]:
        assert ctx.thread_id == "thread-1"
        return messages

    def fake_insert(conn_str: str, row: dict) -> str:
        captured["conn_str"] = conn_str
        captured["row"] = row
        return "fb-123"

    headers = {
        "x-tool-invocation-context": invocation_header(),
        "x-pg-connection-string": "postgresql://test/db",
    }
    app = server.create_app(
        get_request=lambda: build_request(headers),
        fetch_messages=fake_fetch,
        insert_feedback=fake_insert,
    )

    async with Client(app) as client:
        result = await client.call_tool("give_thumbs_down", {"notes": "too generic"})

    assert "👎" in result.data
    assert "feedback_id=fb-123" in result.data
    assert "thread_id=thread-1" in result.data
    assert "rated_message_id=m2" in result.data
    row = captured["row"]
    assert captured["conn_str"] == "postgresql://test/db"
    assert row["thumb_up_or_down"] == "down"
    assert row["notes"] == "too generic"
    assert row["agent_id"] == "agent-1"
    assert row["thread_id"] == "thread-1"
    assert row["tenant_id"] == "tenant-1"
    assert row["rated_message_id"] == "m2"
    assert row["rated_agent_message"] == "suggested media placements here"
    assert row["preceding_user_message"] == "make 3 placements"
    assert row["source_url"] == "https://api.example.com"
    assert row["thread_transcript"] == messages  # full transcript persisted
    assert row["user_id"] == "user-1"  # acting user captured for distinct-user counts


# --- connection-string resolution from the SDM data connection ------------- #
def test_build_pg_url_basic() -> None:
    cfg = {"host": "h", "port": 5432, "database": "agent_feedback", "user": "u", "password": "p"}
    assert build_pg_url_from_config(cfg) == (
        "postgresql://u:p@h:5432/agent_feedback?sslmode=require"
    )


def test_build_pg_url_encodes_special_chars_and_sslmode() -> None:
    cfg = {
        "host": "h",
        "database": "db",
        "user": "u@x",
        "password": "p@ss/w:rd",
        "sslmode": "verify-full",
    }
    url = build_pg_url_from_config(cfg)
    assert "u%40x:p%40ss%2Fw%3Ard@h:5432/db" in url
    assert url.endswith("?sslmode=verify-full")


def test_build_pg_url_missing_fields() -> None:
    with pytest.raises(ValueError):
        build_pg_url_from_config({"host": "h"})


@pytest.mark.parametrize("port", [5432, 5432.0, "5432", "5432.0"])
def test_build_pg_url_coerces_port_to_int(port) -> None:
    cfg = {"host": "h", "database": "db", "user": "u", "password": "p", "port": port}
    assert build_pg_url_from_config(cfg) == "postgresql://u:p@h:5432/db?sslmode=require"


def test_as_dict_handles_plain_dict_and_typed() -> None:
    assert _as_dict({"a": 1}) == {"a": 1}

    class Typed:
        def to_dict(self):
            return {"b": 2}

    assert _as_dict(Typed()) == {"b": 2}


def test_pick_data_connection_by_name() -> None:
    conns = [
        {"name": "other", "engine": "snowflake", "configuration": {}},
        {"name": "agent-feedback-neon", "engine": "postgres", "configuration": {"host": "h"}},
    ]
    assert pick_data_connection(conns, "agent-feedback-neon")["engine"] == "postgres"


def test_pick_data_connection_single_postgres_fallback() -> None:
    conns = [
        {"name": "x", "engine": "snowflake"},
        {"name": "y", "engine": "Postgres"},
    ]
    assert pick_data_connection(conns, "nope")["name"] == "y"


def test_pick_data_connection_none() -> None:
    conns = [{"name": "a", "engine": "postgres"}, {"name": "b", "engine": "postgres"}]
    assert pick_data_connection(conns, "missing") is None


async def test_record_feedback_resolves_conn_from_data_connection(monkeypatch) -> None:
    # no header / env override -> must resolve from the agent server data connection
    monkeypatch.delenv("PG_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("FEEDBACK_DATA_CONNECTION_NAME", raising=False)

    messages = [
        text_msg("user", "input", message_id="m1"),
        text_msg("agent", "the suggestion", message_id="m2"),
        text_msg("user", "feedback: 👍", message_id="m3"),
    ]
    captured: dict = {}

    def fake_fetch_dc(ctx) -> list[dict]:
        return [
            {
                "name": "agent-feedback-neon",
                "engine": "postgres",
                "configuration": {
                    "host": "db.example.com",
                    "port": 5432,
                    "database": "agent_feedback",
                    "user": "feedback_user",
                    "password": "secret",
                },
            }
        ]

    def fake_insert(conn_str: str, row: dict) -> str:
        captured["conn_str"] = conn_str
        return "fb-1"

    headers = {"x-tool-invocation-context": invocation_header()}  # note: no x-pg header
    app = server.create_app(
        get_request=lambda: build_request(headers),
        fetch_messages=lambda ctx: messages,
        fetch_data_connections=fake_fetch_dc,
        insert_feedback=fake_insert,
    )
    async with Client(app) as client:
        await client.call_tool("give_thumbs_up", {})

    assert captured["conn_str"] == (
        "postgresql://feedback_user:secret@db.example.com:5432/agent_feedback?sslmode=require"
    )


async def test_lists_three_tools() -> None:
    app = server.create_app(get_request=lambda: build_request({}))
    async with Client(app) as client:
        tools = await client.list_tools()
    assert sorted(t.name for t in tools) == [
        "add_feedback_reason",
        "give_thumbs_down",
        "give_thumbs_up",
    ]


async def test_add_feedback_reason_updates_latest(monkeypatch) -> None:
    monkeypatch.delenv("PG_CONNECTION_STRING", raising=False)
    captured: dict = {}

    def fake_update(conn_str: str, thread_id: str, reason: str, feedback_id=None) -> str:
        captured.update(
            conn_str=conn_str, thread_id=thread_id, reason=reason, feedback_id=feedback_id
        )
        return "fb-9"

    headers = {
        "x-tool-invocation-context": invocation_header(thread_id="thr-42"),
        "x-pg-connection-string": "postgresql://test/db",
    }
    app = server.create_app(
        get_request=lambda: build_request(headers),
        update_feedback_reason=fake_update,
    )
    async with Client(app) as client:
        result = await client.call_tool(
            "add_feedback_reason", {"reason": "the dates were wrong"}
        )

    assert captured["thread_id"] == "thr-42"
    assert captured["reason"] == "the dates were wrong"
    assert captured["feedback_id"] is None  # not supplied -> latest in thread
    assert "feedback_id=fb-9" in result.data


async def test_add_feedback_reason_targets_specific_id() -> None:
    captured: dict = {}

    def fake_update(conn_str: str, thread_id: str, reason: str, feedback_id=None) -> str:
        captured["feedback_id"] = feedback_id
        return feedback_id or "latest"

    headers = {
        "x-tool-invocation-context": invocation_header(),
        "x-pg-connection-string": "postgresql://test/db",
    }
    app = server.create_app(
        get_request=lambda: build_request(headers),
        update_feedback_reason=fake_update,
    )
    async with Client(app) as client:
        result = await client.call_tool(
            "add_feedback_reason", {"reason": "why", "feedback_id": "fb-xyz"}
        )
    assert captured["feedback_id"] == "fb-xyz"
    assert "feedback_id=fb-xyz" in result.data


async def test_add_feedback_reason_no_prior_feedback() -> None:
    headers = {
        "x-tool-invocation-context": invocation_header(),
        "x-pg-connection-string": "postgresql://test/db",
    }
    app = server.create_app(
        get_request=lambda: build_request(headers),
        update_feedback_reason=lambda *_: None,
    )
    async with Client(app) as client:
        result = await client.call_tool("add_feedback_reason", {"reason": "x"})
    assert "No matching feedback" in result.data
