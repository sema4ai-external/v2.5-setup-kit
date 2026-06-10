# Example agents that consume the Feedback MCP

Two exported agent bundles that show the [Feedback MCP](../) in use — one on
each side of the data:

| Agent | Role | Wires up |
| --- | --- | --- |
| [`rate-my-food-recommendation/`](rate-my-food-recommendation/) | **Produces** feedback. A demo conversational agent that recommends food for a place, tells a joke, then renders 👍/👎 quick-options and records the verdict. | The **Feedback MCP** (`give_thumbs_up` / `give_thumbs_down` / `add_feedback_reason`) via the runbook's quick-options block. |
| [`agent-feedback-analyzer/`](agent-feedback-analyzer/) | **Analyzes** feedback. A read-only reporting agent that charts the up/down split, weekly trend, file-attachment breakdown, and notes word-frequency. | A semantic data model over the same `agent_feedback` table — no MCP. |

Each bundle is an agent package (`agent-spec.yaml` + `runbook.md` +
`semantic-data-models/`) you can import into a Sema4.ai agent.

## Before importing

These are sanitized examples — fill in your own values:

- **`rate-my-food-recommendation/agent-spec.yaml`** points its `Feedback Tools`
  MCP server at `https://<your-feedback-mcp-host>/mcp` with a placeholder
  `X-Sema4ai-Auth` token. Set the URL to your deployed Feedback MCP and supply a
  real auth token (however your deployment authenticates).
- Both bundles reference the `agent-feedback-neon` Postgres **data connection**
  and the `agent_feedback` table. Create that data connection on the agent (see
  [`../reporter-agent/`](../reporter-agent/)) before the SDM queries resolve.
- The `model:` is set to a known-valid example (`OpenAI / gpt-4o`); swap it for
  your platform's preferred model.

The semantic-data-model `id` values are carried over from the export; they're
opaque identifiers and are regenerated when you upload the model.
