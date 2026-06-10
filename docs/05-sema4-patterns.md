# Sema4.ai-specific patterns

Three integration points matter when the Sema4.ai agent calls your MCP:
the per-request **context header**, the **auth** shape, and **thread-
file** upload/download. This page is a conceptual reference; for code
see the [`convert-action-pack`](../.claude/skills/convert-action-pack/SKILL.md)
skill (sections 9.1–9.5) and the
[worked SharePoint migration](../examples/worked-migration/).

For a focused, runnable reference of these three points on their own —
context, thread dataframes, and thread files as six small tools — see the
[agent-server-example](../examples/agent-server-example/).

## Context: `X-Tool-Invocation-Context`

One base64-encoded JSON header carries every piece of platform context
your tool might need. Decoded:

```json
{
  "agent_id": "4b0ec5bf-…",
  "thread_id": "7f3a19c2-…",
  "tenant_id": "8f1d5a60-…",
  "invoked_on_behalf_of_user_id": "user-42",
  "agent_server_api_url": "https://agents.company.example.com",
  "agent_server_api_token": "sat_…"
}
```

Fields are optional at the protocol level — tolerate missing keys.

| Field | Meaning | Usually required? |
| --- | --- | --- |
| `agent_id` | ID of the Sema4.ai agent making the call. | Optional; safe default for local dev. |
| `thread_id` | Conversation thread ID. | Required for per-thread state (memory, file attachments). |
| `tenant_id` | Tenant / organization ID. | Optional. Useful for multi-tenant partitioning. |
| `invoked_on_behalf_of_user_id` | End-user ID the agent is acting for. | Optional. Metadata only — not an identity claim. |
| `agent_server_api_url` | Callback URL for the Sema4.ai Agent Server API. | Required for the thread-files overlay. |
| `agent_server_api_token` | Auth token for Agent Server callbacks. | Required for the thread-files overlay. |

The legacy name `X-Action-Invocation-Context` and the individual legacy
headers (`X-Invoked-By-Assistant-Id`, `X-Thread-Id`, …) are gone —
don't use them in new code.

### Two parsing patterns

- **Direct parse** — stdlib only. Use when your tool reads a field or
  two and doesn't call back into the Agent Server. See skill
  section 9.4.
- **ContextVar overlay** — binds the full header dict to a
  `ContextVar` so helpers deep in the call stack reach it without
  explicit threading. Use when you also upload/download thread files.
  See skill section 9.5 and
  [`agent_server_context.py`](../examples/worked-migration/microsoft-sharepoint-mcp/agent_server_context.py)
  in the worked example.

**Rule of thumb**: safe defaults for identity / telemetry fields (e.g.
`agent_id` → `"local_testing"`), strict errors for load-bearing fields
(e.g. missing `thread_id` on a memory-partitioning tool should fail
loudly).

### Security

- Don't log the raw header or the decoded JSON —
  `agent_server_api_token` is a credential.
- Don't trust `invoked_on_behalf_of_user_id` for authorization; it's
  metadata, not an identity claim.
- Don't echo the context back in error messages or tool results.

## Auth

Most migrations land on one of four patterns:

| Pattern | When | Where to look |
| --- | --- | --- |
| **Forwarded bearer** | Legacy `OAuth2Secret[...]`. The Sema4.ai agent runs the OAuth dance upstream and forwards the token on `Authorization`. | Skill 9.2; `_require_bearer()` in the [SharePoint `server.py`](../examples/worked-migration/microsoft-sharepoint-mcp/server.py). |
| **`JWTVerifier`** | Your MCP itself validates tokens against an issuer/audience (scope checks, resource-server role). | `fastmcp.server.auth.JWTVerifier` — see the fastmcp docs. |
| **API-key** | Legacy `Secret` values. Read a header (e.g. `X-Api-Key`) → fall back to env var → fail cleanly. Handle multi-value secrets (key + workspace ID) independently. | Skill 9.1. |
| **No auth** | Legacy pack had no secrets. Don't invent requirements. | — |

Every pattern should support an env-var fallback for local dev so
`python server.py` + MCP Inspector works without the agent in the loop.
Document the env-var names in your MCP's README.

**Forwarded bearer assumes a user is present.** It fits a *conversational*
agent. A *worker* agent (triggers / schedule, no interactive user at run
time) can't run the OAuth dance on demand — provision a non-interactive
credential (a service / long-lived token, or the provider's
client-credentials flow) and register the MCP with `org_secret` rather than
`user_oauth`. [`analyze-agent-zip`](../.claude/skills/analyze-agent-zip/SKILL.md)
flags this from the agent's run model.

### OAuth scope consolidation

The biggest quiet shift from actions to MCP.

Legacy packs declare scopes **per action**:

```python
@action
def search_for_site(..., token: OAuth2Secret[..., ["Sites.Read.All"]]): ...

@action
def create_sharepoint_list(..., token: OAuth2Secret[..., ["Sites.Manage.All"]]): ...
```

MCP servers register the OAuth client **once**, with a **union** of
scopes covering every tool. Per-tool least-privilege moves upstream:
either split the MCP into two servers (read-only + mutation), or
enforce at the agent-policy layer. The MCP itself doesn't know which
scopes its bearer has unless it calls an introspection endpoint.

