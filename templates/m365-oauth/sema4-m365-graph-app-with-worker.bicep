// TEMPLATE B — WORKER AGENTS (app-only) + USER AGENTS (delegated).
// (For user agents only, see sema4-m365-graph-app.bicep.)
//
// Entra app registration for the Sema4 M365 / Microsoft Graph MCP servers,
// configured for BOTH delegated (user-on-behalf-of-user) and app-only (machine-to-machine)
// authentication flows.
//
// Delegated scopes allow user agents to act on behalf of a signed-in user.
// Application scopes enable worker agents to act as the app itself via client credentials.
//
// Uses the Microsoft.Graph Bicep extension (preview). Deploy with:
//   az deployment tenant create \
//     --name sema4-m365-graph-app-worker \
//     --location <region> \
//     --template-file sema4-m365-graph-app-with-worker.bicep
//
// Post-deployment:
//   1. Grant admin consent for all scopes:
//      az ad app permission admin-consent --id <appId>
//   2. Create a client secret (required for worker agents):
//      az ad app credential reset --id <appId> --display-name spar --years 2

extension microsoftGraphV1_0

targetScope = 'tenant'

@description('Display name and uniqueName for the Entra app registration.')
param appName string = 'Sema4.ai Worker'

@description('Auth-code redirect URIs (web). Defaults to the SPAR prod + local callbacks.')
param redirectUris array = [
  'http://localhost:8001/tenants/spar/agents/api/v2/oauth2/callback'
  'https://backend.sema4.ai/oauth/callback'
  'https://backend.sema4ai.dev/oauth/callback'
]

@description('Sign-in audience. The live app is multi-tenant (AzureADMultipleOrgs).')
@allowed([
  'AzureADMyOrg'
  'AzureADMultipleOrgs'
])
param signInAudience string = 'AzureADMultipleOrgs'

var graphAppId = '00000003-0000-0000-c000-000000000000'

// Delegated scopes for user agents (act-as-user).
// [user] = user-consentable; [ADMIN] = requires tenant admin consent.
var delegatedScopes = {
  // shared / auth
  'offline_access': '7427e0e9-2fba-42fe-b0c0-848c9e6a8182' // user
  'User.Read': 'e1fe6dd8-ba31-4d61-89e7-88639da4683d' // user
  // microsoft-mail
  'Mail.ReadWrite': '024d486e-b451-40bb-833d-3e66d98c5c73' // user
  'Mail.Send': 'e383f46e-2787-4529-855e-0e479a3ffac0' // user
  // microsoft-calendar
  'Calendars.ReadWrite': '1ec239c2-d7c9-4623-a91a-a9775856bb36' // user
  'MailboxSettings.Read': '87f447af-9fa4-4c32-9dfa-4a57a73d18ce' // user
  // microsoft-excel / onedrive / sharepoint (files)
  'Files.Read': '10465720-29dd-4523-a11a-6a75c743c9d9' // user
  'Files.Read.All': 'df85f4d6-205c-4ac5-a5ea-6bf408dba283' // user
  'Files.ReadWrite': '5c28f0bf-8a70-41f1-8ab2-9032436ddb65' // user
  'Files.ReadWrite.All': '863451e7-0667-486c-a5d6-d135439485f0' // user
  // microsoft-sharepoint (sites)
  'Sites.Read.All': '205e70e5-aba6-4c52-a976-6d2d46c48043' // user
  'Sites.Manage.All': '65e50fdc-43b7-4915-933e-e8138f11f40a' // user
  // microsoft-teams
  'Team.ReadBasic.All': '485be79e-c497-4b35-9400-0e3fa7f2a5d4' // user
  'Channel.ReadBasic.All': '9d8982ae-4365-4f57-95e9-d6032a4c0b87' // user
  'ChannelMessage.Send': 'ebf0f66e-9fb1-49e4-a278-222f76911cf4' // user
  'Team.Create': '7825d5d6-6049-4ce7-bdf6-3b8d53f4bcd0' // user
  'Chat.Create': '38826093-1258-4dea-98f0-00003be2b8d0' // user
  'Chat.ReadWrite': '9ff7295e-131b-4d94-90e1-69fde507ac11' // user
  'ChatMessage.Send': '116b7235-7cc6-461e-b163-8e55691d839e' // user
  // microsoft-teams — ADMIN CONSENT REQUIRED
  'TeamMember.Read.All': '2497278c-d82d-46a2-b1ce-39d4cdde5570' // ADMIN
  'ChannelMessage.Read.All': '767156cb-16ae-4d10-8f8b-41b657c8c8c8' // ADMIN
  'User.Read.All': 'a154be20-db9c-4678-8ab7-66f6cc099a59' // ADMIN
  'Group.Read.All': '5f8c59db-677d-491f-a6b8-5f174b11ec1d' // ADMIN
  'GroupMember.ReadWrite.All': 'f81125ac-d3b7-4573-a3b2-7099cc39df9e' // ADMIN
  'Group.ReadWrite.All': '4e46008b-f24c-477d-8fff-7bb4ec7aafe0' // ADMIN
}

