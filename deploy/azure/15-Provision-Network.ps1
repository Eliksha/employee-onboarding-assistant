<#
.SYNOPSIS
  Step 1.5 - PRIVATE networking for PostgreSQL: VNet, delegated subnets, private DNS zone + VNet link, and regional
  VNet integration of the backend Web App (all outbound traffic routed through the VNet). Reuse what exists.
.DESCRIPTION
  * postgres-subnet (owner-created, delegated to PostgreSQL) and the VNet onboardai-vnet: REUSED, never created.
  * appservice-subnet (owner-created; re-delegated to Microsoft.Web/serverFarms, service endpoint Microsoft.Web): regional VNet integration of both apps.
  * Private DNS zone <server>.private.postgres.database.azure.com linked to the VNet (no auto-registration), so the
    server FQDN resolves to its private address inside the VNet only.
  Policy (25 Nov 2026): private DNS zones and VNet links are now allowed; the zone + link were created with the
  server in the portal. The server itself is REUSED by 10-Provision-Database.ps1 (no public access, no firewall rules).
#>
param([string] $ConfigPath = (Join-Path $PSScriptRoot 'config.psd1'), [switch] $Execute)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'OnboardAI.Azure.psm1') -Force
$config = Initialize-Deployment -ConfigPath $ConfigPath -Execute:$Execute
$rg = $config.ResourceGroup
# Actual resources (owner, Azure Portal): VNet onboardai-vnet (10.0.0.0/16), postgres-subnet (10.0.1.0/24, delegated to
# PostgreSQL) and the private server with its private DNS zone + VNet link. They are REUSED, never created here.
$vnet = if ($config.ContainsKey('VnetName')) { $config.VnetName } else { 'onboardai-vnet' }
$pgSubnetName = if ($config.ContainsKey('PgSubnetName')) { $config.PgSubnetName } else { 'postgres-subnet' }
$appSubnet = @{ Name = $(if ($config.ContainsKey('AppSubnetName')) { $config.AppSubnetName } else { 'appservice-subnet' })
                Prefix = $(if ($config.ContainsKey('AppSubnetPrefix')) { $config.AppSubnetPrefix } else { '10.0.2.0/24' })
                Delegation = 'Microsoft.Web/serverFarms' }

Invoke-Az -Arguments @('account', 'set', '--subscription', $config.SubscriptionId)
$vnetObj = Find-AzResource -Arguments @('network', 'vnet', 'show', '--resource-group', $rg, '--name', $vnet) `
                           -DryRunResult ([pscustomobject]@{ addressSpace = [pscustomobject]@{ addressPrefixes = @('10.0.0.0/16') } })
if (-not $vnetObj) { throw "VNet $vnet not found: it is created by the owner (portal), never by this script." }
Write-Host "  reusing VNet $vnet ($($vnetObj.addressSpace.addressPrefixes -join ', '))"
$pgSubnetObj = Find-AzResource -Arguments @('network', 'vnet', 'subnet', 'show', '--resource-group', $rg, '--vnet-name', $vnet, '--name', $pgSubnetName) `
                               -DryRunResult ([pscustomobject]@{ addressPrefix = '10.0.1.0/24' })
if (-not $pgSubnetObj) { throw "Subnet $pgSubnetName not found in $vnet (owner-created PostgreSQL subnet)." }
Write-Host "  reusing PostgreSQL subnet $pgSubnetName ($($pgSubnetObj.addressPrefix))"

