# v2.5 Setup Kit

Complete migration guide, templates, and tooling for moving Sema4.ai custom actions to remote MCP servers and setting up production infrastructure.

> **Sema4.ai only supports remote MCPs.** Stdio MCPs are fine for local
> development (Claude Desktop, Cursor), but every MCP registered with a
> Sema4.ai agent must be a remote, HTTP-reachable server using streamable-HTTP
> transport.

## Who this is for

Technical users who already ship Sema4.ai Action packs and need to migrate
them to MCP servers. Fluency with Python, `uv`, OAuth, and HTTP is assumed.

## Before you migrate

Not every action should become an MCP. In order:

1. **Does the vendor already publish a remote MCP?** Use it. Many vendors
   now ship one.
2. **Is it a `@query` / parameterized-SQL action?** Extract it as an SDM
   Verified Query in your agent instead.
3. **Is it retired or unused?** Delete it.
4. **Otherwise** — migrate to MCP.

Full decision tree with signals for each branch: [docs/01-decide.md](docs/01-decide.md).

## The biggest shift

With Sema4.ai actions, the platform runtime called your code inside the
agent — injecting context, managing secrets, shaping errors. With MCPs, the
Sema4.ai agent calls your server over HTTP and chooses which tool to use
from the tool's name and description. Your job shifts to writing tools the
agent can understand at a glance.

More in [docs/02-mental-model.md](docs/02-mental-model.md).

## Repo map

```
docs/          Narrative guide — decide, mental model, setup, patterns, deploy
examples/      Worked migration (SharePoint) + feedback-mcp (data-connection
               pattern + two consumer agents)
templates/     Reusable infrastructure templates (Bicep, etc.) — M365 OAuth
               app registration, etc.
.claude/       Skills and slash commands (convert-action-pack)
```

## Contributing

This guide evolves with customer feedback. Open issues for migration patterns
that aren't covered or that you'd frame differently.

## License

See [LICENSE](LICENSE).