// Application scopes for worker agents (app-only / client credentials).
// Worker agents require ADMIN consent. They act on behalf of the app, not a user.
// Set X-User-Id header or AZURE_USER_ID env var to target a specific user/mailbox.
var applicationScopes = {
  // shared / auth
  'offline_access': '7427e0e9-2fba-42fe-b0c0-848c9e6a8182'
  // microsoft-mail (app-only)
  'Mail.Read': '7b9103a5-4610-446b-9670-7a282ec5b86b'
  'Mail.ReadWrite': '5dafcb41-563f-4368-929f-d30e06f17d79'
  'Mail.Send': 'e2a3a72e-5f46-42a2-914a-e4c3d60e0e6f'
  // microsoft-calendar (app-only)
  'Calendars.Read': '662a16c0-deea-4070-a154-6ee9236afba8'
  'Calendars.ReadWrite': '879a6098-7e63-4988-bda2-23ba472a1c32'
  'MailboxSettings.Read': 'f7dd0f93-3db6-4cfe-a5f9-fee2adb76861'
  // microsoft-onedrive/sharepoint (files) — app-only
  'Files.Read.All': '01d0a3a6-594d-4d0c-be28-bdd4d2c5e83c'
  'Files.ReadWrite.All': '75359482-378e-40d7-8e7c-e7f32b5f5143'
  // microsoft-sharepoint (sites) — app-only
  'Sites.Read.All': '205e70e5-aba6-4c52-a976-6d2d46c48043'
  'Sites.Manage.All': '65e50fdc-43b7-4915-933e-e8138f11f40a'
  // microsoft-teams (app-only)
  'Team.ReadBasic.All': '485be79e-c497-4b35-9400-0e3fa7f2a5d4'
  'Channel.ReadBasic.All': '9d8982ae-4365-4f57-95e9-d6032a4c0b87'
  'ChannelMessage.Read': '767156cb-16ae-4d10-8f8b-41b657c8c8c8'
  'ChannelMessage.Send': 'ebf0f66e-9fb1-49e4-a278-222f76911cf4'
  'Team.Create': '7825d5d6-6049-4ce7-bdf6-3b8d53f4bcd0'
  'TeamMember.Read.All': '2497278c-d82d-46a2-b1ce-39d4cdde5570'
  'Chat.Create': '38826093-1258-4dea-98f0-00003be2b8d0'
  'Chat.ReadWrite': '9ff7295e-131b-4d94-90e1-69fde507ac11'
  'ChatMessage.Send': '116b7235-7cc6-461e-b163-8e55691d839e'
  // user/group — app-only
  'User.Read.All': 'a154be20-db9c-4678-8ab7-66f6cc099a59'
  'Group.Read.All': '5f8c59db-677d-491f-a6b8-5f174b11ec1d'
  'GroupMember.ReadWrite.All': 'f81125ac-d3b7-4573-a3b2-7099cc39df9e'
  'Group.ReadWrite.All': '4e46008b-f24c-477d-8fff-7bb4ec7aafe0'
}

// Combine delegated + application scopes for requiredResourceAccess.
var allScopes = union(delegatedScopes, applicationScopes)
var graphResourceAccess = [
  for scope in items(allScopes): {
    id: scope.value
    type: 'Scope'
  }
]

resource app 'Microsoft.Graph/applications@v1.0' = {
  displayName: appName
  uniqueName: appName
  signInAudience: signInAudience
  web: {
    redirectUris: redirectUris
    implicitGrantSettings: {
      enableAccessTokenIssuance: false
      enableIdTokenIssuance: false
    }
  }
  requiredResourceAccess: [
    {
      resourceAppId: graphAppId
      resourceAccess: graphResourceAccess
    }
  ]
}

resource appSp 'Microsoft.Graph/servicePrincipals@v1.0' = {
  appId: app.appId
}

output appId string = app.appId
output servicePrincipalId string = appSp.id