# App Service integration subnet: reuse the owner's subnet (appservice-subnet). Regional VNet integration requires the
# delegation Microsoft.Web/serverFarms; the Microsoft.Web service endpoint lets the backend admit ONLY this subnet
# (network isolation without shared IPs or headers). An existing subnet is re-delegated only while it is unused.
$existingApp = Find-AzResource -Arguments @('network', 'vnet', 'subnet', 'show', '--resource-group', $rg, '--vnet-name', $vnet, '--name', $appSubnet.Name)
if ($existingApp) {
    $delegations = @($existingApp.delegations | ForEach-Object { $_.serviceName })
    # (Where-Object drops nulls: in PowerShell @($null).Count is 1)
    $inUse = @($existingApp.ipConfigurations | Where-Object { $_ }).Count + @($existingApp.serviceAssociationLinks | Where-Object { $_ }).Count
    Write-Host "  reusing subnet $($appSubnet.Name) ($($existingApp.addressPrefix); delegation: $($delegations -join ',')); in use: $inUse"
    if ($delegations -notcontains $appSubnet.Delegation -and $inUse -gt 0) {
        throw "Subnet $($appSubnet.Name) is delegated to $($delegations -join ',') and in use; choose another integration subnet."
    }
} else {
    Invoke-Az -Arguments @('network', 'vnet', 'subnet', 'create', '--resource-group', $rg, '--vnet-name', $vnet, '--name', $appSubnet.Name,
        '--address-prefixes', $appSubnet.Prefix, '--delegations', $appSubnet.Delegation, '--default-outbound', 'false')
}
Invoke-Az -Arguments @('network', 'vnet', 'subnet', 'update', '--resource-group', $rg, '--vnet-name', $vnet,
    '--name', $appSubnet.Name, '--delegations', $appSubnet.Delegation, '--service-endpoints', 'Microsoft.Web')

# Private DNS: taken from the server itself (portal-created zone + link); checked, never created here.
$server = Find-AzResource -Arguments @('postgres', 'flexible-server', 'show', '--resource-group', $rg, '--name', $config.PgServer)
if ($server) {
    if ($server.network.publicNetworkAccess -ne 'Disabled') { throw "Server $($config.PgServer) allows public access; private only." }
    $zoneId = [string]$server.network.privateDnsZoneArmResourceId
    $zone = $zoneId.Split('/')[-1]
    $links = Find-AzResource -Arguments @('network', 'private-dns', 'link', 'vnet', 'list', '--resource-group', $zoneId.Split('/')[4], '--zone-name', $zone)
    $linked = @($links | Where-Object { $_.virtualNetwork.id -match "/virtualNetworks/$vnet$" })
    if ($linked.Count -eq 0) { throw "Private DNS zone $zone is not linked to $vnet; the backend could not resolve the server." }
    Write-Host "  private DNS zone $zone linked to $vnet ($($linked[0].name))"
} elseif (-not (Test-DryRun)) {
    Write-Warning "Server $($config.PgServer) not provisioned yet: DNS zone/link are checked once it exists (re-run this step)."
}

Write-Host "`nRegional VNet integration of BOTH apps (all outbound through the VNet)" -ForegroundColor Cyan
# backend -> private PostgreSQL; frontend -> backend via the Microsoft.Web service endpoint (backend admits only the integration subnet).
foreach ($name in $config.BackendApp, $config.FrontendApp) {
    $app = Find-AzResource -Arguments @('webapp', 'show', '--resource-group', $rg, '--name', $name)
    if ($app -and $app.virtualNetworkSubnetId) { Write-Host "  $name already integrated: $($app.virtualNetworkSubnetId.Split('/')[-1])" }
    else {
        Invoke-Az -Arguments @('webapp', 'vnet-integration', 'add', '--resource-group', $rg, '--name', $name,
            '--vnet', $vnet, '--subnet', $appSubnet.Name)
    }
    Invoke-Az -Arguments @('webapp', 'config', 'set', '--resource-group', $rg, '--name', $name, '--vnet-route-all-enabled', 'true')
}
Write-Host "`nBackend inbound: only the integration subnet (default deny); the SCM site keeps its own (Entra-protected) access" -ForegroundColor Cyan
Invoke-Az -Arguments @('webapp', 'config', 'access-restriction', 'add', '--resource-group', $rg, '--name', $config.BackendApp,
    '--rule-name', 'allow-app-subnet', '--action', 'Allow', '--vnet-name', $vnet, '--subnet', $appSubnet.Name, '--priority', '100') -AllowFailure
Invoke-Az -Arguments @('webapp', 'config', 'access-restriction', 'set', '--resource-group', $rg, '--name', $config.BackendApp,
    '--default-action', 'Deny', '--use-same-restrictions-for-scm-site', 'false')
Write-Host "`nPrivate network ready. Next: 10-Provision-Database.ps1 (reuses the private server; TLS parameters and database)." -ForegroundColor Cyan
