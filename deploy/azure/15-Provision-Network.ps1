<#
.SYNOPSIS
  Step 1.5 - PRIVATE networking for PostgreSQL: VNet, delegated subnets, private DNS zone + VNet link, and regional
  VNet integration of the backend Web App (all outbound traffic routed through the VNet). Reuse what exists.
.DESCRIPTION
  * snet-postgres (delegated to Microsoft.DBforPostgreSQL/flexibleServers): the server's private interface.
  * snet-app (delegated to Microsoft.Web/serverFarms): App Service regional VNet integration of the backend.
  * Private DNS zone <server>.private.postgres.database.azure.com linked to the VNet (no auto-registration), so the
    server FQDN resolves to its private address inside the VNet only.
  NOTE (24 Nov 2026): the sandbox policy "Allowed resource types" currently DENIES Microsoft.Network/privateDnsZones
  and privateDnsZones/virtualNetworkLinks; run 00-Preflight.ps1 -Execute after the exception to confirm.
  The database server itself is created PRIVATE by 10-Provision-Database.ps1 (no public access, no firewall rules).
#>
param([string] $ConfigPath = (Join-Path $PSScriptRoot 'config.psd1'), [switch] $Execute)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'OnboardAI.Azure.psm1') -Force
$config = Initialize-Deployment -ConfigPath $ConfigPath -Execute:$Execute
$rg = $config.ResourceGroup
$vnet = if ($config.ContainsKey('VnetName')) { $config.VnetName } else { 'onboardai-vnet' }
$prefix = if ($config.ContainsKey('VnetPrefix')) { $config.VnetPrefix } else { '10.20.0.0/16' }
$pgSubnet = @{ Name = 'snet-postgres'; Prefix = $(if ($config.ContainsKey('PgSubnetPrefix')) { $config.PgSubnetPrefix } else { '10.20.1.0/24' }); Delegation = 'Microsoft.DBforPostgreSQL/flexibleServers' }
$appSubnet = @{ Name = 'snet-app'; Prefix = $(if ($config.ContainsKey('AppSubnetPrefix')) { $config.AppSubnetPrefix } else { '10.20.2.0/24' }); Delegation = 'Microsoft.Web/serverFarms' }
$zone = "$($config.PgServer).private.postgres.database.azure.com"
$tags = @($config.Tags.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" })

Invoke-Az -Arguments @('account', 'set', '--subscription', $config.SubscriptionId)
if (Find-AzResource -Arguments @('network', 'vnet', 'show', '--resource-group', $rg, '--name', $vnet)) { Write-Host "  reusing VNet $vnet" }
else {
    Invoke-Az -Arguments (@('network', 'vnet', 'create', '--resource-group', $rg, '--name', $vnet, '--location', $config.Location,
        '--address-prefixes', $prefix, '--tags') + $tags)
}
foreach ($s in $pgSubnet, $appSubnet) {
    if (Find-AzResource -Arguments @('network', 'vnet', 'subnet', 'show', '--resource-group', $rg, '--vnet-name', $vnet, '--name', $s.Name)) {
        Write-Host "  reusing subnet $($s.Name)"
    } else {
        Invoke-Az -Arguments @('network', 'vnet', 'subnet', 'create', '--resource-group', $rg, '--vnet-name', $vnet, '--name', $s.Name,
            '--address-prefixes', $s.Prefix, '--delegations', $s.Delegation, '--default-outbound', 'false')
    }
}
# Service endpoint Microsoft.Web on the integration subnet: the backend's access restriction can then admit ONLY traffic
# from this subnet (frontend + backend VNet integration) - network isolation without shared IPs or headers.
Invoke-Az -Arguments @('network', 'vnet', 'subnet', 'update', '--resource-group', $rg, '--vnet-name', $vnet,
    '--name', $appSubnet.Name, '--service-endpoints', 'Microsoft.Web')
if (Find-AzResource -Arguments @('network', 'private-dns', 'zone', 'show', '--resource-group', $rg, '--name', $zone)) { Write-Host "  reusing zone $zone" }
else { Invoke-Az -Arguments (@('network', 'private-dns', 'zone', 'create', '--resource-group', $rg, '--name', $zone, '--tags') + $tags) }
if (Find-AzResource -Arguments @('network', 'private-dns', 'link', 'vnet', 'show', '--resource-group', $rg, '--zone-name', $zone, '--name', "$vnet-link")) {
    Write-Host '  reusing VNet link'
} else {
    Invoke-Az -Arguments @('network', 'private-dns', 'link', 'vnet', 'create', '--resource-group', $rg, '--zone-name', $zone,
        '--name', "$vnet-link", '--virtual-network', $vnet, '--registration-enabled', 'false')
}

Write-Host "`nRegional VNet integration of BOTH apps (all outbound through the VNet)" -ForegroundColor Cyan
# backend -> private PostgreSQL; frontend -> backend via the Microsoft.Web service endpoint (backend admits only snet-app).
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
    '--rule-name', 'allow-snet-app', '--action', 'Allow', '--vnet-name', $vnet, '--subnet', $appSubnet.Name, '--priority', '100') -AllowFailure
Invoke-Az -Arguments @('webapp', 'config', 'access-restriction', 'set', '--resource-group', $rg, '--name', $config.BackendApp,
    '--default-action', 'Deny', '--use-same-restrictions-for-scm-site', 'false')
Write-Host "`nPrivate network ready. Next: 10-Provision-Database.ps1 (creates the server PRIVATE in $($pgSubnet.Name))." -ForegroundColor Cyan
