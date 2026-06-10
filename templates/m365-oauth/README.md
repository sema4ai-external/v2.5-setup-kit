# Microsoft 365 OAuth App Registration Templates

Bicep templates for provisioning Entra (Azure AD) app registrations for the Sema4 M365 and Microsoft Graph MCP servers.

## Templates

### Template A: User Agents Only (`sema4-m365-graph-app.bicep`)

Configures an Entra app registration with **delegated permissions** for user agents (user-on-behalf-of-user OAuth flow).

**When to use:**
- Only delegated (user OAuth) access is needed
- No worker/background agents required
- Minimal operational overhead

**Key constraint:** The shared production app `Sema4.ai` (client_id: `31731790-4d45-4ab6-8ab7-30813caab8c3`) is a **public client** and should be used instead of deploying your own, unless you need tenant isolation or custom scopes.

**Setup:** 3 steps (deploy → grant admin consent → create secret)

### Template B: User + Worker Agents (`sema4-m365-graph-app-with-worker.bicep`)

Configures an Entra app registration with **both delegated and application permissions**, supporting:
- User agents (delegated OAuth flow)
- Worker agents (client credentials / machine-to-machine flow)

**When to use:**
- Worker agents (background tasks, scheduled jobs, bot automation) are needed
- User agents and worker agents share the same Microsoft 365 permissions
- You want one app registration for both flows

**Authentication flows:**
- **User agents**: pass Bearer token (delegated OAuth)
- **Worker agents**: pass X-Tenant-Id/X-Client-Id/X-Client-Secret headers or env vars (app-only)

**Setup:** 3 steps (deploy → grant admin consent → create secret)

## Quick Start

### Prerequisites

```bash
# Install Azure CLI and the Microsoft.Graph Bicep extension
az bicep install --id microsoftGraph
```

### User Agents Only

```bash
cd templates/m365-oauth
az deployment tenant create \
  --name sema4-m365-graph-app \
  --location eastus \
  --template-file sema4-m365-graph-app.bicep

# Get the app ID from output
appId=$(az deployment tenant show --name sema4-m365-graph-app --query 'properties.outputs.appId.value' -o tsv)

# Grant admin consent
az ad app permission admin-consent --id $appId

# Create client secret
az ad app credential reset --id $appId --display-name spar --years 2
```

### User + Worker Agents

```bash
cd templates/m365-oauth
az deployment tenant create \
  --name sema4-m365-graph-app-worker \
  --location eastus \
  --template-file sema4-m365-graph-app-with-worker.bicep

# Get the app ID from output
appId=$(az deployment tenant show --name sema4-m365-graph-app-worker --query 'properties.outputs.appId.value' -o tsv)

# Grant admin consent (for both delegated + application scopes)
az ad app permission admin-consent --id $appId

# Create client secret (required for worker agents)
az ad app credential reset --id $appId --display-name spar --years 2
```

## Configuration

### Parameters (both templates)

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `appName` | string | `Sema4.ai` / `Sema4.ai Worker` | Display name in Entra |
| `redirectUris` | array | SPAR prod + local | OAuth redirect URIs (user agents only) |
| `signInAudience` | string | `AzureADMultipleOrgs` | `AzureADMyOrg` or `AzureADMultipleOrgs` |

Override parameters during deployment:

```bash
az deployment tenant create \
  --template-file sema4-m365-graph-app.bicep \
  --parameters appName='MyOrg M365' signInAudience='AzureADMyOrg'
```

## Permissions

### User Agents (Delegated Scopes)

Both templates include delegated scopes for:
- **Auth**: `offline_access`, `User.Read`
- **Mail**: `Mail.ReadWrite`, `Mail.Send`
- **Calendar**: `Calendars.ReadWrite`, `MailboxSettings.Read`
- **Files**: `Files.Read`, `Files.Read.All`, `Files.ReadWrite`, `Files.ReadWrite.All`
- **SharePoint**: `Sites.Read.All`, `Sites.Manage.All`
- **Teams**: `Team.ReadBasic.All`, `Channel.ReadBasic.All`, `ChannelMessage.Send`, `Team.Create`, `Chat.Create`, `Chat.ReadWrite`, `ChatMessage.Send`
- **Admin scopes**: `TeamMember.Read.All`, `ChannelMessage.Read.All`, `User.Read.All`, `Group.Read.All`, `GroupMember.ReadWrite.All`, `Group.ReadWrite.All`

