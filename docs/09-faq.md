# FAQ

Common questions that come up during migration. Skim the ones that
sound like your situation.

## Do I have to migrate every action?

No. Run the [decision tree](01-decide.md) first. Many actions should
retire (unused), become SDM Verified Queries (`@query`-style SQL), or
be replaced by a vendor-published remote MCP. Migrate only what's
left.

## Can I still use stdio MCPs?

For local development, yes. For **registration with a Sema4.ai agent,
no** — Sema4.ai supports only remote streamable-HTTP MCPs.

## My pack has both `@action` and `@query` functions. What happens?

The [`convert-action-pack`](../.claude/skills/convert-action-pack/SKILL.md)
skill handles this. `@action`s become MCP tools; `@query`s are
extracted as SDM Verified Query definitions for you to paste into
your agent's Semantic Data Model config. Neither loses functionality.

## How do I handle legacy `chat.*` APIs?

Use the thread-files overlay: `sema4ai-api-client` plus the
`ContextVar` binding pattern. See
[files and threads](05-sema4-patterns.md#thread-files).

## What about cold starts on serverless platforms?

Cloud Run, Fargate, and Container Apps all cold-start in the
hundreds-of-ms range. For latency-sensitive MCPs, set min-instances
to 1. For background-use MCPs, tolerate it.

## How do I version my MCP?

`pyproject.toml`'s `version` field, plus container image tags. Treat
every breaking tool-shape change (renamed tool, removed parameter)
as a major-version bump; keep the old URL live until agents migrate.

## How do I test against a real Sema4.ai agent before deploying?

ngrok. See
[framework and setup](03-framework-and-setup.md#testing-against-sema4ai-in-the-loop)
and [migration workflow](04-migration-workflow.md) step 5.

## What if a vendor publishes an official remote MCP later?

Switch your agent to the vendor MCP and retire your own. The decision
tree starts with exactly this question
([01-decide.md](01-decide.md#1-does-the-vendor-already-publish-a-remote-mcp)).

## Can I run the MCP on my laptop for production?

No — Sema4.ai needs a public, always-on HTTPS URL. Deploy to one of
the [orchestration targets](07-orchestration/).

## How do I handle rate limiting?

Vendor SDKs usually have built-in retry logic; use it. If you're
writing a raw `httpx` client, add a retry policy for 429 responses
on read tools. **Don't** silently retry mutating tools — document
caller behavior instead.

## Can one MCP server speak multiple auth schemes?

fastmcp supports one `auth=` config per `FastMCP` instance. If tools
genuinely need different schemes, split into multiple servers.

## What Python version?

**3.12 or newer.** `fastmcp`, `sema4ai-api-client`, and the worked
examples all assume it.

## How do I know my tool descriptions are good enough for the agent?

Spot-check via MCP Inspector. Ask a Sema4.ai agent in plain language
("find the Contoso site") and see if it picks the right tool without
a nudge. If not, tighten descriptions — see
[tools and testing](06-tools-and-testing.md#descriptions).

## My migrated MCP's output shape drifted from the legacy action. Is that OK?

Depends who's reading the output.

- **If an agent prompt hard-codes field names** (`"use result.site_id
  when calling X"`) or a **non-LLM consumer** — a handoff step, a
  webhook receiver, a script — parses the output as structured data,
  drift breaks them. Preserve the names.
- **If the agent just LLM-reasons over the result** ("which site did
  I just get?"), drift is usually fine. The Pydantic schema is
  advertised in the tool metadata; the model reads the new shape and
  adapts.

Drop `Response[T]` wrappers — that's intended drift. Cleanup that
clarifies legacy cruft is a net win. Preserve field names where
something already depends on them, not by default.

## See also

- [Decision tree](01-decide.md) — the starting question for every
  pack.
- [Migration workflow](04-migration-workflow.md) — step-by-step with
  Claude Code.
- [Sema4.ai patterns](05-sema4-patterns.md) — the integration
  details.
