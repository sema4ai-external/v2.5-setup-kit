"""User Feedback MCP server.

Records a thumbs up/down (plus optional notes) that a user gives on an agent's
previous suggestion, into a Neon Postgres table. ``give_thumbs_up`` and
``give_thumbs_down`` are called by the agent in the turn that results from the
user clicking a thumbs quick-action button (see the runbook segment in
README.md); ``add_feedback_reason`` is an optional follow-up that attaches a
reason to the latest feedback in the thread. ``thread_id`` / ``agent_id`` /
``tenant_id`` are taken implicitly from the ``X-Tool-Invocation-Context``
header — the LLM only passes notes/reason text.

On each call the MCP pulls the thread's recent messages from the agent server
(authenticated with the callback token in the invocation context), so it can
capture the *authoritative* rated agent suggestion and the user input that
preceded it — content a verified query cannot reach. Input files are stored as
refs only (name / mime_type / uri), never bytes.
"""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request
from mcp.types import ToolAnnotations
from starlette.requests import Request

HTTP_PORT = 8067
_INVOCATION_CONTEXT_HEADER = "x-tool-invocation-context"
_PG_HEADER = "x-pg-connection-string"
_DATA_CONNECTION_NAME_ENV = "FEEDBACK_DATA_CONNECTION_NAME"
_DEFAULT_DATA_CONNECTION_NAME = "agent-feedback-neon"

_TEXT_KINDS = {"text", "formatted-text"}
_UP = {"up", "thumbs_up", "thumbsup", "positive", "helpful", "👍"}
_DOWN = {"down", "thumbs_down", "thumbsdown", "negative", "unhelpful", "👎"}


# --------------------------------------------------------------------------- #
# Invocation context (mirrors servers/get-thread-link + agent-server-example)  #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class InvocationContext:
    base_url: str
    api_token: str
    data: dict[str, str]

    @property
    def agent_id(self) -> str:
        return (self.data.get("agent_id") or "").strip()

    @property
    def thread_id(self) -> str:
        return (self.data.get("thread_id") or "").strip()

    @property
    def tenant_id(self) -> str:
        return (self.data.get("tenant_id") or "").strip()

    @property
    def user_id(self) -> str:
        return (self.data.get("invoked_on_behalf_of_user_id") or "").strip()


def _get_header_case_insensitive(headers: Mapping[str, str], key: str) -> str | None:
    for header_key, value in headers.items():
        if header_key.lower() == key:
            return value
    return None


def parse_invocation_data(raw_header: str | None) -> dict[str, str]:
    if not raw_header:
        raise ValueError("Missing X-Tool-Invocation-Context header")
    try:
        decoded = base64.b64decode(raw_header).decode("utf-8")
        loaded = json.loads(decoded)
    except Exception as exc:
        raise ValueError("Invalid X-Tool-Invocation-Context header") from exc
    if not isinstance(loaded, dict):
        raise ValueError("X-Tool-Invocation-Context must decode to an object")
    return {str(k): "" if v is None else str(v) for k, v in loaded.items()}


def _validate_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Invalid agent_server_api_url in invocation context")
    return base_url.rstrip("/")


def parse_invocation_context(headers: Mapping[str, str]) -> InvocationContext:
    data = parse_invocation_data(
        _get_header_case_insensitive(headers, _INVOCATION_CONTEXT_HEADER)
    )
    api_token = (data.get("agent_server_api_token") or "").strip()
    if not api_token:
        raise ValueError("Missing agent_server_api_token in X-Tool-Invocation-Context")
    base_url = (data.get("agent_server_api_url") or "").strip()
    if not base_url:
        raise ValueError("Missing agent_server_api_url in X-Tool-Invocation-Context")
    ctx = InvocationContext(_validate_base_url(base_url), api_token, data)
    if not ctx.agent_id or not ctx.thread_id:
        raise ValueError("Missing agent_id or thread_id in X-Tool-Invocation-Context")
    return ctx


# --------------------------------------------------------------------------- #
# Pure helpers (unit-tested without network or DB)                             #
# --------------------------------------------------------------------------- #
def normalize_thumb(value: str) -> str:
    """Map a free-ish verdict to 'up' or 'down'. Raises ValueError otherwise."""
    key = (value or "").strip().lower()
    if key in _UP:
        return "up"
    if key in _DOWN:
        return "down"
    raise ValueError(f"thumb_up_or_down must be 'up' or 'down', got {value!r}")


