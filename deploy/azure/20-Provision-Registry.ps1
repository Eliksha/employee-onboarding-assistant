<#
.SYNOPSIS
  Step 2 - Azure Container Registry: REUSE if it exists (admin user must be disabled), otherwise create Basic with the
  admin user disabled. App Service pulls with its managed identity (AcrPull, 40-Provision-AppService.ps1).
#>
param([string] $ConfigPath = (Join-Path $PSScriptRoot 'config.psd1'), [switch] $Execute)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'OnboardAI.Azure.psm1') -Force
$config = Initialize-Deployment -ConfigPath $ConfigPath -Execute:$Execute
$tags = @($config.Tags.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" })

Invoke-Az -Arguments @('account', 'set', '--subscription', $config.SubscriptionId)
$acr = Find-AzResource -Arguments @('acr', 'show', '--name', $config.AcrName)
if ($acr) {
    Write-Host "  reusing registry $($acr.loginServer) ($($acr.sku.name))"
    if ($acr.adminUserEnabled) {
        Write-Warning 'The registry admin user is ENABLED; disabling it (managed identity is used instead).'
        Invoke-Az -Arguments @('acr', 'update', '--name', $config.AcrName, '--admin-enabled', 'false')
    }
} else {
    Invoke-Az -Arguments (@('acr', 'create', '--resource-group', $config.ResourceGroup, '--name', $config.AcrName,
        '--location', $config.Location, '--sku', 'Basic', '--admin-enabled', 'false', '--tags') + $tags)
}
Write-Host "`nRegistry ready." -ForegroundColor Cyan