### Gotchas and security

- **Ingress strips `Authorization`** in some nginx configs and cloud
  gateways. Before deploying, send a bearer through and log what the
  MCP actually sees.
- **Headers only** for tokens — never query parameters. Cached URLs and
  proxy logs leak query strings.
- **Redact** `Authorization` / `X-Api-Key` before logging requests.
- **Error messages name what is missing, not why.** "Missing bearer" is
  useful; internal crypto details are a reconnaissance aid.

## Thread files

Replace `sema4ai.actions.chat.*` with a callback into the Sema4.ai
Agent Server API, using `sema4ai-api-client` plus the ContextVar
overlay above.

### Why a callback

Action Server ran in-process with the agent runtime, so `chat.*` was a
local call. MCP servers run remotely, so attaching a file to a thread
is an HTTP callback into the Agent Server — scoped by `agent_id` and
`thread_id`, authenticated with `agent_server_api_token`, targeted at
`agent_server_api_url`. All four arrive via `X-Tool-Invocation-Context`.

### The overlay files

Two plumbing files live alongside `server.py`, copied verbatim from the
skill — no service-specific logic in them:

- [`agent_server_context.py`](../examples/worked-migration/microsoft-sharepoint-mcp/agent_server_context.py)
  — ContextVar binding, header parsing, `AuthenticatedClient` factory.
- [`agent_server_helper.py`](../examples/worked-migration/microsoft-sharepoint-mcp/agent_server_helper.py)
  — `attach_file_content(name, data, content_type)` and
  `get_file_content(file_ref)`.

### Request-binding context manager

Every tool that uses the helpers wraps its body in
`_bind_request_context()`. The context manager ensures helpers reach
the right headers and that the binding clears after the tool returns
(important under concurrent requests). Pattern + usage:
[SharePoint `server.py`](../examples/worked-migration/microsoft-sharepoint-mcp/server.py)
(`download_sharepoint_file`, `upload_file_to_sharepoint`).

**Keep the wrap surgical** — only wrap tools that actually call the
helpers. Wrapping everything adds overhead and obscures errors.

### Legacy → MCP mapping

| Legacy call | MCP equivalent |
| --- | --- |
| `chat.attach_file_content(name, data, ...)` | `attach_file_content(name=…, data=…, content_type=…)` inside `_bind_request_context()` |
| `chat.get_file_content(file_ref)` | `get_file_content(file_ref)` inside `_bind_request_context()` |
| `chat.get_file(…)` | `get_file_content(…)` — legacy `get_file` + `get_file_content` collapse to one call |
| `chat.attach_file(path)` | Read the bytes yourself, then `attach_file_content(...)` — the helper is content-based, not path-based |

### Content types and size limits

Be specific with MIME types — agents make downstream decisions based on
them. Use `application/octet-stream` as the honest fallback; prefer it
over a wrong guess.

The helpers are bytes-in / bytes-out, fine for files under a few MB.
For larger payloads: split into multiple attachments, rely on the Agent
Server's size ceiling (enforced server-side), or use streaming
primitives if `sema4ai-api-client` exposes them in your version. Memory
is the practical bound — don't load a 2 GB file just to attach it.

### Testing without a real Agent Server

Fabricate the context header, or monkeypatch the helper functions. The
worked migration's
[`tests/test_context.py`](../examples/worked-migration/microsoft-sharepoint-mcp/tests/test_context.py)
covers valid / malformed / missing / partially-filled headers;
[`tests/test_tools.py`](../examples/worked-migration/microsoft-sharepoint-mcp/tests/test_tools.py)
shows a no-op `_bind_request_context` stub alongside a monkeypatched
`attach_file_content`.

### Pitfalls

- **Forgetting `_bind_request_context()`** — helper raises
  `RuntimeError("No request headers bound — …")`. If you see that, a
  tool is missing the wrap.
- **Wrapping every tool by default** — extra overhead, worse errors.
- **Missing `sema4ai-api-client` in `pyproject.toml`** — the import
  fails at tool-call time, not server startup.
- **Logging bytes** — filename and size only, never content.

## Data connections (a database with no DB secret)

When a migrated MCP needs a **database**, you don't have to hand it a
separate DB secret. The same callback token that powers the thread-files
overlay also authorizes the Agent Server's **data-connections** endpoint —
so the MCP can read the agent's already-configured data connection at call
time and build its connection string from that.

The flow, on each tool call:

1. Parse `X-Tool-Invocation-Context` for `agent_server_api_url` +
   `agent_server_api_token` (same as the thread-files overlay).
2. `GET` the agent's data connections, pick the one by name (e.g.
   `agent-feedback-neon`), and read its `configuration`
   (host / port / database / user / password).
3. Build the connection string and connect.

Keep an explicit-override order for local dev — a connection-string header,
then an env var, then the data-connection lookup — so `python server.py`
works without the agent in the loop. The MCP then needs **no DB secret of
its own**; the data connection is the single source of truth (and the same
one a reporting SDM reads).

Worked end to end in the [feedback-mcp example](../examples/feedback-mcp/)
(`resolve_connection_string` in its `server.py`), which also ships a
read-only reporting SDM and two agents that consume the MCP.