### Worker Agents (Application Scopes) — Template B Only

Application scopes with app-only equivalents for:
- **Mail**: `Mail.Read`, `Mail.ReadWrite`, `Mail.Send`
- **Calendar**: `Calendars.Read`, `Calendars.ReadWrite`, `MailboxSettings.Read`
- **Files**: `Files.Read.All`, `Files.ReadWrite.All`
- **SharePoint**: `Sites.Read.All`, `Sites.Manage.All`
- **Teams**: Full suite (read, send, create, member management)
- **Org**: `User.Read.All`, `Group.Read.All`, `GroupMember.ReadWrite.All`, `Group.ReadWrite.All`

All application scopes require admin consent.

## Using the App Registration

### User Agents (Delegated OAuth)

Pass the user's access token via `Authorization` header:

```bash
curl -H "Authorization: Bearer <user-access-token>" \
  https://mcp-server.example.com/api/mail/read
```

### Worker Agents (Client Credentials)

**Headers:**
```bash
curl -H "X-Tenant-Id: <tenant-id>" \
     -H "X-Client-Id: <client-id>" \
     -H "X-Client-Secret: <client-secret>" \
     -H "X-User-Id: user@example.com" \
     https://mcp-server.example.com/api/mail/read
```

**Environment variables:**
```bash
export AZURE_TENANT_ID=<tenant-id>
export AZURE_CLIENT_ID=<client-id>
export AZURE_CLIENT_SECRET=<client-secret>
export AZURE_USER_ID=user@example.com  # optional
curl https://mcp-server.example.com/api/mail/read
```

**Note:** `X-User-Id` / `AZURE_USER_ID` targets a specific user's resources. Omit to use app-wide permissions (if granted).

## Audit Trail

### User Agents
Azure AD audit logs show which **user** (signed-in identity) accessed what.

### Worker Agents
Azure AD audit logs show which **app** (client_id) accessed what, but not which worker agent triggered it. For per-worker audit trails:

1. Log actions in the worker agent itself (before calling MCP server)
2. Include custom headers (e.g., `X-Worker-Id`) in MCP server logs
3. Use application-level logging, not Azure AD audit logs

For granular per-worker Azure AD auditing, deploy separate app registrations per worker (higher operational overhead).

## Troubleshooting

### Microsoft.Graph extension not available

```bash
az bicep install --id microsoftGraph
```

### Insufficient privileges

Deployment must be run by a **Global Administrator** (tenant admin).

### Worker agent gets access_denied

Ensure admin consent was granted (step 2). Application scopes require explicit admin consent.

### Worker agent cannot access a specific user's mailbox

Pass the target user email/ID via `X-User-Id` header or `AZURE_USER_ID` env var.

### Conflict with existing app registration

Use the Azure Portal to rename or archive the existing app, or deploy with a different `appName`:

```bash
az deployment tenant create \
  --template-file sema4-m365-graph-app.bicep \
  --parameters appName='Sema4 M365 v2'
```

## Comparison

| Feature | User Only | User + Worker |
|---------|-----------|---------------|
| File | `sema4-m365-graph-app.bicep` | `sema4-m365-graph-app-with-worker.bicep` |
| Delegated (user) | ✓ | ✓ |
| App-only (machine) | ✗ | ✓ |
| Client secret required | No | **Yes** |
| Redirect URIs | Yes | Yes |
| Setup complexity | Simple | Moderate |
| Audit granularity per agent | Per-user | Per-app (not per-worker) |

## Related Resources

- [Microsoft Graph Overview](https://learn.microsoft.com/en-us/graph/overview)
- [Azure Bicep](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/)
- [Entra App Registration](https://learn.microsoft.com/en-us/entra/identity-platform/app-objects-and-service-principals)
- [OAuth 2.0 Client Credentials Flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow)
- [Delegated vs. App-Only Permissions](https://learn.microsoft.com/en-us/graph/auth/auth-concepts#delegated-and-app-only-access)
