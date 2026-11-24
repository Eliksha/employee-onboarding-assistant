<#
.SYNOPSIS
  Step 1 - Azure Database for PostgreSQL Flexible Server (PostgreSQL 16): REUSE if it exists, otherwise create;
  always enforce TLS and ensure the application database.
.DESCRIPTION
  An existing server (found by name; see 05-Discover-Resources.ps1) is reused: no create call is made. A new server is
  created in public-access mode WITHOUT firewall rules (50-Configure-Apps.ps1 adds the backend's outbound IPs,
  60-Migrate-Database.ps1 temporarily adds the operator IP), password authentication for the administrator
  (AZURE_PG_ADMIN_PASSWORD in the secrets file) and 7-day point-in-time restore. In both cases
  require_secure_transport=on and TLS >= 1.2 are enforced and the database is created if missing.
#>
param([string] $ConfigPath = (Join-Path $PSScriptRoot 'config.psd1'), [switch] $Execute)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'OnboardAI.Azure.psm1') -Force
$config = Initialize-Deployment -ConfigPath $ConfigPath -Execute:$Execute
$tags = @($config.Tags.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" })

Invoke-Az -Arguments @('account', 'set', '--subscription', $config.SubscriptionId)
$server = Find-AzResource -Arguments @('postgres', 'flexible-server', 'show', '--resource-group', $config.ResourceGroup,
                                       '--name', $config.PgServer)
$vnet = if ($config.ContainsKey('VnetName')) { $config.VnetName } else { 'onboardai-vnet' }
$zone = "$($config.PgServer).private.postgres.database.azure.com"
if ($server) {
    Write-Host "  reusing existing server $($server.fullyQualifiedDomainName) (version $($server.version), $($server.state))"
    if ([string]$server.version -ne '16') { Write-Warning "Server version is $($server.version); the application is tested on PostgreSQL 16." }
    if ($server.network -and $server.network.publicNetworkAccess -ne 'Disabled') {
        throw "Server $($config.PgServer) allows public network access; this deployment requires a PRIVATE (VNet-only) server."
    }
} else {
    # PRIVATE ONLY: VNet-injected into the delegated subnet with the private DNS zone (15-Provision-Network.ps1).
    # No --public-access and no firewall rule is ever created.
    $secrets = Read-SecretsFile -Path $config.SecretsFile -Required @('AZURE_PG_ADMIN_PASSWORD')
    Invoke-Az -Arguments (@('postgres', 'flexible-server', 'create', '--resource-group', $config.ResourceGroup,
        '--name', $config.PgServer, '--location', $config.Location, '--version', $config.PgVersion,
        '--tier', $config.PgTier, '--sku-name', $config.PgSkuName, '--storage-size', [string]$config.PgStorageGb,
        '--storage-auto-grow', 'Enabled', '--backup-retention', '7', '--geo-redundant-backup', 'Disabled',
        '--vnet', $vnet, '--subnet', 'snet-postgres', '--private-dns-zone', $zone,
        '--password-auth', 'Enabled', '--microsoft-entra-auth', 'Disabled',
        '--admin-user', $config.PgAdminUser, '--admin-password', $secrets['AZURE_PG_ADMIN_PASSWORD'], '--yes', '--tags') + $tags)
}

foreach ($parameter in @(@('require_secure_transport', 'on'), @('ssl_min_protocol_version', 'TLSv1.2'))) {
    Invoke-Az -Arguments @('postgres', 'flexible-server', 'parameter', 'set', '--resource-group', $config.ResourceGroup,
        '--server-name', $config.PgServer, '--name', $parameter[0], '--value', $parameter[1])
}
$database = Find-AzResource -Arguments @('postgres', 'flexible-server', 'db', 'show', '--resource-group', $config.ResourceGroup,
                                         '--server-name', $config.PgServer, '--name', $config.PgDatabase)
if ($database) { Write-Host "  database $($config.PgDatabase) exists" }
else {
    Invoke-Az -Arguments @('postgres', 'flexible-server', 'db', 'create', '--resource-group', $config.ResourceGroup,
        '--server-name', $config.PgServer, '--name', $config.PgDatabase)
}
Write-Host "`nPostgreSQL ready for migration (TLS enforced)." -ForegroundColor Cyan
