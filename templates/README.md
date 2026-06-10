# Reusable Infrastructure Templates

Ready-to-use Bicep and configuration templates for deploying MCP server infrastructure and supporting services.

## Templates

### Microsoft 365 OAuth App Registration

**Directory:** `m365-oauth/`

Entra app registrations for Microsoft 365 and Microsoft Graph MCP servers.

**Includes:**
- `sema4-m365-graph-app.bicep` — User agents only (delegated OAuth)
- `sema4-m365-graph-app-with-worker.bicep` — User + worker agents (delegated + app-only)
- `README.md` — Detailed guide, quick start, troubleshooting

**Use when:** Migrating M365 actions (mail, calendar, teams, files, etc.) to MCP and need to configure OAuth/Entra permissions.

See [m365-oauth/README.md](m365-oauth/README.md) for setup instructions.

---

## Contributing New Templates

When adding a new template:

1. Create a subdirectory named after the service/pattern (e.g., `templates/slack-oauth/`)
2. Include the IaC files (Bicep, Terraform, CloudFormation, etc.)
3. Add a `README.md` with:
   - Overview of what the template provisions
   - When to use it (vs. alternatives)
   - Quick start guide
   - Parameter reference
   - Troubleshooting
4. Update this file (templates/README.md) with a brief entry

---

## General Notes

- **No secrets in templates** — templates should never contain actual API keys, client secrets, or PII
- **Tested defaults** — parameter defaults should be tested and work for common use cases
- **Multi-tenant safe** — unless explicitly single-tenant, templates should support both single and multi-tenant scenarios
- **Output clarity** — templates should output IDs and endpoints needed by downstream services (e.g., app ID, server URL)
