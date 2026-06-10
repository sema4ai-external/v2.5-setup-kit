# Feedback Reports Agent (SDM)

A second agent that reads the same `agent_feedback` Postgres table the feedback
MCP writes to, and answers simple reporting questions through a Semantic Data
Model with verified queries. **Read-only** — it never writes feedback.

## Files

| File | Purpose |
| ---- | ------- |
| `sdm.yml` | The semantic data model: the `agent_feedback` table + verified queries (gate-check + reports). |
| `config.yml` | The Postgres data connection (`agent-feedback-neon`). Credentials via env. |
| `agent-spec.yaml` | The agent package; binds `sdm.yml` and `runbook.md`. |
| `runbook.md` | Instructions for the reporter agent. |

## Data connection

`config.yml` points at a Postgres database `agent_feedback`. Set
`FEEDBACK_PG_HOST` / `FEEDBACK_PG_USER` / `FEEDBACK_PG_PASSWORD` (and the rest if
needed) — do not commit real values. This is the **same** database the feedback
MCP writes to: the MCP inserts rows, this SDM reads them.

## Verified queries

All SELECT (the gate-check is also a SELECT):

- **Last Thumb For Thread Step** — `thread_id`, optional `rated_message_id`.
  Returns the latest thumb for a thread/step. A runbook uses this to block a step
  until the user has chosen (see the main [`README.md`](../README.md)).
- **Feedback Counts By Verdict** — `days_back`.
- **Up Rate By Agent** — `days_back` (approval % per agent).
- **Recent Thumbs Down With Notes** — `row_limit`.
- **Feedback Volume Over Time** — `days_back` (daily up/down trend).

All are plain SELECTs over the `agent_feedback` table.

## Deploying / attaching

The SDM and agent are uploaded to the agent server, then bound:

1. Create the data connection from `config.yml` (with `FEEDBACK_PG_PASSWORD` set).
2. Upload `sdm.yml` as a semantic data model.
3. Create the agent from `agent-spec.yaml`.
4. Bind the SDM to the agent:
   `POST /api/v2/agents/{agent_id}/semantic-data-models` with the SDM id.

> The `model:` in `agent-spec.yaml` is set to a known-valid example
> (`OpenAI / gpt-4o`); swap it for your platform's preferred model.
