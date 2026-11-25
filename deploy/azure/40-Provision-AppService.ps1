<#
.SYNOPSIS
  Step 4 - App Service plan and the two Web Apps: REUSE what exists (discovered plan, existing backend app),
  create only what is missing; always apply the container image and security configuration.
.DESCRIPTION
  Both apps: system-assigned managed identity with AcrPull on the registry (no registry credentials), HTTPS only,
  TLS >= 1.2, FTP/FTPS and basic-auth publishing disabled, HTTP/2, Always On, no ARR affinity cookie, container
  logging to the file system. Health check: backend /ready (database, migrations, FAISS index, embedding model,
  configuration), frontend /healthz.
#>
param([string] $ConfigPath = (Join-Path $PSScriptRoot 'config.psd1'), [switch] $Execute, [switch] $HardenOnly)
# -HardenOnly: security settings of the EXISTING apps only (FTPS off, basic auth off, HTTP/2, TLS 1.2, HTTPS only,
# no ARR affinity, ACR pulls via managed identity, container logging). No image change, no health-check path, nothing
# created; the managed identity and AcrPull assignment are only checked (read-only).
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'OnboardAI.Azure.psm1') -Force
$notNeeded = @(); if ($HardenOnly) { $notNeeded = @('PgServer', 'PgHost', 'PgAdminUser') }
$config = Initialize-Deployment -ConfigPath $ConfigPath -Execute:$Execute -NotNeeded $notNeeded
$tags = @($config.Tags.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" })
$rg = $config.ResourceGroup

Invoke-Az -Arguments @('account', 'set', '--subscription', $config.SubscriptionId)
$plan = Find-AzResource -Arguments @('appservice', 'plan', 'show', '--resource-group', $rg, '--name', $config.PlanName)
if ($plan) { Write-Host "  reusing plan $($plan.name) ($($plan.sku.name), linux=$($plan.reserved))" }
elseif ($HardenOnly -and -not (Test-DryRun)) { throw "Plan $($config.PlanName) not found; -HardenOnly creates nothing." }
else {
    Invoke-Az -Arguments (@('appservice', 'plan', 'create', '--resource-group', $rg, '--name', $config.PlanName,
        '--location', $config.Location, '--is-linux', '--sku', $config.PlanSku, '--number-of-workers', '1', '--tags') + $tags)
}
$acr = Find-AzResource -Arguments @('acr', 'show', '--name', $config.AcrName) -DryRunResult ([pscustomobject]@{ id = '<acr-resource-id>' })
if (-not $acr) { throw "Registry $($config.AcrName) not found (run 20-Provision-Registry.ps1)." }

$apps = @(
    @{ Name = $config.BackendApp;  Component = 'backend';  Health = '/ready';   Port = 8000 },
    @{ Name = $config.FrontendApp; Component = 'frontend'; Health = '/healthz'; Port = 80 }
)
foreach ($app in $apps) {
    Write-Host "`nWeb App $($app.Name)" -ForegroundColor Cyan
    $image = Get-ImageName -Config $config -Component $app.Component
    $existing = Find-AzResource -Arguments @('webapp', 'show', '--resource-group', $rg, '--name', $app.Name)
    if ($HardenOnly) {
        if (-not $existing -and -not (Test-DryRun)) { throw "Web App $($app.Name) not found; -HardenOnly creates nothing." }
        if ($existing) {
            $principal = $existing.identity.principalId
            $assigned = Find-AzResource -Arguments @('role', 'assignment', 'list', '--assignee', $principal, '--scope', $acr.id, '--role', 'AcrPull')
            Write-Host "  identity $($existing.identity.type); AcrPull on the registry: $([bool]$assigned)"
            if (-not $assigned) { Write-Warning "No AcrPull assignment for $($app.Name) on $($config.AcrName) (not changed by -HardenOnly)." }
        }
        Invoke-Az -Arguments @('webapp', 'config', 'set', '--resource-group', $rg, '--name', $app.Name,
            '--always-on', 'true', '--ftps-state', 'Disabled', '--http20-enabled', 'true', '--min-tls-version', '1.2',
            '--acr-use-identity', 'true')
        Invoke-Az -Arguments @('webapp', 'update', '--resource-group', $rg, '--name', $app.Name,
            '--client-affinity-enabled', 'false', '--https-only', 'true', '--basic-auth', 'Disabled')
        Invoke-Az -Arguments @('webapp', 'log', 'config', '--resource-group', $rg, '--name', $app.Name,
            '--docker-container-logging', 'filesystem')
        continue
    }
    if ($existing) {
        Write-Host "  reusing existing app $($existing.defaultHostName)"
        $identity = Invoke-Az -Arguments @('webapp', 'identity', 'assign', '--resource-group', $rg, '--name', $app.Name) -Json `
                              -DryRunResult ([pscustomobject]@{ principalId = '<principal-id>' })
        $assigned = Find-AzResource -Arguments @('role', 'assignment', 'list', '--assignee', $identity.principalId,
                                                 '--scope', $acr.id, '--role', 'AcrPull')
        if (-not $assigned) {
            Invoke-Az -Arguments @('role', 'assignment', 'create', '--assignee-object-id', $identity.principalId,
                '--assignee-principal-type', 'ServicePrincipal', '--role', 'AcrPull', '--scope', $acr.id)
        }
        Set-WebAppImage -ResourceGroup $rg -App $app.Name -Image $image -Port $app.Port -ExistingApp $existing
    } else {
        Invoke-Az -Arguments (@('webapp', 'create', '--resource-group', $rg, '--plan', $config.PlanName,
            '--name', $app.Name, '--container-image-name', $image,
            '--assign-identity', '[system]', '--role', 'AcrPull', '--scope', $acr.id, '--acr-use-identity',
            '--https-only', 'true', '--min-tls-version', '1.2', '--basic-auth', 'Disabled', '--tags') + $tags)
    }
    Invoke-Az -Arguments @('webapp', 'config', 'set', '--resource-group', $rg, '--name', $app.Name,
        '--always-on', 'true', '--ftps-state', 'Disabled', '--http20-enabled', 'true', '--min-tls-version', '1.2',
        '--acr-use-identity', 'true', '--generic-configurations', "healthCheckPath=$($app.Health)")
    Invoke-Az -Arguments @('webapp', 'update', '--resource-group', $rg, '--name', $app.Name,
        '--client-affinity-enabled', 'false', '--https-only', 'true', '--basic-auth', 'Disabled')
    Invoke-Az -Arguments @('webapp', 'log', 'config', '--resource-group', $rg, '--name', $app.Name,
        '--docker-container-logging', 'filesystem')
}
Write-Host "`nApp Service ready. Next (private database): 15, 10, 50, then 65-Migrate-Database-InVNet.ps1." -ForegroundColor Cyan
