# Worked migration: Microsoft SharePoint

Walk-through of the [`convert-action-pack`](../../.claude/skills/convert-action-pack/SKILL.md)
skill applied end to end to a real Sema4.ai action pack — **Microsoft
SharePoint**. Twelve OAuth-authenticated actions covering site lookup,
list CRUD, and file operations (including thread-file upload/download
through the Sema4.ai Agent Server API).

Read this as:
- **A reference** when migrating your own pack — see what the output of
  each skill step actually looks like.
- **A starting point** — [`microsoft-sharepoint-mcp/`](microsoft-sharepoint-mcp/)
  is a runnable scaffold you can clone and adapt.

## What we're migrating

The legacy pack at `gallery/actions/microsoft-sharepoint/` (snapshot in
[`legacy-snapshot/`](legacy-snapshot/)) has:

- **Version**: 3.1.1, `spec-version: v2`, `sema4ai-actions=1.6.6`.
- **Twelve `@action` functions** across three modules:
  - `sharepoint_site_action.py` — 3 read actions (search, get, list sites).
  - `sharepoint_list_action.py` — 6 actions (read + create list, add/update/delete items).
  - `sharepoint_file_action.py` — 3 actions (search, download, upload). The
    download and upload use `sema4ai.actions.chat.*` for thread files.
- **Auth**: `OAuth2Secret[Literal["microsoft"], list[Literal["..."]]` with
  per-action scopes — `Sites.Read.All`, `Sites.Manage.All`, `Files.Read*`,
  `Files.ReadWrite`.
- **HTTP**: direct Microsoft Graph API calls via `sema4ai_http`.

Example legacy action (from `sharepoint_site_action.py`):

```python
@action
def search_for_site(
    search_string: str,
    token: OAuth2Secret[
        Literal["microsoft"],
        list[Literal["Sites.Read.All"]],
    ],
) -> Response[dict]:
    """Search for a Sharepoint site by name or by domain/hostname."""
    headers = build_headers(token)
    ...
    return Response(result=response_json)
```

## Commit-by-commit

### Commit 1 — `feat: inventory the legacy pack`

Claude Code reads the legacy pack and produces the inventory table. No
omissions — every action maps 1:1 to an MCP tool of the same name.

| Legacy action | Target tool name | Read/mutate | Auth type | Platform context? | Uses thread files? | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `search_for_site` | `search_for_site` | read | OAuth | no | no | Sites.Read.All |
| `get_sharepoint_site` | `get_sharepoint_site` | read | OAuth | no | no | Sites.Read.All |
| `get_all_sharepoint_sites` | `get_all_sharepoint_sites` | read | OAuth | no | no | Sites.Read.All |
| `get_sharepoint_lists` | `get_sharepoint_lists` | read | OAuth | no | no | Sites.Read.All |
| `create_sharepoint_list` | `create_sharepoint_list` | mutating | OAuth | no | no | Sites.Manage.All |
| `add_sharepoint_list_item` | `add_sharepoint_list_item` | mutating | OAuth | no | no | Sites.Manage.All |
| `update_sharepoint_list_item` | `update_sharepoint_list_item` | mutating | OAuth | no | no | Sites.Manage.All |
| `delete_sharepoint_list_item` | `delete_sharepoint_list_item` | mutating | OAuth | no | no | Sites.Manage.All |
| `get_sharepoint_list_items` | `get_sharepoint_list_items` | read | OAuth | no | no | Sites.Read.All |
| `search_sharepoint_files` | `search_sharepoint_files` | read | OAuth | no | no | Files.Read.All |
| `download_sharepoint_file` | `download_sharepoint_file` | read | OAuth | yes | **yes** | Files.Read; attaches to thread |
| `upload_file_to_sharepoint` | `upload_file_to_sharepoint` | mutating | OAuth | yes | **yes** | Files.ReadWrite; reads from thread |

**No `@query` functions**, so nothing to extract as SDM Verified Queries.

**Scope consolidation.** The legacy pack declared per-action scopes; the
MCP surfaces a single OAuth grant that includes every scope the server's
tools can need. Gallery operators register the aggregated scope string on
the OAuth client once.

