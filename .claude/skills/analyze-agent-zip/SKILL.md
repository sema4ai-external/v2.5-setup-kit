---
name: analyze-agent-zip
description: Analyze an exported Sema4.ai agent (a .zip bundle) and produce a MIGRATION PLAN — a per-pack inventory, a vendor-MCP / SDM-Verified-Query / delete / migrate-to-MCP decision for each bundled action pack, and a checklist of everything the customer must provide (auth secrets, OAuth apps + scopes, data connections). Read-only — writes no code. Run this BEFORE convert-action-pack.
---

# analyze-agent-zip

Analyze an **exported Sema4.ai agent** — a `.zip` that bundles the agent's
runbook(s) and one or more action packs — and produce a **migration plan**.
This skill is the triage step that runs across the whole export and decides
what happens to each pack. It writes **no code**; `convert-action-pack`
does the actual per-pack conversion.

This skill is self-contained — everything you need to produce the plan is
below. The conceptual reference for these decisions is
[`docs/01-decide.md`](../../docs/01-decide.md).

## 1. Goal

Given an agent export at `{zip_path}`, produce one document:

1. An **agent summary** — name, runbook notes, the list of bundled packs.
2. A **per-pack decision** — for each pack, exactly one of: use a vendor
   MCP, extract as SDM Verified Queries, delete, or migrate to MCP.
3. A **per-pack inventory** — every function classified.
4. A **customer-requirements checklist** — everything the customer must
   create or provide for the migrated agent to work.
5. **Parity notes** — anything that will be dropped, merged, or renamed.

Hand the plan to `convert-action-pack` for each pack that lands on
"migrate to MCP".

## 2. Unpack and enumerate

The export is a zip. Unpack it to a temp directory and map the contents:

- **Runbook(s) / agent spec** — capture the agent name and a one-line note
  on what it does. You don't migrate the runbook; you migrate the packs it
  depends on.
- **Run model** — is this a **conversational** agent (a user is present and
  drives it in chat) or a **worker** agent (autonomous — runs on triggers,
  a schedule, an inbound mailbox/channel, or a runbook that executes
  unattended)? Signals in the runbook/spec: triggers, a schedule, mailbox or
  channel inputs, "runs unattended" → worker; otherwise conversational. This
  decides which MCP auth mode the customer should configure (§7) — it is the
  single most-missed requirement for OAuth packs on worker agents.
- **Action packs** — each directory containing a `package.yaml` is one
  pack. A single export commonly bundles several. List them all before
  analyzing any — a pack missed here is a capability silently dropped.

Bundled packs typically live under an `actions/` tree
(`actions/<publisher>/<pack>/<version>/`), but don't assume the layout —
find every `package.yaml`.

**When the export doesn't cooperate — stop; don't emit a hollow plan:**

- **Zip won't unpack, or it isn't a valid agent export** (not a zip, no
  runbook/agent spec, no `actions/` tree) → say so and stop. A plan built
  from nothing is worse than no plan.
- **No `package.yaml` anywhere** → there are no action packs to migrate.
  Report that and stop, rather than emitting an empty inventory.
- **A pack with zero `@action`/`@query` functions** → list it, mark it
  `drop` (nothing to migrate), and continue with the rest.
- **Run model undetermined** (no clear conversational/worker signal) → flag
  it as undetermined and ask the customer to confirm; don't silently assume
  one, since it drives the auth-mode recommendation (§7).

## 3. Decide per pack (four outcomes, in order)

Run this decision for **each** pack, in order. Stop at the first match.

1. **Vendor already ships a remote MCP?** → **USE VENDOR MCP**. Don't
   migrate; point the customer at the vendor's server. Many vendors now
   ship one.
2. **Document Intelligence pack?** (name/description mentions "DI",
   "parse", "extract", "document intelligence" **and** dependencies
   include `reductoai`, `sema4ai_docint`, or a similar DI library) → **NO
   MIGRATION (native platform DI)**. Don't build an MCP; the customer uses
   the platform's built-in Document Intelligence.
3. **All `@query`, all pure-query?** (the pack is only `@query` functions
   and every one is a single parameterized statement — see §5) → **SDM
   (all Verified Queries)**. Every function becomes a Verified Query in the
   agent's Semantic Data Model. No MCP server.
4. **Otherwise** (any `@action`, or any **mixed** `@query`) → **MCP (whole
   pack)**. The whole pack becomes one MCP server, so it stays a single
   cohesive deployable with its orchestration and shared DB connection
   intact.

State the verdict per pack in one line with its reason — e.g.
"MCP (whole pack) — contains a variable-row write loop" or
"SDM — three read-only parameterized queries".

> Don't split one pack across both SDM and MCP. The unit of decision is the
> pack.

## 4. Collect the facts (per pack)

From each pack, read `package.yaml`, every action file, and
`data_sources.py`. Capture:

- **`package.yaml`** — name, description, version, dependencies,
  `external-endpoints`.
- **Each `@action`** (`sema4ai.actions`) — name, params, return type,
  `is_consequential`.
