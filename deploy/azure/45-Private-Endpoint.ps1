<#
.SYNOPSIS
  Step 4.5 - PRIVATE ENDPOINT for the backend Web App, then backend public network access disabled.
.DESCRIPTION
  Run AFTER the database migration (65 needs the public SCM site for its tunnel) and after 40 activated the images.
  * private-endpoint-subnet (owner-created, unused): its PostgreSQL delegation is removed (a private endpoint cannot live
    in a delegated subnet); refuses if the subnet is in use.
  * Private DNS zone privatelink.azurewebsites.net linked to onboardai-vnet; private endpoint (group "sites") with a DNS
    zone group, so inside the VNet the backend host name resolves to the endpoint's private IP.
  * Backend publicNetworkAccess = Disabled: the main and SCM sites are reachable only through the private endpoint.
    The frontend (VNet-integrated, route-all) reaches the backend over the private endpoint.
  Reuses every existing object; creates only what is missing.
#>
param([string] $ConfigPath = (Join-Path $PSScriptRoot 'config.psd1'), [switch] $Execute, [switch] $SkipDisablePublicAccess)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'OnboardAI.Azure.psm1') -Force
$config = Initialize-Deployment -ConfigPath $ConfigPath -Execute:$Execute
$rg = $config.ResourceGroup
$vnet = if ($config.ContainsKey('VnetName')) { $config.VnetName } else { 'onboardai-vnet' }
$peSubnet = if ($config.ContainsKey('PeSubnetName')) { $config.PeSubnetName } else { 'private-endpoint-subnet' }
$zone = 'privatelink.azurewebsites.net'
$peName = "$($config.BackendApp)-pe"

Invoke-Az -Arguments @('account', 'set', '--subscription', $config.SubscriptionId)
$backend = Find-AzResource -Arguments @('webapp', 'show', '--resource-group', $rg, '--name', $config.BackendApp) `
                           -DryRunResult ([pscustomobject]@{ id = '<backend-site-id>' })
if (-not $backend) { throw "Backend $($config.BackendApp) not found." }

Write-Host "`nPrivate endpoint subnet" -ForegroundColor Cyan
$subnet = Find-AzResource -Arguments @('network', 'vnet', 'subnet', 'show', '--resource-group', $rg, '--vnet-name', $vnet, '--name', $peSubnet) `
                          -DryRunResult ([pscustomobject]@{ addressPrefix = '10.0.3.0/24'; delegations = @() })
if (-not $subnet) { throw "Subnet $peSubnet not found in $vnet (owner-created)." }
$delegations = @($subnet.delegations | Where-Object { $_ } | ForEach-Object { $_.serviceName })
$inUse = @($subnet.ipConfigurations | Where-Object { $_ }).Count + @($subnet.serviceAssociationLinks | Where-Object { $_ }).Count
$hasOurEndpoint = @($subnet.privateEndpoints | Where-Object { $_ -and $_.id -match "/privateEndpoints/$peName$" }).Count -gt 0
Write-Host "  $peSubnet ($($subnet.addressPrefix)); delegation: $($delegations -join ','); in use: $inUse"
if ($delegations.Count -gt 0) {
    if ($inUse -gt 0) { throw "Subnet $peSubnet is delegated and in use; refusing to change it." }
    Invoke-Az -Arguments @('network', 'vnet', 'subnet', 'update', '--resource-group', $rg, '--vnet-name', $vnet, '--name', $peSubnet,
        '--remove', 'delegations')
}
Invoke-Az -Arguments @('network', 'vnet', 'subnet', 'update', '--resource-group', $rg, '--vnet-name', $vnet, '--name', $peSubnet,
    '--disable-private-endpoint-network-policies', 'true')

Write-Host "`nPrivate DNS for App Service private endpoints" -ForegroundColor Cyan
if (Find-AzResource -Arguments @('network', 'private-dns', 'zone', 'show', '--resource-group', $rg, '--name', $zone)) { Write-Host "  reusing zone $zone" }
else { Invoke-Az -Arguments @('network', 'private-dns', 'zone', 'create', '--resource-group', $rg, '--name', $zone) }
if (Find-AzResource -Arguments @('network', 'private-dns', 'link', 'vnet', 'show', '--resource-group', $rg, '--zone-name', $zone, '--name', "$vnet-webapps")) {
    Write-Host '  reusing VNet link'
} else {
    Invoke-Az -Arguments @('network', 'private-dns', 'link', 'vnet', 'create', '--resource-group', $rg, '--zone-name', $zone,
        '--name', "$vnet-webapps", '--virtual-network', $vnet, '--registration-enabled', 'false')
}

Write-Host "`nBackend private endpoint" -ForegroundColor Cyan
if (Find-AzResource -Arguments @('network', 'private-endpoint', 'show', '--resource-group', $rg, '--name', $peName)) { Write-Host "  reusing $peName" }
else {
    Invoke-Az -Arguments @('network', 'private-endpoint', 'create', '--resource-group', $rg, '--name', $peName, '--location', $config.Location,
        '--vnet-name', $vnet, '--subnet', $peSubnet, '--private-connection-resource-id', $backend.id, '--group-id', 'sites',
        '--connection-name', "$peName-connection", '--nic-name', "$peName-nic")
}
# `dns-zone-group show` returns {} with exit 0 when the group is MISSING (CLI 2.91), so check for a real object
# (the first execution skipped the creation because of this).
$zoneGroup = Find-AzResource -Arguments @('network', 'private-endpoint', 'dns-zone-group', 'show', '--resource-group', $rg, '--endpoint-name', $peName, '--name', 'default')
if ($zoneGroup -and $zoneGroup.name) {
    Write-Host '  reusing DNS zone group'
} else {
    Invoke-Az -Arguments @('network', 'private-endpoint', 'dns-zone-group', 'create', '--resource-group', $rg, '--endpoint-name', $peName,
        '--name', 'default', '--private-dns-zone', $zone, '--zone-name', 'sites')
}
$pe = Find-AzResource -Arguments @('network', 'private-endpoint', 'show', '--resource-group', $rg, '--name', $peName)
if ($pe) {
    $state = $pe.privateLinkServiceConnections[0].privateLinkServiceConnectionState.status
    Write-Host "  endpoint provisioning: $($pe.provisioningState); connection: $state"
    if ($state -ne 'Approved') { throw "Private endpoint connection is $state (expected Approved)." }
}

if ($SkipDisablePublicAccess) { Write-Warning 'Backend public network access left unchanged (-SkipDisablePublicAccess).' }
else {
    Write-Host "`nBackend public network access -> Disabled (main and SCM sites only through the private endpoint)" -ForegroundColor Cyan
    Invoke-Az -Arguments @('resource', 'update', '--ids', $backend.id, '--set', 'properties.publicNetworkAccess=Disabled')
}
Write-Host "`nBackend private endpoint ready. Next: 70-Verify-Deployment.ps1 (frontend -> backend over the private endpoint)." -ForegroundColor Cyan
