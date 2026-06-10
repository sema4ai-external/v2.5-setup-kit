# Agent Server example MCP

A minimal, runnable MCP server that exercises the three Sema4.ai platform
features a migrated MCP most often needs:

- **Invocation context** — reading `X-Tool-Invocation-Context`.
- **Thread dataframes** — listing and fetching dataframes on the current thread.
- **Thread files** — listing, uploading, and downloading files on the current thread.

Where the [worked SharePoint migration](../worked-migration/) shows a whole
action pack converted to an MCP, this example is a focused **reference for
the platform-feature surface itself**. It is not a migration of any
particular pack — reach for it when you need to see exactly how the
context header, the Agent Server callbacks, and the
[`sema4ai-api-client`](https://pypi.org/project/sema4ai-api-client/) helpers
fit together. The conceptual write-up of these patterns lives in
[docs/05-sema4-patterns.md](../../docs/05-sema4-patterns.md).

## Tools

| Tool | What it does |
| --- | --- |
| `get_bound_context()` | Return the invocation-context fields bound to this request. Debugging aid. |
| `list_thread_data_frames(num_samples=5)` | List dataframes on the current thread, with a small row sample each. |
| `get_thread_data_frame(data_frame_name, ...)` | Fetch rows of one named dataframe from the current thread. |
| `list_thread_files()` | List files attached to the current thread. |
| `upload_text_to_thread_file(name, content, content_type="text/plain")` | Upload text as a new thread file. |
| `download_thread_file_text(file_ref, encoding="utf-8")` | Download a thread file and decode it as text. |

## Files

```
server.py                 module-level `mcp`, the six tools, streamable-HTTP entry point
agent_server_context.py   X-Tool-Invocation-Context parsing + ContextVar binding + client factory
agent_server_helper.py    thread-file upload/download via sema4ai-api-client
pyproject.toml
tests/                    smoke + context tests
```

## Run locally

```bash
cd examples/agent-server-example
uv sync
uv run python server.py
```

The server listens on `http://0.0.0.0:8067` (override with `MCP_HTTP_PORT`)
and serves the MCP at `/mcp`. Point
[MCP Inspector](https://github.com/modelcontextprotocol/inspector) at
`http://localhost:8067/mcp` to list the tools, or run the full loop against
a Sema4.ai agent over ngrok — see
[docs/04-migration-workflow.md](../../docs/04-migration-workflow.md).

## Invocation context it expects

Every tool reads these fields from `X-Tool-Invocation-Context` (base64-encoded
JSON, supplied by the Sema4.ai agent at call time):

- `agent_server_api_token` — auth for Agent Server callbacks.
- `agent_server_api_url` — Agent Server base URL.
- `agent_id`, `thread_id` — scope every dataframe/file call.

Load-bearing fields fail loudly when missing rather than guessing a default
— see `agent_server_context.py`. The generated `sema4ai-api-client` endpoint
names in `server.py` / `agent_server_helper.py` track the installed package
version; if they drift, check the package and adjust.