### Commit 2 — `feat: classify auth and context`

One server-wide classification applies to all tools:

- **Auth**: OAuth with forwarded bearer. The Sema4.ai agent performs the
  OAuth dance upstream and forwards `Authorization: Bearer …` with each
  tool call.
- **Platform context**: only needed by the two file tools, for the Agent
  Server callback URL and token.
- **Thread-files overlay**: only `download_sharepoint_file` (attaches a
  downloaded file to the thread) and `upload_file_to_sharepoint` (reads
  a thread-attached file to upload to SharePoint).

Everything else needs auth but no context or thread files.

### Commit 3 — `feat: scaffold the MCP project`

```
microsoft-sharepoint-mcp/
├── pyproject.toml            fastmcp, pydantic, httpx, sema4ai-api-client
├── server.py                 entry point + all 12 tools
├── sharepoint_client.py      thin Microsoft Graph client (replaces sema4ai_http)
├── models.py                 Pydantic input/output models
├── agent_server_context.py   thread-files overlay helper (from the skill)
├── agent_server_helper.py    thread-files overlay helper (from the skill)
└── tests/
    ├── conftest.py
    ├── test_smoke.py
    ├── test_context.py
    └── test_tools.py
```

See [`microsoft-sharepoint-mcp/pyproject.toml`](microsoft-sharepoint-mcp/pyproject.toml).
Flat layout per the skill convention — no `src/` directory, no
`create_app()` factory. The `mcp` object is registered at module level,
and `if __name__ == "__main__": mcp.run(...)` is the entry point.

### Commit 4 — `feat: wire up context + thread files`

[`agent_server_context.py`](microsoft-sharepoint-mcp/agent_server_context.py)
and [`agent_server_helper.py`](microsoft-sharepoint-mcp/agent_server_helper.py)
come from the `convert-action-pack` skill verbatim — no SharePoint-
specific logic in them. They bind per-request headers to a `ContextVar`
and wrap the Agent Server file-upload/download calls via
`sema4ai-api-client`.

`server.py` wraps only the tools that need context with
`_bind_request_context()`:

```python
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
```

### Commit 5 — `feat: Graph client + Pydantic models`

[`models.py`](microsoft-sharepoint-mcp/models.py) collects the Pydantic
types the tools accept and return — `SiteIdentifier`, `SharepointList`,
`ListItem`, `FileList`, and a typed output model per tool. These mirror
the legacy `microsoft_sharepoint/models.py` almost verbatim; preserving
the input schemas lets the Sema4.ai agent reuse its existing knowledge of
the shapes.

[`sharepoint_client.py`](microsoft-sharepoint-mcp/sharepoint_client.py) is
a small `httpx`-based client for the Microsoft Graph endpoints the
legacy pack hit — replacing the legacy `sema4ai_http` + `send_request`
helpers. Each method takes the bearer token explicitly so tool code can
fail fast with a clear message when it's missing.

### Commit 6 — `feat: implement tools in server.py`

[`server.py`](microsoft-sharepoint-mcp/server.py) registers all twelve
tools. Representative patterns:

**Simple read (site lookup)**:

```python
@mcp.tool(annotations=READ)
def search_for_site(search_string: str) -> SearchSitesOutput:
    """Search for a SharePoint site by name or hostname."""
    token = _require_bearer()
    return SearchSitesOutput(**client.search_for_site(token, search_string))
```

**Mutation (list create)**:

```python
@mcp.tool(annotations=MUTATE)
def create_sharepoint_list(
    site: SiteIdentifier,
    sharepoint_list: SharepointList,
) -> CreateListOutput:
    """Create a new SharePoint list on the given site."""
    token = _require_bearer()
    return CreateListOutput(list=client.create_list(token, site, sharepoint_list))
```

**Thread-files overlay (download + attach)**:

```python
@mcp.tool(annotations=READ)
def download_sharepoint_file(
    filelist: FileList,
    site: SiteIdentifier | None = None,
    attach: bool = False,
) -> DownloadFilesOutput:
    """Download file(s) from SharePoint; optionally attach to the thread."""
    token = _require_bearer()
    results: list[str] = []
    with _bind_request_context():
        for file in filelist.files:
            content, name = client.download_file(token, site, file)
            if attach:
                attach_file_content(
                    name=name, data=content, content_type="application/octet-stream"
                )
            results.append(name)
    return DownloadFilesOutput(files=results)
```

The `_bind_request_context()` wrap is narrow: only two tools use it.
Don't wrap every tool by default — it adds no value where the agent
callback isn't needed, and it makes errors harder to read.

### Commit 7 — `test: smoke, context, representative tools`

Four test files, mirroring the skill's template:

- [`tests/test_smoke.py`](microsoft-sharepoint-mcp/tests/test_smoke.py) —
  imports `server`, lists the tool registry, asserts the twelve expected
  names.
- [`tests/test_context.py`](microsoft-sharepoint-mcp/tests/test_context.py) —
  exercises `current_invocation_data()` across valid / invalid / missing
  header cases, and confirms the thread-files helpers raise on missing
  required fields.
- [`tests/test_tools.py`](microsoft-sharepoint-mcp/tests/test_tools.py) —
  one test per category (read, mutation, missing-auth, thread-file) with
  the Graph client mocked.
- [`tests/conftest.py`](microsoft-sharepoint-mcp/tests/conftest.py) —
  fixtures for a fake Graph client and a helper that patches
  `get_http_request` to return a request with a chosen `Authorization`
  header.

### Validation gate

```bash
cd microsoft-sharepoint-mcp
uv sync
uv run pytest
uv run python server.py   # binds 0.0.0.0:8067, endpoint /mcp
```

The tool registry matches the inventory (twelve tools). Auth-failure
paths raise `ValueError("Missing OAuth token — …")`. Thread-file flows
round-trip against the Agent Server API once the ngrok-to-Sema4.ai loop
is connected (see [`docs/04-migration-workflow.md`](../../docs/04-migration-workflow.md)
step 5).

## Parity report

- **Pack path**: `gallery/actions/microsoft-sharepoint/` (v3.1.1).
- **Target**: `microsoft-sharepoint-mcp/`.
- **Tools migrated**: 12 (all legacy `@action`s, preserved names).
- **Actions omitted**: 0.
- **SDM Verified Queries extracted**: 0 (pack has no `@query`).
- **Auth classification**: OAuth forwarded bearer, server-wide. Two file
  tools additionally need `X-Tool-Invocation-Context` and the
  `sema4ai-api-client` thread-files overlay.
- **Known deltas**:
  - Per-action OAuth scopes collapse to a single aggregated scope on the
    OAuth client registration. Per-tool scope gating, if needed, moves
    to the agent / gateway layer.
  - Return types are explicit Pydantic output models (`SearchSitesOutput`,
    …) instead of `Response[dict]`. Field shapes are preserved; only the
    wrapper is gone.
  - `ActionError` is replaced with `ValueError` / Graph HTTP errors.
  - `sema4ai_http` is replaced with `httpx`.

## Tips from this migration

- **OAuth scope consolidation is the biggest surprise.** Legacy packs
  tailor scopes per action; in the MCP world the OAuth client registers
  once with a union of scopes. If your pack depended on enforcing
  least-privilege per tool via scope separation, that enforcement moves
  up — either to multiple OAuth clients, or to agent-side policy.
- **Thread-files overlay is surgical.** Only the tools that use `chat.*`
  need the overlay. Don't wrap every tool in `_bind_request_context()`
  by default.
- **Keep Pydantic input models shape-for-shape.** The Sema4.ai agent
  already knows these schemas. Renaming fields or changing types costs
  more than it's worth.
- **`sema4ai_http` → `httpx` is a free upgrade.** Better timeouts,
  streaming support, and a clean async path if you ever need it.

## What's next

- [Sema4.ai patterns](../../docs/05-sema4-patterns.md) — context headers,
  auth, thread files in depth.
- [Orchestration](../../docs/07-orchestration/) — Cloud Run, AWS ECS
  Fargate, Azure Container Apps, multi-MCP gateway.
