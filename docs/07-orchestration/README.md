# Orchestration

How to host your migrated MCP. Sema4.ai doesn't host custom MCPs for
you — you run them on your own infrastructure and register each
server's URL on an agent.

The per-platform walkthroughs live in the public docs and are the
source of truth — they're versioned and kept current there:

**→ [sema4.ai/docs/v2/setup/mcp-orchestration](https://sema4.ai/docs/v2/setup/mcp-orchestration)**

Recommended hosting targets, each with its own walkthrough:

| Target | Best for |
| --- | --- |
| **Google Cloud Run** | Teams already on GCP; the simplest setup. |
| **AWS ECS Fargate** | AWS-first stacks wanting a long-running container behind an ALB. |
| **Azure Container Apps** | Azure-first stacks. |

Hosting several custom MCPs? The public docs also cover the **multi-MCP
gateway pattern** — one nginx container routing by path prefix to
several MCP processes, each still registered independently on the
agent.

## What every target needs

The MCP itself is the same in every case — what differs is the
container image's base, how ingress is configured, and how secrets
arrive. Whatever you host on, the deployment must provide:

- **Streamable-HTTP transport** — Sema4.ai connects to remote MCPs over
  HTTP only; `stdio` is not supported. The endpoint is served at the
  `/mcp` path, so the URL you register always ends in `/mcp`.
- **Session affinity (sticky sessions)** on the load balancer or
  ingress — MCP sessions are stateful per connection. Without affinity,
  requests get balanced across instances and sessions break.
- **Secrets wiring** — inject anything your MCP reads via `os.environ`
  using the platform's native secret manager.
- **A health endpoint** if the platform expects one (all targets do).
- **Network line of sight** — the Sema4.ai platform must be able to
  reach the MCP's URL. On private ingress (internal ALB, private
  subnets, internal-only Cloud Run), make sure the platform's network
  can route to it and that firewall / security-group / NSG rules allow
  the connection.

For the Sema4.ai-specific wiring your MCP must do regardless of host —
the `X-Tool-Invocation-Context` header and auth forwarding — see
[sema4-patterns](../05-sema4-patterns.md). To register the deployed URL
on an agent, see
[registering with a Sema4.ai agent](../03-framework-and-setup.md#registering-with-a-sema4ai-agent).
