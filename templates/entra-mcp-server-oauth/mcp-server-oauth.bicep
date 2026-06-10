// Entra ID (Azure AD) app registration for securing an MCP SERVER with OAuth2.
//
// Supports BOTH flows a FastMCP server needs:
//   - machine auth (client credentials)  -> app role in the `roles` claim
//   - auth code / PKCE (interactive)     -> delegated scope in the `scp` claim
//
// Pairs with the AzureHybridProvider pattern in the convert-action-pack skill
// (section 10.7) — see README.md for the server-side code and validation steps.
//
// Deploy TWICE (identifierUris cannot self-reference app.appId):
//   az deployment group create -g <rg> -f mcp-server-oauth.bicep \
//     -p appName=<name> appBaseUrl=https://<your-mcp-host>            # pass 1
//   az deployment group create -g <rg> -f mcp-server-oauth.bicep \
//     -p appName=<name> appBaseUrl=https://<your-mcp-host> \
//     -p knownClientId=<clientId output from pass 1>                  # pass 2
//
// The resource group is only a deployment anchor — Graph objects are tenant-level.
// Upsert via uniqueName makes both passes idempotent.
//
// Client secret: the Graph extension cannot manage secret VALUES. After deploy:
//   az ad app credential reset --id <clientId> --display-name mcp --years 1
// (or mint one in the portal under Certificates & secrets). The first token
// request after secret creation may 401 for ~30-60s — AAD propagation; retry.

extension microsoftGraphV1

@description('Display name and uniqueName (idempotency key) for the app registration.')
param appName string

@description('Public base URL of the deployed MCP server, e.g. https://my-mcp.example.com')
param appBaseUrl string

@description('Leave empty on pass 1. On pass 2, set to the clientId output of pass 1 so identifierUris can be populated (it cannot self-reference app.appId).')
param knownClientId string = ''

@description('Delegated scope value (auth code flow -> scp claim).')
param scopeValue string = 'invoke'

@description('App role value (client credentials flow -> roles claim). MUST differ from scopeValue — Entra rejects duplicate values across scopes and roles.')
param roleValue string = 'invoke.app'

@description('Extra redirect URIs (e.g. local development callback).')
param extraRedirectUris array = ['http://localhost:8000/auth/callback']

var scopeId = guid(appName, 'mcp-delegated-scope')
var roleId = guid(appName, 'mcp-app-role')

resource app 'Microsoft.Graph/applications@v1.0' = {
  uniqueName: appName
  displayName: appName
  signInAudience: 'AzureADMyOrg'
  // Set on pass 2 only. Default tenant policy requires the api://{client_id}
  // form — vanity URIs like api://my-app are rejected.
  identifierUris: empty(knownClientId) ? [] : ['api://${knownClientId}']
  api: {
    // CRITICAL: without this, even the /oauth2/v2.0 endpoint issues v1 tokens
    // (iss: sts.windows.net/...) which fail v2 issuer validation. Token format
    // is decided by the resource app's manifest, not the endpoint called.
    requestedAccessTokenVersion: 2
    oauth2PermissionScopes: [
      {
        id: scopeId
        value: scopeValue
        type: 'User'
        isEnabled: true
        adminConsentDisplayName: 'Invoke MCP'
        adminConsentDescription: 'Allows the app to invoke the MCP server'
        userConsentDisplayName: 'Invoke MCP'
        userConsentDescription: 'Allows the app to invoke the MCP server'
      }
    ]
  }
  appRoles: [
    {
      id: roleId
      value: roleValue
      displayName: roleValue
      description: 'Machine auth (client credentials) access to the MCP server'
      allowedMemberTypes: ['Application']
      isEnabled: true
    }
  ]
  web: {
    redirectUris: concat(['${appBaseUrl}/auth/callback'], extraRedirectUris)
  }
}

resource sp 'Microsoft.Graph/servicePrincipals@v1.0' = {
  appId: app.appId
}

// Assign the app role to the app's OWN service principal. Without this,
// client-credentials tokens contain NO roles claim and scope checks fail
// with an opaque invalid_token.
resource selfAssignment 'Microsoft.Graph/appRoleAssignedTo@v1.0' = {
  appRoleId: roleId
  principalId: sp.id
  resourceId: sp.id
}

output clientId string = app.appId
output appObjectId string = app.id
output spId string = sp.id
output tokenEndpointHint string = 'https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0/token'
output clientCredentialsScope string = 'api://${empty(knownClientId) ? app.appId : knownClientId}/.default'