def _extract_text(content: list[dict[str, Any]] | None) -> str:
    parts = [
        item["text"]
        for item in (content or [])
        if isinstance(item, dict) and item.get("kind") in _TEXT_KINDS and item.get("text")
    ]
    return "\n".join(parts).strip()


def pick_data_connection(connections: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    """Choose the feedback data connection from the agent server's list.

    Prefer an exact name match; otherwise, if there is exactly one postgres-like
    connection, use it. Returns None when nothing suitable is found.
    """
    name_l = (name or "").strip().lower()
    by_name = [c for c in connections if (c.get("name") or "").strip().lower() == name_l]
    if by_name:
        return by_name[0]
    postgres = [c for c in connections if "postgres" in (c.get("engine") or "").lower()]
    return postgres[0] if len(postgres) == 1 else None


def build_pg_url_from_config(cfg: dict[str, Any]) -> str:
    """Build a libpq connection URL from a postgres data-connection configuration."""
    from urllib.parse import quote

    host = cfg.get("host")
    database = cfg.get("database")
    user = cfg.get("user")
    if not (host and database and user):
        raise ValueError("postgres data connection config missing host/database/user")
    raw_port = cfg.get("port") or 5432
    try:
        port = int(float(raw_port))  # configs may carry the port as 5432.0 or "5432"
    except (TypeError, ValueError):
        raise ValueError(f"invalid port in data connection config: {raw_port!r}")
    sslmode = cfg.get("sslmode") or "require"
    auth = quote(str(user), safe="")
    password = cfg.get("password")
    if password:
        auth += ":" + quote(str(password), safe="")
    return f"postgresql://{auth}@{host}:{port}/{database}?sslmode={sslmode}"


def _extract_file_refs(content: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    return [
        {
            "name": item.get("name"),
            "mime_type": item.get("mime_type"),
            "uri": item.get("uri"),
        }
        for item in (content or [])
        if isinstance(item, dict) and item.get("kind") == "attachment"
    ]


def select_feedback_context(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """From the thread's messages (oldest→newest), pick the rated agent suggestion
    and the user input that preceded it.

    The rated suggestion is the most recent *complete* agent message with text;
    this naturally skips the in-progress assistant turn that is calling this tool
    and the trailing user 'click' message. The preceding user message is the last
    user message before that suggestion (so its attachments are the input files).
    """
    rated_idx: int | None = None
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if m.get("role") == "agent" and m.get("complete") and _extract_text(m.get("content")):
            rated_idx = i
            break
    if rated_idx is None:  # fallback: last agent message regardless of flags
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "agent":
                rated_idx = i
                break

    rated = messages[rated_idx] if rated_idx is not None else None

    preceding = None
    if rated_idx is not None:
        for j in range(rated_idx - 1, -1, -1):
            if messages[j].get("role") == "user":
                preceding = messages[j]
                break

    return {
        "rated_message_id": rated.get("message_id") if rated else None,
        "rated_agent_message": _extract_text(rated.get("content")) if rated else None,
        "preceding_user_message": _extract_text(preceding.get("content")) if preceding else None,
        "input_file_refs": _extract_file_refs(preceding.get("content")) if preceding else [],
    }


# --------------------------------------------------------------------------- #
# Agent-server + Postgres I/O                                                  #
# --------------------------------------------------------------------------- #
def _as_dict(item: Any) -> dict[str, Any]:
    """Normalize an API list item to a plain dict.

    The generated client returns typed models (with ``to_dict``) for some
    responses and already-parsed dicts for others, so handle both.
    """
    to_dict = getattr(item, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    if isinstance(item, dict):
        return item
    raise TypeError(f"Unexpected API item type: {type(item)!r}")


def _fetch_messages(ctx: InvocationContext) -> list[dict[str, Any]]:
    from sema4ai_api_client.api.agents import (
        get_chat_messages_agents_aid_conversations_cid_messages_get as get_messages,
    )
    from sema4ai_api_client.client import AuthenticatedClient
    from sema4ai_api_client.models.error_envelope import ErrorEnvelope

    client = AuthenticatedClient(base_url=ctx.base_url, token=ctx.api_token)
    result = get_messages.sync(aid=ctx.agent_id, cid=ctx.thread_id, client=client)
    if isinstance(result, ErrorEnvelope):
        raise RuntimeError(
            f"Failed to fetch thread messages: {result.error.code}: {result.error.message}"
        )
    data = getattr(result, "data", None) or []
    return [_as_dict(m) for m in data]


def _fetch_data_connections(ctx: InvocationContext) -> list[dict[str, Any]]:
    """List the agent's data connections from the agent server (callback token).

    The data-connections endpoint uses the same AuthedUser dependency as the
    conversation endpoints, so the invocation-context callback token authorizes
    it. Each connection's ``configuration`` carries the postgres credentials.
    """
    from sema4ai_api_client.api.data_connections import (
        list_data_connections_data_connections_get as list_dc,
    )
    from sema4ai_api_client.client import AuthenticatedClient
    from sema4ai_api_client.models.error_envelope import ErrorEnvelope

    client = AuthenticatedClient(base_url=ctx.base_url, token=ctx.api_token)
    result = list_dc.sync(client=client)
    if isinstance(result, ErrorEnvelope):
        raise RuntimeError(
            f"Failed to list data connections: {result.error.code}: {result.error.message}"
        )
    return [_as_dict(c) for c in (result or [])]


def resolve_connection_string(
    headers: Mapping[str, str],
    ctx: InvocationContext,
    fetch_data_connections: Callable[[InvocationContext], list[dict[str, Any]]],
) -> str:
    """Resolve the feedback DB connection string.

    Order: explicit override (X-Pg-Connection-String header, then
    PG_CONNECTION_STRING env) — handy for local dev — otherwise fetch the
    feedback data connection from the agent server's semantic-data-model layer
    so no separate secret is needed in production.
    """
    header_conn = (_get_header_case_insensitive(headers, _PG_HEADER) or "").strip()
    if header_conn:
        return header_conn
    env_conn = (os.environ.get("PG_CONNECTION_STRING") or "").strip()
    if env_conn:
        return env_conn

    name = (os.environ.get(_DATA_CONNECTION_NAME_ENV) or _DEFAULT_DATA_CONNECTION_NAME).strip()
    connection = pick_data_connection(fetch_data_connections(ctx), name)
    if connection is None:
        raise ValueError(
            "Could not resolve a Postgres connection: set PG_CONNECTION_STRING / "
            f"X-Pg-Connection-String, or create the {name!r} data connection on the agent."
        )
    return build_pg_url_from_config(connection.get("configuration") or {})


def _insert_feedback(conn_str: str, row: dict[str, Any]) -> str:
    """Insert a feedback row; return the new row's id."""
    import psycopg2

    conn = psycopg2.connect(conn_str)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into agent_feedback (
                    tenant_id, user_id, agent_id, thread_id, rated_message_id,
                    thumb_up_or_down, notes, rated_agent_message,
                    preceding_user_message, input_file_refs, thread_transcript,
                    source_url
                ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                returning id
                """,
                (
                    row["tenant_id"] or None,
                    row.get("user_id") or None,
                    row["agent_id"],
                    row["thread_id"],
                    row["rated_message_id"],
                    row["thumb_up_or_down"],
                    row["notes"],
                    row["rated_agent_message"],
                    row["preceding_user_message"],
                    json.dumps(row["input_file_refs"]),
                    json.dumps(row.get("thread_transcript") or []),
                    row["source_url"],
                ),
            )
            return str(cur.fetchone()[0])
    finally:
        conn.close()


def _update_feedback_reason(
    conn_str: str, thread_id: str, reason: str, feedback_id: str | None = None
) -> str | None:
    """Attach a reason to a feedback row. If feedback_id is given, target that
    exact row (scoped to this thread); otherwise the most recent feedback in the
    thread. Returns the updated row's id, or None if no matching row exists."""
    import psycopg2

    conn = psycopg2.connect(conn_str)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            if feedback_id:
                cur.execute(
                    "update agent_feedback set notes = %s "
                    "where id = %s and thread_id = %s returning id",
                    (reason, feedback_id, thread_id),
                )
            else:
                cur.execute(
                    """
                    update agent_feedback set notes = %s
                    where id = (
                        select id from agent_feedback
                        where thread_id = %s
                        order by created_at desc
                        limit 1
                    )
                    returning id
                    """,
                    (reason, thread_id),
                )
            updated = cur.fetchone()
            return str(updated[0]) if updated else None
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Server                                                                       #
# --------------------------------------------------------------------------- #
def create_app(
    get_request: Callable[[], Request | None] = get_http_request,
    *,
    fetch_messages: Callable[[InvocationContext], list[dict[str, Any]]] = _fetch_messages,
    fetch_data_connections: Callable[
        [InvocationContext], list[dict[str, Any]]
    ] = _fetch_data_connections,
    insert_feedback: Callable[[str, dict[str, Any]], str] = _insert_feedback,
    update_feedback_reason: Callable[..., str | None] = _update_feedback_reason,
) -> FastMCP:
    mcp = FastMCP("User Feedback")

    def _record(thumb: str, notes: str | None) -> str:
        request = get_request()
        if request is None:
            raise RuntimeError("No HTTP request context available")

        ctx = parse_invocation_context(request.headers)
        conn_str = resolve_connection_string(request.headers, ctx, fetch_data_connections)

        messages = fetch_messages(ctx)
        selected = select_feedback_context(messages)
        row = {
            "tenant_id": ctx.tenant_id,
            "user_id": ctx.user_id,
            "agent_id": ctx.agent_id,
            "thread_id": ctx.thread_id,
            "thumb_up_or_down": thumb,
            "notes": notes,
            "source_url": ctx.base_url,
            "thread_transcript": messages,
            **selected,
        }
        feedback_id = insert_feedback(conn_str, row)

        emoji = "👍" if thumb == "up" else "👎"
        return (
            f"Recorded {emoji} feedback. "
            f"feedback_id={feedback_id} thread_id={ctx.thread_id} "
            f"rated_message_id={row.get('rated_message_id')}"
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))
    def give_thumbs_up(notes: str | None = None) -> str:
        """Record a 👍 (thumbs up) on the agent's previous suggestion.

        Call this only in response to the user clicking the 👍 feedback button.
        The thread/agent are detected automatically; the tool pulls the rated
        suggestion and the preceding user input from the thread and writes the
        record to the feedback database.

        Parameters
        ----------
        notes : str, optional
            Free-text the user added with their thumb.
        """
        return _record("up", notes)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))
    def give_thumbs_down(notes: str | None = None) -> str:
        """Record a 👎 (thumbs down) on the agent's previous suggestion.

        Call this only in response to the user clicking the 👎 feedback button.
        The thread/agent are detected automatically; the tool pulls the rated
        suggestion and the preceding user input from the thread and writes the
        record to the feedback database.

        Parameters
        ----------
        notes : str, optional
            Free-text the user added with their thumb.
        """
        return _record("down", notes)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))
    def add_feedback_reason(reason: str, feedback_id: str | None = None) -> str:
        """Attach a reason to a thumbs feedback in this thread.

        Use this as a follow-up after give_thumbs_up / give_thumbs_down, once the
        user explains why they gave that thumb.

        Parameters
        ----------
        reason : str
            The user's explanation for their thumbs up/down.
        feedback_id : str, optional
            The id returned by give_thumbs_up / give_thumbs_down. Pass it to
            update that exact feedback row. If omitted, the most recent feedback
            in the current thread is updated.
        """
        request = get_request()
        if request is None:
            raise RuntimeError("No HTTP request context available")
        ctx = parse_invocation_context(request.headers)
        conn_str = resolve_connection_string(request.headers, ctx, fetch_data_connections)
        updated_id = update_feedback_reason(conn_str, ctx.thread_id, reason, feedback_id)
        if not updated_id:
            target = f"feedback_id={feedback_id}" if feedback_id else "this thread"
            return f"No matching feedback found for {target} to attach a reason to."
        return f"Saved the reason. feedback_id={updated_id} thread_id={ctx.thread_id}"

    return mcp


def run_http() -> None:
    port = int(os.environ.get("MCP_HTTP_PORT", str(HTTP_PORT)))
    create_app().run(transport="streamable-http", host="0.0.0.0", port=port)


if __name__ == "__main__":
    run_http()
