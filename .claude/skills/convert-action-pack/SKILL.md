---
name: convert-action-pack
description: Convert a Sema4.ai Action pack into a remote MCP server (fastmcp + streamable-HTTP). Handles inventory, @query extraction into Semantic Data Model queries, auth classification (API-key/OAuth/none), platform-context headers, thread-file operations, and scaffold generation. Self-contained — all snippets inlined, no other repo required.
---

# convert-action-pack

Prescriptive workflow for converting a Sema4.ai Action pack into a remote
MCP server. Use this skill when the user hands you a legacy pack and asks
you to migrate it to MCP.

This skill is self-contained. Every code snippet you need — context-header
parser, auth resolvers, `sema4ai-api-client` helpers, tests — is inlined
below.

## 1. Goal

Given a Sema4.ai Action pack at `{pack_path}`, produce:

1. A **migration inventory table** mapping each `@action` to an MCP tool,
   including read/mutate, auth type, platform-context needs, and thread-
   file dependency.
2. If the pack contains `@query` functions: a set of **SDM Verified Query
   definitions** for the user to paste into their agent. `@query`
   functions do not become MCP tools.
3. A **fastmcp MCP server** at `{target_path}` (default:
   `{pack_name}-mcp/` adjacent to the legacy pack) with tests and a
   self-contained dependency setup.
4. A **parity report** listing any action intentionally omitted, merged,
   or renamed.

Sema4.ai supports only remote MCPs (streamable-HTTP transport). Every
output must be a remote-capable server.

## 2. Inputs to confirm with the user before you start

- **Pack path** — e.g. `./gallery/actions/microsoft-sharepoint/`.
- **Target directory** — default is `{pack_name}-mcp/` adjacent to the
  pack; ask if they want something else.
- **Deployment target** (optional at this stage) — Cloud Run, Bedrock
  AgentCore, Azure Container Apps, or multi-MCP gateway. Doesn't change
  the scaffold, but tells you which ingress conventions to mention later.

If the pack path is ambiguous (monorepo with many packs), ask.

## 3. Interactive conduct

This skill runs inside a coding agent (Claude Code by default) with the
user in the loop. Two points in the workflow require explicit user
confirmation:

1. **After the inventory + auth classification, before scaffolding** —
   show the table, ask the user to approve or correct.
2. **Before overwriting any existing file in the target directory** —
   confirm, don't assume.

For everything else (reading legacy source, generating code, running
`uv sync` and tests), proceed unless the user has asked for step-by-step
confirmation.

## 4. Workflow overview

Follow these steps in order:

1. **Inventory** the pack: actions, queries, auth signals, context usage,
   file operations.
2. **Extract `@query` functions** into SDM Verified Query definitions.
3. **Classify auth and context** for each `@action`.
4. **Confirm with the user.** Wait for approval before scaffolding.
5. **Scaffold** the MCP server per the target layout.
6. **Wire up** auth resolution, context parsing, thread-file helpers.
7. **Write tests** — smoke, tools, context (if applicable).
8. **Run the validation gate** — `uv sync`, tests pass, server starts.
9. **Produce the parity report.**
10. **Offer verification** — MCP Inspector locally, then ngrok → Sema4.ai.

## 5. Inventory phase

### 5.1 Read `package.yaml`

Extract:

- `name`, `description`, `version`
- Dependencies (conda + pypi)
- `external-endpoints` (for OAuth or API-access requirements)

### 5.2 Scan the Python sources

For every `@action` function:

- Function name → target MCP tool name (same unless there's a collision).
- Parameters and return type — note `Secret`, `OAuth2Secret`, `Response[T]`,
  `ActionError`, `DataSource` usage.
- `is_consequential` flag → informs `ToolAnnotations(readOnlyHint=…,
  destructiveHint=…)`. Verify against actual behavior; legacy flags are
  occasionally wrong.
- Docstring — preserve operational guidance verbatim where possible.

For every `@query` function: flag separately, handle in step 6.

### 5.3 Detect auth shape

- `OAuth2Secret[...]` anywhere → **OAuth auth**.
- `Secret` (one or more) without OAuth → **API-key auth**.
- Neither → **No auth**.

Count and name all required values. Many packs need two or more — an API
key **plus** a workspace/account/server identifier. Don't miss secondary
values.

### 5.4 Detect platform-context usage

Signals:

- Reads `X-Action-Invocation-Context` header (legacy name — becomes
  `X-Tool-Invocation-Context` in MCP).
- Uses `agent_id`, `thread_id`, `tenant_id`, or
  `invoked_on_behalf_of_user_id` from the invocation context.
- Uses deprecated individual headers — `X-Invoked-By-Assistant-Id`,
  `X-Thread-Id`, and similar. These are gone; all platform context now
  comes through the single base64-encoded `X-Tool-Invocation-Context`
  header.

If any signal fires, add a **platform-context** overlay to the
classification.

### 5.5 Detect thread-file operations

Signals:

- `from sema4ai.actions import chat` or
  `from sema4ai.actions.chat import ...`.
- Calls to `chat.get_file`, `chat.get_file_content`, `chat.attach_file`,
  `chat.attach_file_content`.

If any fire, add a **thread-files overlay** (implies platform-context
overlay).

### 5.6 Flag platform-sensitive dependencies

Browser automation (Playwright), OCR, native binaries, Windows-only Excel
COM — all need extra container work. Mark the pack **runtime-sensitive**
and note the dependencies so the scaffold includes them.

### 5.7 Build the inventory table

Emit a markdown table:

| Legacy action | Target tool name | Read/mutate | Auth type | Platform context? | Uses thread files? | Notes |
| --- | --- | --- | --- | --- | --- | --- |

List `@query` functions separately — they don't belong in the main
inventory.

## 6. `@query` → SDM Verified Query extraction

`@query` functions do not migrate to MCP tools. They become **SDM Verified
Queries** in the user's agent.

### 6.1 When it's SDM vs. when it stays an MCP tool

- **Parameterized SQL** (conditional `WHERE` building, light date math,
  string interpolation) → **SDM Verified Query**. Most cases.
- **Heavy custom Python** (complex post-processing, multi-step
  transformations, API calls mixed with SQL) → **MCP tool**. Rare —
  default to SDM unless you see real Python work beyond what SQL can do.

### 6.2 Extraction format

For each SDM-bound `@query`:

- **Name**: function name.
- **Description**: docstring first line.
- **Data source**: from `data_sources.py` (engine, name, description).
- **Parameters**: extracted from the Pydantic param model, with types
  mapped (`date` → `string (YYYY-MM-DD)`, `Optional[X]` → `X (optional)`).
  Preserve descriptions from `Field(description=...)`.
- **SQL**: from the function body, with these transformations:
  - `$variable` → `:variable`.
  - Flatten dynamic `WHERE` clauses (`where_conditions.append(...)`) into
    static SQL with all possible conditions joined by `AND`. Mark each
    condition's parameters optional.
  - Drop Python string formatting (`f"""..."""`); output plain SQL.
  - Preserve table and schema references exactly.

### 6.3 One data source per SDM

SDM supports one database connection per SDM instance. Group queries by
data source — each group becomes one SDM. If a `@query` joins across two
data sources, it **cannot** be a single Verified Query. Flag it to the
user as either (a) splittable, or (b) needing an MCP-tool conversion
(rare).

### 6.4 Output shape

Present each extracted query as a pasteable block:

```text
Name: get_studio_users
Description: Get Studio users with optional filtering by date range, company, and role.
Data Source: studio_users (redshift)

Parameters:
  - start_date (string, optional): Start date (YYYY-MM-DD)
  - end_date   (string, optional): End date (YYYY-MM-DD)
  - company_name (string, optional): Partial-match company name
  - role (string, optional): Filter by user role

SQL:
  SELECT source_id, email, name, company_name, role, registration_date
  FROM studio_users.studio_users
  WHERE registration_date >= :start_date
    AND registration_date <  :end_date
    AND UPPER(company_name) LIKE UPPER(:company_name)
    AND role = :role
  ORDER BY registration_date DESC
```

Ask the user how their SDM engine handles optional/unset parameters —
the `WHERE` clause may need adjustment.

### 6.5 Computed parameters

Some queries compute derived values in Python
(`end_date_plus_one = end_date + timedelta(days=1)`). Flag these — they
need either an SQL adjustment (`:end_date + INTERVAL '1 day'`) or a
parameter rename to make the intent clear.

### 6.6 If the pack is entirely `@query`

No MCP server is needed. Output all Verified Query definitions and tell
the user: "This pack is entirely data queries. Add them as Verified
Queries in your agent's Semantic Data Model configuration. No MCP server
to build."

## 7. Auth and context classification (coverage matrix)

| Auth type | No context        | Context only      | Context + thread files     |
| --------- | ----------------- | ----------------- | -------------------------- |
| OAuth     | OAuth             | OAuth + Context   | OAuth + Thread files       |
| API-key   | API-key           | API-key + Context | API-key + Thread files     |
| No auth   | No auth           | No auth + Context | No auth + Thread files     |

Pick one row × column combination per tool, or per server when consistent.

## 8. Target layout

```
{target_path}/
├── server.py                entry point — binds port, runs mcp.run()
├── pyproject.toml
├── uv.lock                  generated by `uv sync`
├── models.py                optional — Pydantic models for complex tools
├── client.py                optional — vendor SDK / HTTP client wrapper
├── agent_server_context.py  only if thread-files overlay (see 9.5)
├── agent_server_helper.py   only if thread-files overlay (see 9.5)
└── tests/
    ├── conftest.py
    ├── test_smoke.py
    ├── test_tools.py
    └── test_context.py      only if context / thread-files overlay
```

Naming:

- Directory: kebab-case, typically `{service}-mcp` (e.g.
  `microsoft-sharepoint-mcp`).
- `pyproject.toml` project name: `mcp-{service}` (e.g.
  `mcp-microsoft-sharepoint`) to avoid PyPI collisions with vendor SDKs.

Keep it flat — no `src/` layout, no `create_app()` / `run_http()`
wrapper. Simpler review.

## 9. Action → tool mapping rules

### 9.1 Decorator

- Legacy `@action(is_consequential=False)` →
  `ToolAnnotations(readOnlyHint=True, destructiveHint=False)`.
- Legacy `@action(is_consequential=True)` →
  `ToolAnnotations(readOnlyHint=False, destructiveHint=True)`.

This is a starting point, not a mechanical rule. The final annotation must
match the tool's actual behavior — legacy flags are occasionally wrong.
Trust the code, not the decorator.

### 9.2 Signatures

- Prefer **one Pydantic input model** for non-trivial tools.
- Keep scalar args only for tools with 1–2 primitive parameters.

### 9.3 Return types

- Replace `Response[T]` wrappers with plain typed returns (Pydantic model
  or scalar).
- Keep output schemas deterministic — don't return `dict` when a model
  fits.

### 9.4 Errors

- Replace `ActionError` with standard Python exceptions: `ValueError` for
  bad input, `RuntimeError` for unexpected state, HTTP-client exceptions
  for upstream failures.
- Keep error messages descriptive — they surface to the Sema4.ai agent.

### 9.5 Docstrings

- Keep operational guidance in tool docstrings. They matter more than
  they did in `package.yaml` — the Sema4.ai agent reads them when
  deciding which tool to call.

## 10. Auth migration — inline patterns

Use the snippet that matches the classification.

### 10.1 API-key auth

Read from the request header first; fall back to an env var for local
dev; fail with a clear message if neither is present.

```python
import os
from fastmcp.server.dependencies import get_http_request


def _require_api_key() -> str:
    request = get_http_request()
    key = request.headers.get("X-Api-Key", "").strip()
    if key:
        return key
    env_key = os.environ.get("MY_SERVICE_API_KEY", "").strip()
    if env_key:
        return env_key
    raise ValueError(
        "API key required — send X-Api-Key header, or set MY_SERVICE_API_KEY for local dev."
    )
```

Some providers need multiple values (API key **plus** workspace ID).
Handle each independently — one resolver per required value.

### 10.2 OAuth auth (forwarded bearer)

The common shape: the Sema4.ai agent performs the OAuth dance, then
forwards the bearer token in the `Authorization` header. Your MCP uses
it directly.

```python
from fastmcp.server.dependencies import get_http_request


def _require_bearer() -> str:
    request = get_http_request()
    auth = request.headers.get("Authorization", "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    raise ValueError(
        "Missing OAuth token — the Sema4.ai agent must forward Authorization: Bearer …"
    )
```

For OAuth servers where the MCP itself validates JWTs against an issuer,
use fastmcp's built-in `JWTVerifier` — see the fastmcp docs; it's
constructed with `FastMCP(auth=JWTVerifier(...))`.

### 10.3 No auth

Don't invent auth requirements for packs that had none. Keep the tool
signatures auth-free.

### 10.4 Platform context (no thread files)

Parse `X-Tool-Invocation-Context` directly. No `sema4ai-api-client`
dependency needed.

```python
import base64
import json
from fastmcp.server.dependencies import get_http_request


def _invocation_context() -> dict:
    """Parse the Sema4.ai platform context from X-Tool-Invocation-Context."""
    request = get_http_request()
    raw = request.headers.get("X-Tool-Invocation-Context", "").strip()
    if not raw:
        return {}
    try:
        decoded = base64.b64decode(raw).decode("utf-8")
        parsed = json.loads(decoded)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _current_agent_id() -> str:
    """Return the agent ID, or a safe default for local dev."""
    return _invocation_context().get("agent_id") or "local_testing"


def _current_thread_id() -> str:
    """Return the thread ID, or raise if the caller needs it but didn't send it."""
    thread_id = _invocation_context().get("thread_id")
    if not thread_id:
        raise ValueError(
            "Missing thread_id in X-Tool-Invocation-Context — required for this tool."
        )
    return thread_id
```

- **Safe defaults for local dev.** For fields like `agent_id`, default to
  `"local_testing"` so the server runs without the header.
- **Strict when required.** For fields the tool cannot function without
  (e.g. `thread_id` for per-thread memory partitioning), raise clearly.

### 10.5 Thread-files overlay (Agent Server callbacks)

When the legacy pack uses `sema4ai.actions.chat.*`, the MCP needs to call
back into the Sema4.ai Agent Server API for file uploads and downloads.
This requires:

- The `sema4ai-api-client` PyPI package as a dependency.
- A `ContextVar` that binds the incoming request headers to the tool
  call, so helper functions can read them without explicit parameter
  threading.

Place these two files alongside `server.py`.

#### `agent_server_context.py`

```python
"""Per-request Sema4.ai platform-context binding for tool handlers."""
from __future__ import annotations

import base64
import contextvars
import json
from typing import Any

from sema4ai_api_client import AuthenticatedClient

_headers_ctx: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "agent_server_headers", default=None
)


def bind_request_headers(headers) -> contextvars.Token:
    """Bind the incoming request headers for the duration of a tool call."""
    normalized = {k.lower(): v for k, v in headers.items()}
    return _headers_ctx.set(normalized)


def reset_request_headers(token: contextvars.Token) -> None:
    _headers_ctx.reset(token)


def _require_headers() -> dict[str, str]:
    headers = _headers_ctx.get()
    if headers is None:
        raise RuntimeError(
            "No request headers bound — call bind_request_headers() first."
        )
    return headers


def current_invocation_data() -> dict[str, Any]:
    """Decode X-Tool-Invocation-Context as a dict. Returns {} if missing/invalid."""
    raw = _require_headers().get("x-tool-invocation-context", "").strip()
    if not raw:
        return {}
    try:
        return json.loads(base64.b64decode(raw).decode("utf-8"))
    except Exception:
        return {}


def current_client_agent_and_thread_id() -> tuple[AuthenticatedClient, str, str]:
    """Build a Sema4.ai Agent Server API client from the current invocation context.

    Returns (client, agent_id, thread_id). Raises RuntimeError if any required
    field is missing.
    """
    ctx = current_invocation_data()
    api_url = ctx.get("agent_server_api_url")
    api_token = ctx.get("agent_server_api_token")
    agent_id = ctx.get("agent_id")
    thread_id = ctx.get("thread_id")

    missing = [
        name
        for name, value in (
            ("agent_server_api_url", api_url),
            ("agent_server_api_token", api_token),
            ("agent_id", agent_id),
            ("thread_id", thread_id),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"Missing required platform context fields: {', '.join(missing)}"
        )

    client = AuthenticatedClient(base_url=api_url, token=api_token)
    return client, agent_id, thread_id
```

#### `agent_server_helper.py`

```python
"""Thread-file upload / download helpers — wraps sema4ai-api-client."""
from __future__ import annotations

from agent_server_context import current_client_agent_and_thread_id


def attach_file_content(name: str, data: bytes, content_type: str) -> list[dict]:
    """Upload bytes as a thread file. Returns the Agent Server's file descriptor list."""
    client, agent_id, thread_id = current_client_agent_and_thread_id()
    # Exact method surface varies by sema4ai-api-client version.
    # Replace with the current SDK signature if it has evolved.
    response = client.threads.attach_file(
        agent_id=agent_id,
        thread_id=thread_id,
        file_name=name,
        file_bytes=data,
        content_type=content_type,
    )
    response.raise_for_status()
    return response.parsed or []


def get_file_content(file_ref: str) -> bytes:
    """Download a thread file by reference."""
    client, agent_id, thread_id = current_client_agent_and_thread_id()
    response = client.threads.download_file(
        agent_id=agent_id,
        thread_id=thread_id,
        file_reference=file_ref,
    )
    response.raise_for_status()
    return response.content
```

> The `sema4ai-api-client` API evolves; treat the calls above as the
> shape of the thing. Check the installed SDK for the current method
> names and adjust.

#### Binding in `server.py`

Wrap every tool that uses context or thread files:

```python
from collections.abc import Iterator
from contextlib import contextmanager

from fastmcp.server.dependencies import get_http_request

from agent_server_context import bind_request_headers, reset_request_headers
from agent_server_helper import attach_file_content


@contextmanager
def _bind_request_context() -> Iterator[None]:
    request = get_http_request()
    if request is None:
        raise RuntimeError("No HTTP request context available")
    token = bind_request_headers(request.headers)
    try:
        yield
    finally:
        reset_request_headers(token)


@mcp.tool()
def attach_report(name: str, data: bytes) -> dict:
    """Attach a generated report to the current thread."""
    with _bind_request_context():
        result = attach_file_content(name, data, "application/pdf")
    return {"attached": result}
```

### 10.6 Legacy call → MCP helper mapping

| Legacy call                                     | MCP equivalent                                    |
| ----------------------------------------------- | ------------------------------------------------- |
| `chat.attach_file_content(name, data, ...)`     | `agent_server_helper.attach_file_content(...)`    |
| `chat.get_file_content(file_ref)`               | `agent_server_helper.get_file_content(...)`       |
| `chat.get_file(...)`                            | `agent_server_helper.get_file_content(...)`       |
| `X-Action-Invocation-Context` header            | `X-Tool-Invocation-Context` (same base64 format)  |
| Individual `X-Invoked-By-Assistant-Id` etc.     | Parse from `X-Tool-Invocation-Context`            |

### 10.7 Securing the MCP server itself with Entra ID (machine auth + auth code)

Sections 10.1–10.4 cover auth **to upstream APIs**. When the MCP server itself must
require OAuth2 (Azure AD / Entra ID), use FastMCP's `AzureProvider` — never hand-roll
JWT validation (Entra publishes ~5 rotating signing keys; the key must be selected by
the token's `kid`, which the provider does automatically).

**Entra setup**: five non-obvious properties are required; missing any one yields an
opaque `invalid_token`. Use the tested Bicep template in
`templates/entra-mcp-server-oauth/` (two-pass deploy, README has CLI quick start +
troubleshooting table). The five, for reference:

1. `requestedAccessTokenVersion: 2` — else even the v2 endpoint issues v1 tokens
   (`iss: sts.windows.net/...`) that fail issuer validation
2. Delegated scope (e.g. `invoke`) → auth-code tokens' `scp` claim
3. App role (e.g. `invoke.app`) **assigned to the app's own service principal** →
   client-credentials tokens' `roles` claim (absent without the self-assignment)
4. Identifier URI in the `api://{client_id}` form (tenant policy rejects vanity names)
5. Redirect URI `{base_url}/auth/callback`

**Server code** — two adjustments are mandatory for machine auth:

```python
from fastmcp.server.auth.providers.azure import AzureProvider

class AzureHybridProvider(AzureProvider):
    """AzureProvider is an OAuth proxy: it issues its own tokens (auth code flow)
    and by design rejects raw Entra tokens. Also accept direct bearer tokens
    (client credentials / machine auth)."""
    async def load_access_token(self, token):
        return (await super().load_access_token(token)
                or await self._token_validator.verify_token(token))

auth = AzureHybridProvider(client_id=..., client_secret=..., tenant_id=...,
                           required_scopes=["invoke"],
                           base_url=os.environ["PUBLIC_BASE_URL"])
# CC tokens carry `roles`, never `scp`; FastMCP only reads scope/scp:
_orig = auth._token_validator._extract_scopes
auth._token_validator._extract_scopes = lambda c: (
    _orig(c) or ["invoke" if r == "invoke.app" else r for r in c.get("roles", [])])
```

**Client config**: machine auth uses scope `api://{client_id}/.default` (named scopes
are rejected for client credentials with `AADSTS70011`); auth-code clients need only
the `/mcp` URL — RFC 9728/8414 discovery + DCR are served by FastMCP.

**Validation — the negative test is mandatory**: `POST /mcp` with no credentials must
return **401** with a `WWW-Authenticate` challenge. An auth test that passes while the
no-credentials probe returns 200 means auth silently failed to initialize — a false
positive. Then verify a real client-credentials token completes `initialize`, and that
`/.well-known/oauth-protected-resource/mcp` resolves. Debug auth **locally** before any
image build — deploy loops are minutes and blind; local is seconds with full logs.

## 11. `pyproject.toml`

Base:

```toml
[project]
name = "mcp-{service-name}"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastmcp>=2.3",
    "pydantic>=2",
]
```

Add when relevant:

- Thread-files overlay → `"sema4ai-api-client"`.
- Vendor SDK → e.g. `"msgraph-sdk"` for Microsoft Graph.
- HTTP client → `"httpx"` (prefer over `requests` for async / streaming).
- OAuth JWT verification → `"pyjwt[crypto]"`.

Commit `uv.lock` after `uv sync`.

## 12. `server.py` skeleton

```python
import fastmcp

mcp = fastmcp.FastMCP("my-service")


@mcp.tool()
def ping() -> str:
    """Return pong. Used for health checks and local smoke tests."""
    return "pong"


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8067)
```

- **Transport**: always `streamable-http`. Stdio is not supported by
  Sema4.ai.
- **Path**: `/mcp` is the fastmcp default endpoint path.
- **Port**: 8067 is a Sema4.ai convention; any port works locally. The
  deployment's ingress port is what matters in production.

## 13. Tests

Minimum set:

### `test_smoke.py`

```python
import server


def test_tools_listed():
    names = {tool.name for tool in server.mcp._tool_manager._tools.values()}
    assert "ping" in names  # replace with the tools you actually scaffolded
```

(Internal attribute access is fragile; if fastmcp exposes a stable
enumeration API in your version, prefer that.)

### `test_tools.py`

- Exercise each tool with mocked dependencies (vendor SDK, HTTP client).
- Verify auth resolution behavior:
  - API-key — header-first, env-fallback, clear missing-value error.
  - OAuth — bearer resolution, clear missing-token error.
  - No auth — tools run without auth headers.
- Verify returned shapes match the expected schema.

### `test_context.py` (only if context / thread-files overlay)

- `current_invocation_data()` with valid base64 → expected dict.
- Missing header → `{}`.
- Malformed base64 → `{}`.
- Missing required fields (`agent_id`, `thread_id`, `agent_server_api_url`,
  `agent_server_api_token`) → `RuntimeError` with clear message.

## 14. Pitfalls — things that cost an afternoon

1. **Forgetting `sema4ai-api-client`** for packs that used `chat.*` APIs.
2. **Binding helpers but not calling `_bind_request_context`** around the
   tool body.
3. **OAuth bearer not resolved** — some ingress configurations strip the
   `Authorization` header by default. Check your ingress.
4. **Missing secondary required `Secret` values** — workspace/account/
   server identifiers are easy to overlook alongside the primary API key.
5. **Mislabeling mutating tools as read-only.** Agents may skip retry
   protection or consequential-action warnings. Double-check every
   annotation.
6. **Dropping actions silently without documenting.** If you merge or
   omit a tool, note it in the parity report.
7. **Container dependencies missing** for browser/OCR/native packs.
8. **Using deprecated individual platform headers**
   (`X-Invoked-By-Assistant-Id`, `X-Thread-Id`). Only
   `X-Tool-Invocation-Context` is current.
9. **Using the legacy header name** `X-Action-Invocation-Context`. It's
   `X-Tool-Invocation-Context` in MCP.
10. **Converting `@query` functions to MCP tools.** They're SDM Verified
    Queries (rare exceptions aside).
11. **Forgetting remote-only.** Sema4.ai only supports streamable-HTTP
    MCPs — the scaffold's `mcp.run()` must use
    `transport="streamable-http"`. Stdio won't register.

## 15. Validation gate

Before reporting the migration complete:

- [ ] `uv sync` succeeds in `{target_path}/`.
- [ ] `pytest` passes (at minimum the smoke test).
- [ ] `python server.py` starts and serves `/mcp`.
- [ ] Tool list matches the inventory table (or documented deltas).
- [ ] Auth failure paths return clear errors, not 500s.
- [ ] Thread-file flows read/upload successfully against a real Agent
      Server (if the pack had thread files).
- [ ] Parity report delivered.

## 16. Parity report

Produce a short report at the end of the migration:

- **Pack path**: `…`
- **Target**: `…`
- **Tools migrated**: N (list names).
- **Actions omitted**: M (list with reason — deprecated, subsumed, moved
  to SDM, etc.).
- **SDM Verified Queries extracted**: K (list names + data sources).
- **Auth classification**: summary per tool.
- **Known deltas**: anything the user should review before deploying.

## 17. Verification offer

After the validation gate passes, offer to run the verification loop with
the user:

1. Start `python server.py` and point **MCP Inspector**
   (`npx @modelcontextprotocol/inspector`) at `http://localhost:8067/mcp`
   to spot-check each tool.
2. Run **ngrok** (`ngrok http 8067`) and register the tunnel URL on the
   user's Sema4.ai agent for a full-loop test.

Both steps are documented in `docs/04-migration-workflow.md`. The user
may want to drive them manually, but offering to run them is the
default.

## 18. User launch prompt

If the user hands you a pack and expects the full workflow without
further prompting, this is the equivalent prompt:

> Migrate the action pack at `{path}` to a remote MCP server using the
> convert-action-pack skill. Produce the inventory, extract any `@query`
> functions as SDM definitions, classify auth per tool, confirm with me
> before scaffolding, then scaffold, wire up auth/context, write tests,
> and deliver a parity report.

Work step by step; pause for user confirmation between the classification
and scaffolding phases.
