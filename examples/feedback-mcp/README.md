# Feedback MCP

A solution template for capturing **trackable thumbs up/down feedback inside a
Sema4.ai agent run**, with **zero platform changes**.

> **Standing this up?** Follow [SETUP.md](SETUP.md) — the ordered end-to-end
> runbook (database → data connection → MCP → agents → SDMs).

Unlike the [SharePoint worked migration](../worked-migration/), this is not a
migrated action pack — it's a from-scratch reference MCP that demonstrates two
patterns the guide cares about:

- **A database connection with no DB secret on the service.** At call time the
  MCP reads the agent's configured SDM **data connection** via the
  invocation-context callback token and builds the connection string from it
  (see ["Database connection"](#database-connection--no-secret-needed) below and
  [docs/05](../../docs/05-sema4-patterns.md)).
- **Authoritative thread-context capture.** The MCP pulls the rated suggestion
  and the preceding user input from the messages API — content a verified query
  can't reach.

The pattern has three pieces:

1. **This MCP** (`server.py`) — `give_thumbs_up` / `give_thumbs_down` (record the
   verdict + thread context to Postgres) and `add_feedback_reason` (attach a
   reason to the latest feedback in the thread).
2. **A runbook segment** (below) — shows the 👍/👎 buttons after a step using the
   native `sema4-json` quick-options, gates the step until the user chooses, and
   calls the MCP on the click.
3. **A reporting agent** (`reporter-agent/`) — a read-only SDM over the same
   table for simple reports (and an optional gate-check verified query).

Two example agents that consume this MCP — one that *collects* feedback and one
that *analyzes* it — live in [`example-agents/`](example-agents/).

## How it works

```
Runbook step → agent presents its suggestion AND emits a quick-options 👍/👎 block,
               then ends its turn (waits)                       [native rendering, no platform change]
  user clicks 👍 → quick-options sends "feedback: 👍" as a normal message (one cheap turn)
    → runbook: optionally ask for a note, then call give_thumbs_up(notes) / give_thumbs_down(notes)
        → MCP reads thread_id/agent_id + callback token from X-Tool-Invocation-Context,
          GETs the thread messages, captures the rated suggestion + the preceding user
          input + input-file refs, and INSERTs the row into Postgres
```

`thread_id` / `agent_id` / `tenant_id` are **implicit** (from the invocation
context header) — the model only passes the verdict and any notes. Input files
are stored as **refs only** (name / mime_type / uri), never bytes.

### Database connection — no secret needed

The MCP resolves the Postgres connection string in this order:

1. `X-Pg-Connection-String` request header (local dev / explicit override),
2. `PG_CONNECTION_STRING` env (local dev),
3. otherwise it **reads the `agent-feedback-neon` data connection from the agent
   server** using the invocation-context callback token, and builds the
   connection string from its config.

So in production you do **not** set a separate DB secret on the service: the
same data connection that backs the reporter SDM (`reporter-agent/config.yml`)
is the single source of truth. The data-connections endpoint uses the same auth
as the conversation endpoints, so the callback token authorizes it. Override the
connection name with `FEEDBACK_DATA_CONNECTION_NAME` if you renamed it.

## The tools

Three tools:

- `give_thumbs_up(notes: str | None = None)` — record a 👍 (creates the row).
  Returns `feedback_id`, `thread_id`, `rated_message_id`.
- `give_thumbs_down(notes: str | None = None)` — record a 👎 (creates the row).
  Returns the same ids.
- `add_feedback_reason(reason: str, feedback_id: str | None = None)` — attach a
  reason. Pass the `feedback_id` returned by the thumb tool to update that exact
  row; omit it to update the **most recent** feedback in the thread.

The intended flow: the click records the verdict immediately
(`give_thumbs_up`/`give_thumbs_down`), then — because we can't pop an inline
textbox natively — the agent asks "why?" as a follow-up and calls
`add_feedback_reason` to update that same row. The thumb tools capture the rated
agent suggestion authoritatively from the thread (a verified query cannot — it
only sees parameters the model types). `notes` on the thumb tools is optional in
case the reason is already known at click time.

## Runbook segment (copy-paste)

Drop this into the agent's runbook, right after the step whose output you want
rated (e.g. after "suggested media placements"):

````markdown
### Collect feedback on the suggestion

After you present the suggestion for this step, you MUST:

1. End your message with exactly this block so the 👍/👎 buttons render:

   ```sema4-json
   {"type":"quick-options","data":[
     {"message":"feedback: 👍","title":"👍 Helpful"},
     {"message":"feedback: 👎","title":"👎 Not helpful"}]}
   ```

2. Then stop and wait. **Do not continue to the next step until the user has
   clicked 👍 or 👎.**

3. When the user's next message is `feedback: 👍` or `feedback: 👎`:
   - Immediately record the verdict: for 👍 call `give_thumbs_up()`; for 👎 call
     `give_thumbs_down()`.
   - Then ask: "Want to add a reason? (optional)".
   - If the user gives a reason, call `add_feedback_reason(reason, feedback_id)`
     using the `feedback_id` from the thumb tool's output (or omit it to target
     the latest feedback in the thread). If they decline, skip.
   - Acknowledge in one line ("Thanks — recorded."), then continue.
````

> **Gating note.** Because the buttons appear at the end of your turn, you are
> already waiting — the user's click is the signal to continue. If this agent
> also has the feedback SDM attached, you can harden the gate by running the
> `Last Thumb For Thread Step` verified query (with the current `thread_id`) and
> refusing to proceed until it returns a thumb.

## Local development

```bash
cd examples/feedback-mcp
uv sync
PG_CONNECTION_STRING="postgresql://USER:PASS@HOST/agent_feedback?sslmode=require" \
  uv run python server.py   # serves on http://localhost:8067/mcp
uv run pytest                # pure helpers + in-memory FastMCP wiring
```

For local dev, set `PG_CONNECTION_STRING` (env) or send `X-Pg-Connection-String`.
In production neither is needed — the connection resolves from the agent
server's `agent-feedback-neon` data connection (see above).

## Database

A Postgres database with one table, `agent_feedback`. Schema in
`migrations/001_init.sql` (+ `002_*` adds `thread_transcript`, `003_*` adds
`user_id`); the row holds the verdict, optional
notes, the acting `user_id` (for distinct-user counts, from
`invoked_on_behalf_of_user_id`), the rated suggestion, the preceding user input,
input-file refs, and `thread_transcript` — the **full thread messages** (every turn, including tool
calls and thoughts) as returned by the agent-server messages API, captured at
feedback time. The reporting agent (`reporter-agent/`) reads this same table.

Note: `thread_transcript` is the agent-server message transcript (turns + tool
calls + thoughts), not the raw OTel/Langsmith spans — those live in the
observability backend and aren't exposed by the agent-server API the MCP can
reach. Capturing true OTel spans would need a Langsmith/Datadog API key wired
into the MCP separately.

## Deployment

Deploy as a remote (streamable-HTTP) MCP like any other in this guide — see
[docs/07-orchestration](../../docs/07-orchestration/). No DB secret is required
on the service: the tool resolves the Postgres connection from the
`agent-feedback-neon` data connection on the agent at call time (see "Database
connection" above), so that data connection must already exist on the agent
(it's created as part of setting up the reporter SDM).
