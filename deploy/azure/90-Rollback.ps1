<#
.SYNOPSIS
  Rollback - point both Web Apps back to a previous image tag (application rollback), restart, optionally verify.
.DESCRIPTION
  Application rollback is safe and fast: images are immutable tags in ACR, App Service pulls the previous tag.
  The tag must exist in the registry for both components (checked first).
  Database: migrations 005/007/008 are additive, so an older image runs against the migrated schema only if it
  predates nothing it requires; images built from this release need migration 008 (present after migration).
  To recover DATA, use Azure point-in-time restore into a NEW server (a billable provisioning action - only with
  explicit approval): the command is printed by -ShowDatabaseRestore, never executed by this script.
.EXAMPLE
  .\90-Rollback.ps1 -ConfigPath .\config.psd1 -PreviousTag 78b80ee-202611241900            # dry run
  .\90-Rollback.ps1 -ConfigPath .\config.psd1 -PreviousTag 78b80ee-202611241900 -Execute -VerifyBaseUrl https://<frontend-host>
#>
param(
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'config.psd1'),
    [Parameter(Mandatory)] [string] $PreviousTag,
    [switch] $Execute,
    [string] $VerifyBaseUrl = '',
    [switch] $ShowDatabaseRestore,
    [string] $RestoreTime = '<UTC time, e.g. 2026-11-24T13:00:00Z>'
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'OnboardAI.Azure.psm1') -Force
$config = Initialize-Deployment -ConfigPath $ConfigPath -Execute:$Execute
Invoke-Az -Arguments @('account', 'set', '--subscription', $config.SubscriptionId)

foreach ($component in 'backend', 'frontend') {
    $tags = Find-AzResource -Arguments @('acr', 'repository', 'show-tags', '--name', $config.AcrName,
                                         '--repository', "onboardai-$component") -DryRunResult @($PreviousTag)
    if (-not (@($tags) -contains $PreviousTag)) { throw "Tag $PreviousTag not found for onboardai-$component in $($config.AcrName)." }
}
foreach ($pair in @(@($config.BackendApp, 'backend'), @($config.FrontendApp, 'frontend'))) {
    $image = Get-ImageName -Config $config -Component $pair[1] -Tag $PreviousTag
    Write-Host "`n$($pair[0]) -> $image" -ForegroundColor Cyan
    $existing = Find-AzResource -Arguments @('webapp', 'show', '--resource-group', $config.ResourceGroup, '--name', $pair[0])
    $port = 80; if ($pair[1] -eq 'backend') { $port = 8000 }
    Set-WebAppImage -ResourceGroup $config.ResourceGroup -App $pair[0] -Image $image -Port $port -ExistingApp $existing
    Invoke-Az -Arguments @('webapp', 'restart', '--resource-group', $config.ResourceGroup, '--name', $pair[0])
}
if ($ShowDatabaseRestore) {
    Write-Host "`nDatabase point-in-time restore (NOT executed; creates a new server - needs approval):" -ForegroundColor Yellow
    Write-Host "  az postgres flexible-server restore --resource-group $($config.ResourceGroup) --name $($config.PgServer)-restore --source-server $($config.PgServer) --restore-time $RestoreTime"
    Write-Host '  then point PG_HOST of the backend to the restored server (50-Configure-Apps.ps1) after verifying it.'
}
if ($VerifyBaseUrl -and -not (Test-DryRun)) {
    Start-Sleep -Seconds 60   # container pull + start
    & (Join-Path $PSScriptRoot '70-Verify-Deployment.ps1') -BaseUrl $VerifyBaseUrl
}
Write-Host "`nRollback to $PreviousTag $(if (Test-DryRun) { 'planned (dry run)' } else { 'applied' })." -ForegroundColor Cyan
