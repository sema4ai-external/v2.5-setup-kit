# How MCPs differ from actions

You already know how the Sema4.ai Action Server works. This page covers only
what's **different** — the conceptual shifts that bite during migration if
you miss them.

## 1. Remote-only on Sema4.ai

| was | now |
| --- | --- |
| Actions ran on the Sema4.ai Action Server — a platform-managed runtime. | MCPs you register with a Sema4.ai agent must be **remote, HTTP-reachable** servers using streamable-HTTP transport. |

Stdio MCPs (the other MCP transport) are useful for purely local
development, but cannot be registered with a Sema4.ai agent. Every
migration target is a URL, not a binary.

## 2. The Sema4.ai agent calls your server over HTTP

| was | now |
| --- | --- |
| Action Server ran your actions inside the agent — injecting context, managing retries, wrapping results. | The Sema4.ai agent calls your MCP server over HTTP. It picks a tool for each step from the tool's name and description. |

Practical consequences:

- **Tool names and descriptions are the contract.** They're what the agent
  reads when deciding which tool to call. Docstrings and `ToolAnnotations`
  (`readOnlyHint`, `destructiveHint`) matter more than the equivalents in
  `package.yaml` did.
- **Cross-cutting concerns live in your code.** Logging, retries, structured
  errors, result shaping — Action Server handled some of these implicitly.
  Your MCP does them explicitly.
- **Stateful flows need a rethink.** Actions that relied on Action Server
  session state ("remember the last call's context") either move that state
  into your service or get redesigned around the per-call context the agent
  provides.

## 3. Context arrives via headers, not runtime magic

| was | now |
| --- | --- |
| `agent_id`, `thread_id`, and user context were available via in-process helpers. | The platform sends a single HTTP header — `X-Tool-Invocation-Context`, base64-encoded JSON — that your tool parses per request. |

The legacy `X-Action-Invocation-Context` name is gone. Individual legacy
headers (`X-Invoked-By-Assistant-Id`, `X-Thread-Id`, etc.) are deprecated —
don't carry them into new code.

Full details in [`05-sema4-patterns.md`](05-sema4-patterns.md).

## 4. Auth is request context, not deployment config

| was | now |
| --- | --- |
| `Secret` and `OAuth2Secret` were injected by the Action Server at call time. | Auth arrives as HTTP headers from the caller — `Authorization: Bearer …`, `X-Api-Key: …`, or vendor-specific. |

Your MCP treats auth as part of the request, not the environment. Two common
patterns:

- **Forwarded token** — the caller already has the bearer (OAuth dance
  happens upstream), forwards it, and your server uses it directly.
- **JWTVerifier** — your server participates in OAuth and verifies tokens
  itself. fastmcp's built-in `JWTVerifier` handles this.

Environment-variable fallbacks for local dev are fine, but production auth
comes from the request.

## 5. Transport is streamable-HTTP, not request/response

| was | now |
| --- | --- |
| Each action call was a stateless HTTP request/response against the Action Server. | MCP keeps a session open over streamable-HTTP. Tools can stream progress and partial results. |

Most migrations won't use streaming — tools stay one call in, one result
out. But the session model means clients list tools once, call them many
times, and expect stable tool identity across a session.

## 6. Check for a vendor MCP before you build

Not a runtime shift, but a workflow shift worth repeating: MCP is a public
standard, and vendors increasingly ship official ones. Before migrating a
`microsoft-teams` or `linear` action pack, check whether the vendor already
publishes a remote MCP. Your action was likely a thin wrapper over the same
API — let the vendor own it. See the [decision tree](01-decide.md).

## Quick reference: where each concept lands

| Action concept                       | MCP equivalent                                                    |
| ------------------------------------ | ----------------------------------------------------------------- |
| `@action` decorator                  | `@mcp.tool()` on a fastmcp `FastMCP` instance                     |
| `is_consequential=False / True`      | `ToolAnnotations(readOnlyHint=…, destructiveHint=…)`              |
| `Secret` injected at runtime         | Read from request header (`X-Api-Key`, …), env-var fallback       |
| `OAuth2Secret[...]`                  | `Authorization: Bearer` from request, or fastmcp `JWTVerifier`    |
| `Response[T]` envelope               | Plain typed return (Pydantic model or scalar)                     |
| `ActionError`                        | Regular Python exceptions — `ValueError`, `RuntimeError`          |
| `sema4ai.actions.chat.*` file APIs   | `sema4ai-api-client` + request-bound context vars                 |
| `X-Action-Invocation-Context` header | `X-Tool-Invocation-Context` (same format, new name)               |
| `package.yaml`                       | `pyproject.toml`                                                  |
| Action Server runtime                | Your deployment — Cloud Run, AWS ECS Fargate, Azure Container Apps, … |
