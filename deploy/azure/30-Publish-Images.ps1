<#
.SYNOPSIS
  Step 3 - build the production images, check them for secrets, push them to ACR.
.DESCRIPTION
  -BuildLocal builds and checks the images locally (no Azure access; allowed in a dry run). -Execute additionally
  signs in to the registry (az acr login, Entra ID token) and pushes both images tagged ImageTag.
  The images contain no secrets: the checks below fail the step if a secrets-file value, an .env file or a database
  dump is found in the image file system.
#>
param([string] $ConfigPath = (Join-Path $PSScriptRoot 'config.psd1'), [switch] $Execute, [switch] $BuildLocal)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'OnboardAI.Azure.psm1') -Force
$config = Initialize-Deployment -ConfigPath $ConfigPath -Execute:$Execute -NotNeeded @('PgServer', 'PgHost', 'PgAdminUser')   # images do not depend on the database
$root = Get-RepositoryRoot
$build = $BuildLocal.IsPresent -or $Execute.IsPresent
$images = @{
    backend  = @{ File = 'deploy/azure/backend.Dockerfile';  Local = "onboardai-backend:$($config.ImageTag)" }
    frontend = @{ File = 'deploy/azure/frontend.Dockerfile'; Local = "onboardai-frontend:$($config.ImageTag)" }
}

Push-Location $root
try {
    foreach ($component in 'backend', 'frontend') {
        $image = $images[$component]
        Write-Host "`nBuild $component" -ForegroundColor Cyan
        $env:DOCKER_BUILDKIT = '1'
        Invoke-Docker -Arguments @('build', '-f', $image.File, '-t', $image.Local, '.') -AlwaysRun:$build
    }

    if ($build) {
        Write-Host "`nImage checks (no secrets, dumps or .env files)" -ForegroundColor Cyan
        $secretValues = @()
        if (Test-Path -LiteralPath $config.SecretsFile) {
            # Credentials and endpoints only: plain identifiers in the file (role names such as onboardai_app) are
            # legitimately part of the application code and would be false positives.
            $all = Read-SecretsFile -Path $config.SecretsFile
            $secretValues = @($all.Keys | Where-Object { $_ -match '(PASSWORD|SECRET|KEY|TOKEN|ENDPOINT)' } |
                              ForEach-Object { $all[$_] } | Where-Object { $_ -and $_.Length -ge 8 })
        }
        foreach ($component in 'backend', 'frontend') {
            $local = $images[$component].Local
            $found = & docker run --rm --entrypoint sh $local -c "find / -xdev \( -name '*.env' -o -name '.env*' -o -name '*.dump' -o -name 'phase1*' -o -name '*.db' \) -not -path '/proc/*' 2>/dev/null"
            if ($found) { throw "$component image contains forbidden files: $found" }
            $paths = '/app /usr/share/nginx/html /etc/nginx'
            $content = & docker run --rm --entrypoint sh $local -c "cat `$(find $paths -type f -size -2M 2>/dev/null) 2>/dev/null"
            $text = ($content | Out-String)
            foreach ($value in $secretValues) {
                if ($text.Contains($value)) { throw "$component image contains a value from the secrets file (not printed)." }
            }
            $size = & docker image inspect $local --format '{{.Size}}'
            Write-Host ("  {0}: no secrets found; size {1:N0} MB" -f $component, ([double]$size / 1MB))
        }
    }

    $registry = (Get-ImageName -Config $config -Component backend).Split('/')[0]
    Write-Host "`nPush to $registry" -ForegroundColor Cyan
    Invoke-Az -Arguments @('account', 'set', '--subscription', $config.SubscriptionId)
    Invoke-Az -Arguments @('acr', 'login', '--name', $config.AcrName)
    foreach ($component in 'backend', 'frontend') {
        $remote = Get-ImageName -Config $config -Component $component
        Invoke-Docker -Arguments @('tag', $images[$component].Local, $remote)
        Invoke-Docker -Arguments @('push', $remote)
    }
}
finally { Pop-Location }
$outcome = 'published'
if (Test-DryRun) { $outcome = 'built locally; push planned (dry run)' }
Write-Host "`nImages $outcome (tag $($config.ImageTag))." -ForegroundColor Cyan