- **Each `@query`** (`sema4ai.data`) — name, params (the Pydantic model),
  the SQL, and whether it reads or mutates (INSERT/UPDATE/DELETE).
- **Auth** — `Secret`, `OAuth2Secret`, `SecretSpec`: count and names of
  every required value (packs often need a key **plus** a workspace/account
  identifier — don't miss the secondary ones).
- **Platform context** — reads of `X-Action-Invocation-Context` /
  `agent_id` / `thread_id` / `tenant_id`.
- **Thread files** — `chat.get_file*` / `chat.attach_file*`.
- **Data sources** (`data_sources.py`) — each `DataSourceSpec`: `engine`,
  `name`, `description`.
- **Runtime-sensitive deps** — browser automation, OCR, Pillow, native
  libraries.

## 5. Classify each `@query`: pure-query vs mixed

For every `@query`, decide whether it is one **parameterized SQL statement**
(a Verified Query) or carries **orchestration** a single statement can't
express.

- **Pure-query** (→ VQ-able): one parameterized statement. Conditional
  `WHERE` building, light date math, and string formatting still count —
  they flatten into one statement. **Writes count as pure too**: a Verified
  Query may INSERT/UPDATE/DELETE; a check-then-upsert can be one `MERGE` /
  `INSERT … ON CONFLICT`. Only DDL is out.
- **Mixed** (→ NOT VQ-able): real control flow or non-SQL work that won't
  collapse to one statement — e.g. a loop inserting a **variable number of
  rows**, multiple branching statements, API calls / file downloads
  interleaved with SQL, or a join across **two different data sources** (one
  DB per SDM).

Record each `@query` as pure-query or mixed — this drives the §3 decision.

## 6. Inventory table (per pack)

Emit one table per pack. Don't skip it — it's the single best place to
catch a silently dropped capability.

```
| Function | @action/@query | read/mutate | pure-query? | auth | platform ctx | thread files | Outcome |
| -------- | -------------- | ----------- | ----------- | ---- | ------------ | ------------ | ------- |
```

`Outcome` is one of: `MCP tool`, `SDM Verified Query`, `drop`, or
`vendor MCP`.

## 7. Customer-requirements checklist

This is the hand-off list the customer acts on. Enumerate everything the
migrated agent needs, consolidated across all packs:

- **Secrets / API keys** — from each `Secret` / `SecretSpec`: the value name
  and what it's for, and how it's supplied (request header / env var).
- **OAuth** — from each `OAuth2Secret`: the **provider**, the **client id +
  client secret** (the customer registers an app, or you supply one), the
  **scopes**, and whether any scope needs **admin consent** (call these out
  — e.g. Microsoft Teams scopes are admin-only). MCP servers register the
  OAuth client once with the **union** of scopes across the pack's tools.
- **MCP auth mode** — how the customer registers each migrated MCP with the
  agent: `none` / `org_secret` / `user_oauth`. **This depends on the run
  model from §2, not just the pack's auth shape:**
  - **API-key pack** → `org_secret` (the key is held as an org secret and
    sent as a header), for either run model.
  - **OAuth pack on a conversational agent** → `user_oauth` — the agent runs
    the OAuth dance with the user present and forwards the bearer.
  - **OAuth pack on a worker agent** → `user_oauth` **does not work**: there
    is no interactive user at run time to authorize. The customer must supply
    a **non-interactive credential** — a service / long-lived token, or the
    provider's client-credentials (M2M) flow — registered as `org_secret`.
    Flag this loudly; it's the requirement customers most often miss.
  - **No-auth pack** → `none`.
- **Data connections** — from each `DataSourceSpec`: the **engine**
  (postgres / snowflake / …) and the **connection name**. The customer
  creates this data connection on the agent (the MCP/SDM resolves
  credentials from it — no separate DB secret). Note the database/schema the
  SQL expects.
  - **Deployment note**: when a pack uses data connections, both the **MCP
    server** *and* the **data connection** must exist — the MCP runs as a
    remote server, but the data connection is created in the product UI with
    the exact **connection name** the pack's SQL expects (e.g. `ANALYTICS_DW`).
    Forgetting this is a common blocker.
- **External endpoints** — any `external-endpoints` hosts that must be
  reachable / allow-listed.
- **Runtime / infra** — native or system dependencies (browser, OCR, …)
  that affect where the MCP can run.
- **Admin consent** — one consolidated line listing every permission/scope
  that needs a tenant admin, so the customer lines the admin up once.

## 8. Plan output

Produce, in one document:

1. The **agent summary** (§2) — including the **run model** (conversational
   vs worker), since it drives the auth-mode recommendation.
2. A **per-pack decision table**: pack → outcome → recommended MCP auth mode
   (§7) → one-line reason.
3. The **per-pack inventory tables** (§6).
4. The **customer-requirements checklist** (§7).
5. **Parity notes** — anything dropped, merged, or renamed, and why.
6. A **hand-off list**: which packs go to `convert-action-pack`, which
   become SDM Verified Queries, which are dropped, which use a vendor MCP.

Then point the user to [`convert-action-pack`](../convert-action-pack/SKILL.md)
for each migrate-bound pack. This skill stops at the plan — it writes no
code.
