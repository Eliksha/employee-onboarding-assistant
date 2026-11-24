<#
.SYNOPSIS
  Step 0 - local and Azure preflight: tools, secrets (names only), subscription, resource providers, policy.
.DESCRIPTION
  Local checks (Azure CLI, Docker, secrets file keys) always run. Azure checks are read-only and run only with
  -Execute: signed-in account, subscription, provider registration, policy assignments on the resource group, and
  an ARM *validation* (az deployment group validate) of one resource of every required type, which evaluates
  Azure Policy (e.g. "Sandbox: Allowed resource types") WITHOUT creating anything.
.EXAMPLE
  .\00-Preflight.ps1 -ConfigPath .\config.psd1            # dry run
  .\00-Preflight.ps1 -ConfigPath .\config.psd1 -Execute   # read-only Azure checks
#>
param([string] $ConfigPath = (Join-Path $PSScriptRoot 'config.psd1'), [switch] $Execute)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'OnboardAI.Azure.psm1') -Force
$config = Initialize-Deployment -ConfigPath $ConfigPath -Execute:$Execute

Write-Host "`n[1/4] Local tools" -ForegroundColor Cyan
$az = Get-Command az -ErrorAction SilentlyContinue
if (-not $az) { throw 'Azure CLI (az) is not installed: https://learn.microsoft.com/cli/azure/install-azure-cli' }
$azVersion = (& az version --output json | ConvertFrom-Json).'azure-cli'
Write-Host "  Azure CLI $azVersion"
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) { throw 'Docker is required to build and publish the images.' }
Write-Host "  Docker $((& docker version --format '{{.Client.Version}}') 2>$null)"

Write-Host "`n[2/4] Secrets file (names only)" -ForegroundColor Cyan
$required = @('AZURE_OPENAI_ENDPOINT', 'AZURE_OPENAI_DEPLOYMENT', 'AZURE_OPENAI_API_KEY', 'ONBOARDAI_APP_DB_PASSWORD',
              'ONBOARDAI_READER_DB_PASSWORD', 'ONBOARDAI_SCOPE_SECRET')
$secrets = Read-SecretsFile -Path $config.SecretsFile -Required $required
foreach ($name in $required) { Write-Host "  $name present" }
if ($secrets.ContainsKey('AZURE_PG_ADMIN_PASSWORD')) { Write-Host '  AZURE_PG_ADMIN_PASSWORD present' }
else { Write-Warning 'AZURE_PG_ADMIN_PASSWORD is not in the secrets file yet (needed by 10-Provision-Database.ps1 -Execute).' }

Write-Host "`n[3/4] Subscription and resource providers (read-only)" -ForegroundColor Cyan
Invoke-Az -Arguments @('account', 'set', '--subscription', $config.SubscriptionId)
$account = Invoke-Az -Arguments @('account', 'show') -Json -DryRunResult ([pscustomobject]@{ name = '<subscription>'; user = [pscustomobject]@{ name = '<user>' } })
Write-Host "  subscription: $($account.name)"
foreach ($ns in 'Microsoft.Web', 'Microsoft.DBforPostgreSQL', 'Microsoft.ContainerRegistry', 'Microsoft.CognitiveServices') {
    $provider = Invoke-Az -Arguments @('provider', 'show', '--namespace', $ns) -Json -DryRunResult ([pscustomobject]@{ registrationState = '<dry-run>' })
    Write-Host "  $ns : $($provider.registrationState)"
    if (-not (Test-DryRun) -and $provider.registrationState -ne 'Registered') {
        Write-Warning "$ns is not registered; ask the subscription owner (registration is a subscription-level change)."
    }
}

Write-Host "`n[4/4] Azure Policy (read-only)" -ForegroundColor Cyan
$assignments = Invoke-Az -Arguments @('policy', 'assignment', 'list', '--resource-group', $config.ResourceGroup,
                                      '--disable-scope-strict-match') -Json -DryRunResult @()
foreach ($a in @($assignments)) { if ($a) { Write-Host "  policy assignment: $($a.displayName)" } }
$template = Join-Path $PSScriptRoot 'preflight-policy.json'
$suffix = Get-Random -Minimum 1000 -Maximum 9999
$result = Invoke-Az -Arguments @('deployment', 'group', 'validate', '--resource-group', $config.ResourceGroup,
                                 '--name', "onboardai-preflight-$suffix", '--template-file', $template,
                                 '--parameters', "location=$($config.Location)", "suffix=$suffix") -Json -AllowFailure `
                    -DryRunResult ([pscustomobject]@{ properties = [pscustomobject]@{ provisioningState = '<dry-run>' } })
if (-not (Test-DryRun)) {
    if ($null -eq $result) {
        Write-Warning 'Validation FAILED (see the message above): a policy or quota blocks the required resource types. Escalate before continuing.'
        exit 2
    }
    Write-Host "  validation: $($result.properties.provisioningState) - App Service plan/site, PostgreSQL flexible server and ACR are allowed" -ForegroundColor Green
}
Write-Host "`nPreflight finished." -ForegroundColor Cyan
