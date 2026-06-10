# Entra ID OAuth2 for MCP servers — machine auth + auth code

Provisions an Entra ID (Azure AD) app registration that secures a **FastMCP server**
with both OAuth2 flows:

| Flow | Use case | Token claim checked |
|---|---|---|
| **Client credentials** (machine auth) | Service-to-service, agent workers | `roles` (app role) |
| **Authorization code + PKCE** | Interactive users via MCP clients | `scp` (delegated scope) |

Five non-obvious Entra settings are required; missing any one yields an opaque
`invalid_token` at the server. This template sets all five:

1. **`requestedAccessTokenVersion: 2`** — without it the v2 token endpoint still issues
   **v1 tokens** (`iss: sts.windows.net/...`) that fail issuer validation. Token format is
   decided by the *resource app's manifest*, not the endpoint you call.
2. **Delegated scope** (`invoke`) — what auth-code tokens carry in `scp`.
3. **App role** (`invoke.app`) **assigned to the app's own service principal** — what
   client-credentials tokens carry in `roles`. Without the self-assignment the claim is
   simply absent. The value must differ from the scope value (Entra rejects duplicates).
4. **`api://{client_id}` identifier URI** — default tenant policy rejects vanity names.
5. **`{base_url}/auth/callback` redirect URI** — FastMCP's OAuth-proxy callback path.

## Quick start

```bash
# Pass 1 — creates app + service principal + role self-assignment
az deployment group create -g <rg> -f mcp-server-oauth.bicep \
  -p appName=my-mcp-server appBaseUrl=https://my-mcp.example.com

# Pass 2 — adds the identifier URI (cannot self-reference app.appId in pass 1)
az deployment group create -g <rg> -f mcp-server-oauth.bicep \
  -p appName=my-mcp-server appBaseUrl=https://my-mcp.example.com \
  -p knownClientId=<clientId output from pass 1>

# Secret — the Graph extension cannot manage secret values
az ad app credential reset --id <clientId> --display-name mcp --years 1
```

No `az` CLI? Deploy the compiled ARM JSON via Azure Portal → *Deploy a custom template*,
or a CI pipeline (`azure/arm-deploy`). The deploying identity needs Graph
`Application.ReadWrite.All` (or the Application Developer role).

## Server side (FastMCP)

Use FastMCP's `AzureProvider` — do **not** hand-roll JWT validation (Entra publishes ~5
rotating signing keys; keys must be selected by the token's `kid`, which the provider does
automatically). Two adjustments are required for machine auth to work:

```python
from fastmcp import FastMCP
from fastmcp.server.auth.providers.azure import AzureProvider

class AzureHybridProvider(AzureProvider):
    """AzureProvider is an OAuth *proxy*: it issues its own tokens for the auth code
    flow and by design rejects raw Entra tokens. This subclass also accepts direct
    Entra bearer tokens (client credentials / machine auth)."""
    async def load_access_token(self, token):
        return (await super().load_access_token(token)
                or await self._token_validator.verify_token(token))

auth = AzureHybridProvider(
    client_id=...,                       # template output: clientId
    client_secret=...,                   # from az ad app credential reset
    tenant_id=...,
    required_scopes=["invoke"],
    base_url=os.environ["PUBLIC_BASE_URL"],   # public HTTPS URL of the deployment
)
# Client-credentials tokens carry app permissions in `roles` (never `scp`), but
# FastMCP's scope extractor only reads scope/scp. Widen it and normalize the
# role value back to the scope value:
_orig = auth._token_validator._extract_scopes
auth._token_validator._extract_scopes = lambda c: (
    _orig(c) or ["invoke" if r == "invoke.app" else r for r in c.get("roles", [])])

mcp = FastMCP("My MCP Server", auth=auth)
```

## Client configuration

- **Machine auth**: token URL `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token`,
  scope `api://{client_id}/.default` (the `.default` form is mandatory for client
  credentials — named scopes are rejected with `AADSTS70011`).
- **Auth code**: clients need only the MCP URL — discovery happens via RFC 9728
  protected-resource metadata, RFC 8414 server metadata, and Dynamic Client Registration,
  all served by FastMCP.

## Validation (do not skip the negative test)

```bash
# 1. NEGATIVE TEST FIRST: no credentials MUST return 401 with a WWW-Authenticate
#    challenge. A passing auth test while this returns 200 means auth silently
#    failed to initialize — a false positive.
curl -si -X POST https://<host>/mcp -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | head -3

# 2. Machine auth: a real client-credentials token must complete initialize
TOKEN=$(curl -s -X POST "https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token" \
  -d client_id=<id> -d client_secret=<secret> \
  -d scope="api://<id>/.default" -d grant_type=client_credentials | jq -r .access_token)
curl -s -X POST https://<host>/mcp -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}'

# 3. Auth code plumbing: discovery + authorize must redirect toward Microsoft login
curl -s https://<host>/.well-known/oauth-protected-resource/mcp
```

Tip: to test the delegated (auth-code) validation path without a browser, pre-authorize
the Azure CLI app (`04b07795-8ddb-461a-bbee-02f9e1bf7b46`) for the scope via
`api.preAuthorizedApplications`, then `az account get-access-token --resource api://<client_id>`
yields a genuine user token.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `invalid_token`, token `iss` is `sts.windows.net/...` | `requestedAccessTokenVersion` not 2 (or not yet propagated — wait ~1 min) |
| `missing required scopes (has [])` on machine auth | App role not assigned to the app's own SP, or scope extractor not widened to `roles` |
| `AADSTS70011 invalid_scope` | Used a named scope for client credentials — must be `api://{client_id}/.default` |
| `AADSTS7000229 missing service principal` | `az ad sp create` never ran (template handles this) |
| Identifier URI rejected | Vanity `api://` name — tenant policy requires `api://{client_id}` |
| First token 401s right after secret creation | AAD propagation, retry for ~60s |
| Valid token rejected, server logs show signature failure | JWT validation pinned to a single JWKS key instead of kid-based selection |

This template was validated end-to-end (June 2026): both deployment passes, all five
properties verified via Graph, and a live client-credentials token issued with
`ver: 2.0` and `roles: ['invoke.app']`.
