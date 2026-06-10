# Setup — end to end

Stand up the whole feedback system: a Postgres database, the **data connection**
the agents resolve at call time, the **Feedback MCP**, and the **agents** (with
their SDMs). Do the steps in order — each depends on the one before it.

```
1. Postgres + schema  ──►  2. data connection  ──►  3. deploy + register MCP
                                   │                         │
                                   └──────────►  4. import agents  ──►  5. bind SDMs
```

## Prerequisites

- A **Postgres** database you control (Neon, RDS, Cloud SQL, or local) reachable
  from wherever the MCP runs. There is no DB-deploy template — bring your own.
- `psql` (or any Postgres client) to run the migrations.
- A host for the MCP — see [docs/07-orchestration](../../docs/07-orchestration/),
  or ngrok for local testing ([docs/04](../../docs/04-migration-workflow.md)).
- A Sema4.ai agent workspace where you can create data connections, upload
  semantic data models, and import agents.

## 1. Provision the database + create the schema

Create a database (e.g. `agent_feedback`), then run the migrations in order:

```bash
export PG="postgresql://USER:PASS@HOST:5432/agent_feedback?sslmode=require"
psql "$PG" -f migrations/001_init.sql
psql "$PG" -f migrations/002_add_thread_transcript.sql
psql "$PG" -f migrations/003_add_user_id.sql
```

That creates the single `agent_feedback` table and its indexes.

## 2. Create the data connection

On the agent workspace, create a Postgres **data connection** named
`agent-feedback-neon` pointing at the database from step 1. Use
[`reporter-agent/config.yml`](reporter-agent/config.yml) as the spec and supply
`FEEDBACK_PG_HOST` / `FEEDBACK_PG_USER` / `FEEDBACK_PG_PASSWORD` (etc.) via env —
don't commit real values.

The MCP **and** the reporting SDM both resolve the database through this one
connection, so the **name must match** (`agent-feedback-neon`, or override with
`FEEDBACK_DATA_CONNECTION_NAME`). Create it before steps 3 and 5 — the MCP's
first call and the SDM both resolve the DB through it.

## 3. Deploy + register the Feedback MCP

Deploy [`server.py`](server.py) as a remote (streamable-HTTP) MCP — see
[docs/07-orchestration](../../docs/07-orchestration/) (or ngrok locally). It needs
**no DB secret**: it reads the data connection from step 2 at call time via the
invocation-context callback token (the pattern is documented in
[docs/05](../../docs/05-sema4-patterns.md)). Note the deployed **URL** and the
**auth** your deployment expects — you'll need both in step 4.

## 4. Import the agents

Import each agent package (`agent-spec.yaml` + `runbook.md` +
`semantic-data-models/`):

- [`reporter-agent/`](reporter-agent/) — reporting agent (reads feedback).
- [`example-agents/agent-feedback-analyzer/`](example-agents/agent-feedback-analyzer/)
  — analyzer (reads feedback, charts + tables).
- [`example-agents/rate-my-food-recommendation/`](example-agents/rate-my-food-recommendation/)
  — collects feedback. **Edit its `agent-spec.yaml` first:** set the
  `Feedback Tools` MCP `url` to your step-3 host and the `X-Sema4ai-Auth` header
  to your token.

Swap each `model:` for your platform's preferred model (the bundles ship
`OpenAI / gpt-4o` as a known-valid placeholder).

## 5. Connect the SDMs to the database

Upload each agent's SDM and bind it to the agent (e.g.
`POST /api/v2/agents/{agent_id}/semantic-data-models`). Each SDM's
`data_connection_name` (`agent-feedback-neon`) ties it to the connection from
step 2 → the database from step 1. See
[`reporter-agent/README.md`](reporter-agent/README.md) for the per-query detail.

## Verify

- Run **rate-my-food-recommendation**, click 👍/👎 → a row appears in
  `agent_feedback` (`select * from agent_feedback order by created_at desc limit 5;`).
- Ask **agent-feedback-analyzer** (or the reporter) for "thumbs up vs down this
  week" → it answers via the SDM, no new row written.
