<#
.SYNOPSIS
  Step 5 - application settings (secrets) and network restrictions; restarts both apps.
.DESCRIPTION
  * Backend settings: PostgreSQL (least-privilege app + reader roles, signed-scope secret, TLS verify-full is the
    image default), Azure OpenAI, proxy secret, trusted proxy hops. Frontend settings: backend origin/host and the
    same proxy secret. Values come from the secrets file and are sent through a temporary JSON file (never printed).
  * Backend access restriction: only the frontend app's outbound IP addresses may reach the backend (all other
    sources get 403 from App Service); in addition the backend rejects API calls without the proxy secret.
  * PostgreSQL firewall: one rule per backend outbound IP address (no "allow all Azure services" rule).
  BACKEND_PROXY_SECRET: taken from ONBOARDAI_BACKEND_PROXY_SECRET in the secrets file when present, otherwise a new
  random value is generated for this run and set on both apps together.
#>
param([string] $ConfigPath = (Join-Path $PSScriptRoot 'config.psd1'), [switch] $Execute)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'OnboardAI.Azure.psm1') -Force
$config = Initialize-Deployment -ConfigPath $ConfigPath -Execute:$Execute
$secrets = Read-SecretsFile -Path $config.SecretsFile -Required @('AZURE_OPENAI_ENDPOINT', 'AZURE_OPENAI_DEPLOYMENT',
    'AZURE_OPENAI_API_KEY', 'ONBOARDAI_APP_DB_PASSWORD', 'ONBOARDAI_READER_DB_PASSWORD', 'ONBOARDAI_SCOPE_SECRET')
$proxySecret = if ($secrets.ContainsKey('ONBOARDAI_BACKEND_PROXY_SECRET')) { $secrets['ONBOARDAI_BACKEND_PROXY_SECRET'] } else { New-RandomSecret }
$backendHost = "$($config.BackendApp).azurewebsites.net"
$backendApp = Find-AzResource -Arguments @('webapp', 'show', '--resource-group', $config.ResourceGroup, '--name', $config.BackendApp)
if ($backendApp -and $backendApp.defaultHostName) { $backendHost = $backendApp.defaultHostName }   # discovered (may differ from <name>.azurewebsites.net)
$pgHost = "$($config.PgServer).postgres.database.azure.com"
if ($config.ContainsKey('PgHost') -and $config.PgHost -and $config.PgHost -notmatch '<') { $pgHost = $config.PgHost }

Invoke-Az -Arguments @('account', 'set', '--subscription', $config.SubscriptionId)

Write-Host "`nBackend application settings" -ForegroundColor Cyan
Set-AppSettingsFromHashtable -ResourceGroup $config.ResourceGroup -App $config.BackendApp -Settings @{
    WEBSITES_PORT                       = '8000'
    WEBSITES_ENABLE_APP_SERVICE_STORAGE = 'false'
    PG_HOST                             = $pgHost
    PG_PORT                             = '5432'
    PG_DATABASE                         = $config.PgDatabase
    PG_USER                             = 'onboardai_app'
    PG_PASSWORD                         = $secrets['ONBOARDAI_APP_DB_PASSWORD']
    PG_READER_USER                      = 'onboardai_reader'
    PG_READER_PASSWORD                  = $secrets['ONBOARDAI_READER_DB_PASSWORD']
    PG_SCOPE_SECRET                     = $secrets['ONBOARDAI_SCOPE_SECRET']
    AZURE_OPENAI_ENDPOINT               = $secrets['AZURE_OPENAI_ENDPOINT']
    AZURE_OPENAI_DEPLOYMENT             = $secrets['AZURE_OPENAI_DEPLOYMENT']
    AZURE_OPENAI_API_KEY                = $secrets['AZURE_OPENAI_API_KEY']
    BACKEND_PROXY_SECRET                = $proxySecret
    TRUSTED_PROXY_HOPS                  = [string]$config.TrustedProxyHops
}

Write-Host "`nFrontend application settings" -ForegroundColor Cyan
Set-AppSettingsFromHashtable -ResourceGroup $config.ResourceGroup -App $config.FrontendApp -Settings @{
    WEBSITES_PORT        = '80'
    WEBSITES_ENABLE_APP_SERVICE_STORAGE = 'false'
    BACKEND_ORIGIN       = "https://$backendHost"
    BACKEND_HOST         = $backendHost
    BACKEND_PROXY_SECRET = $proxySecret
}

Write-Host "`nNetwork isolation check" -ForegroundColor Cyan
# Frontend -> backend isolation is NETWORK-level (15-Provision-Network.ps1): both apps are VNet-integrated in snet-app,
# which has the Microsoft.Web service endpoint, and the backend admits only that subnet (default deny). No shared-IP
# rules are used (the plan's outbound IPs are shared with other apps). The proxy-key header remains an additional layer.
$restrictions = Find-AzResource -Arguments @('webapp', 'config', 'access-restriction', 'show', '--resource-group', $config.ResourceGroup,
                                             '--name', $config.BackendApp)
if (-not (Test-DryRun)) {
    $subnetRule = @($restrictions.ipSecurityRestrictions | Where-Object { $_.vnetSubnetResourceId -and $_.action -eq 'Allow' })
    $ipRules = @($restrictions.ipSecurityRestrictions | Where-Object { $_.ipAddress -and $_.ipAddress -ne 'Any' -and $_.action -eq 'Allow' })
    if ($subnetRule.Count -eq 0 -or $ipRules.Count -gt 0) {
        throw 'The backend is not restricted to the VNet integration subnet (or still has IP allow rules): run 15-Provision-Network.ps1 first.'
    }
    Write-Host "  backend admits only: $(($subnetRule | ForEach-Object { $_.vnetSubnetResourceId.Split('/')[-1] }) -join ', ') (default deny)"
}

# PostgreSQL is PRIVATE (VNet-only, 15-Provision-Network.ps1 + 10-Provision-Database.ps1): the backend reaches it through
# its regional VNet integration and the private DNS zone. No database firewall rule is created - ever.
$server = Find-AzResource -Arguments @('postgres', 'flexible-server', 'show', '--resource-group', $config.ResourceGroup, '--name', $config.PgServer)
if ($server -and $server.network -and $server.network.publicNetworkAccess -ne 'Disabled') {
    throw "Server $($config.PgServer) allows public network access; refusing (private connectivity only)."
}
$backend = Find-AzResource -Arguments @('webapp', 'show', '--resource-group', $config.ResourceGroup, '--name', $config.BackendApp)
if ($backend -and -not $backend.virtualNetworkSubnetId) {
    Write-Warning 'The backend has no VNet integration yet (run 15-Provision-Network.ps1); it cannot reach the private database.'
}

foreach ($app in $config.BackendApp, $config.FrontendApp) {
    Invoke-Az -Arguments @('webapp', 'restart', '--resource-group', $config.ResourceGroup, '--name', $app)
}
Write-Host "`nConfigured. Next: 70-Verify-Deployment.ps1 -BaseUrl https://$($config.FrontendApp).azurewebsites.net" -ForegroundColor Cyan
