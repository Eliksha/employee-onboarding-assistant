# Shared helpers for the OnboardAI Azure deployment scripts (Windows PowerShell 5.1 and PowerShell 7).
#
# Safety model
#   * Every script is a DRY RUN unless -Execute is passed: Azure CLI commands are printed (secrets redacted)
#     and recorded, never executed. Use the dry run to review the exact plan before any billable operation.
#   * Secrets are read from the external secrets file (KEY=VALUE lines) into memory only. They are never
#     printed (every displayed command is redacted) and never written to the repository. Application settings
#     go through a temporary JSON file (current user only) deleted immediately after use; database passwords
#     reach containers through inherited environment variables. One exception: `az postgres flexible-server
#     create` only accepts the administrator password as an argument, so it is visible to local process
#     inspection for the duration of that call (redacted on screen).

Set-StrictMode -Version 2.0

$script:DryRun = $true
$script:Secrets = @()
$script:CommandLog = New-Object System.Collections.Generic.List[string]

function Initialize-Deployment {
    param([Parameter(Mandatory)] [string] $ConfigPath, [switch] $Execute, [switch] $AllowPlaceholders,
          [string[]] $NotNeeded = @())   # keys this step does not use: they may still be placeholders
    if (-not (Test-Path -LiteralPath $ConfigPath)) {
        throw "Configuration file not found: $ConfigPath (copy deploy/azure/config.example.psd1 to deploy/azure/config.psd1)"
    }
    try { $config = Import-PowerShellDataFile -LiteralPath $ConfigPath -ErrorAction Stop }
    catch { throw "Configuration file $ConfigPath is not a valid PowerShell data file: $($_.Exception.Message)" }
    if ($null -eq $config -or $config -isnot [hashtable]) { throw "Configuration file $ConfigPath did not produce settings." }
    foreach ($key in 'SubscriptionId', 'ResourceGroup', 'Location', 'Prefix', 'BackendApp', 'FrontendApp', 'PlanName',
                     'PlanSku', 'AcrName', 'PgServer', 'PgDatabase', 'PgAdminUser', 'SecretsFile', 'ImageTag') {
        if (-not $config.ContainsKey($key) -or [string]::IsNullOrWhiteSpace([string]$config[$key])) {
            throw "Configuration value '$key' is missing in $ConfigPath"
        }
    }
    $script:DryRun = -not $Execute.IsPresent
    $mode = 'DRY RUN (nothing is executed; pass -Execute to run)'
    if (-not $script:DryRun) { $mode = 'EXECUTE' }
    Write-Host "OnboardAI Azure deployment - mode: $mode" -ForegroundColor Cyan
    if (-not $script:DryRun -and -not $AllowPlaceholders) {
        foreach ($k in $config.Keys) {
            if ($NotNeeded -contains $k) { continue }
            if ([string]$config[$k] -match '<[^>]+>') { throw "Configuration value '$k' still contains a placeholder: $($config[$k])" }
        }
    }
    return $config
}

function Test-DryRun { return $script:DryRun }

function Get-CommandLog { return , $script:CommandLog.ToArray() }

function Read-SecretsFile {
    <# KEY=VALUE lines; '#' comments and blank lines ignored; values stay in memory and are registered for redaction. #>
    param([Parameter(Mandatory)] [string] $Path, [string[]] $Required = @())
    $values = @{}
    if (-not (Test-Path -LiteralPath $Path)) {
        if ($script:DryRun) {
            Write-Warning "Secrets file not found ($Path); dry run continues with placeholders."
            foreach ($name in $Required) { $values[$name] = "<$name>" }
            return $values
        }
        throw "Secrets file not found: $Path"
    }
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if ($trimmed -eq '' -or $trimmed.StartsWith('#')) { continue }
        $index = $trimmed.IndexOf('=')
        if ($index -lt 1) { continue }
        $name = $trimmed.Substring(0, $index).Trim()
        $value = $trimmed.Substring($index + 1).Trim().Trim('"').Trim("'")
        $values[$name] = $value
        # Redact credentials (and endpoints) on screen; plain identifiers such as role names stay readable.
        if ($value.Length -ge 6 -and $name -match '(PASSWORD|SECRET|KEY|TOKEN|ENDPOINT)') { Register-Secret $value }
    }
    $missing = @($Required | Where-Object { -not $values.ContainsKey($_) -or [string]::IsNullOrWhiteSpace($values[$_]) })
    if ($missing.Count -gt 0) {
        if ($script:DryRun) {   # a dry run may plan without them; -Execute refuses
            Write-Warning "Secrets file lacks: $($missing -join ', ') - required before -Execute."
            foreach ($name in $missing) { $values[$name] = "<$name>" }
        } else {
            throw "Secrets file lacks: $($missing -join ', ') (names only; values are never printed)"
        }
    }
    return $values
}

function Register-Secret { param([string] $Value) if ($Value) { $script:Secrets += $Value } }

function Protect-Text {
    param([string] $Text)
    $result = $Text
    foreach ($secret in $script:Secrets) { if ($secret) { $result = $result.Replace($secret, '***') } }
    return $result
}

function New-RandomSecret {
    param([int] $Bytes = 36)
    $buffer = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($buffer) } finally { $rng.Dispose() }
    $value = [Convert]::ToBase64String($buffer).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    Register-Secret $value
    return $value
}

function Invoke-Az {
    <# Runs `az <args>` (or records it in a dry run). Returns parsed JSON when -Json is set. #>
    param([Parameter(Mandatory)] [string[]] $Arguments, [switch] $Json, [object] $DryRunResult = $null,
          [switch] $AllowFailure)
    $display = 'az ' + (($Arguments | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join ' ')
    $display = Protect-Text $display
    $script:CommandLog.Add($display)
    if ($script:DryRun) {
        Write-Host "  [dry-run] $display" -ForegroundColor DarkGray
        return $DryRunResult
    }
    Write-Host "  > $display" -ForegroundColor Gray
    $all = @($Arguments)
    if ($Json) { $all += @('--output', 'json') } else { $all += @('--output', 'none') }
    $output = & az @all 2>&1
    if ($LASTEXITCODE -ne 0) {
        $message = Protect-Text (($output | Out-String).Trim())
        if ($AllowFailure) { Write-Warning "az failed (allowed): $message"; return $null }
        throw "az command failed: $display`n$message"
    }
    if ($Json) {
        $text = ($output | Where-Object { $_ -is [string] }) -join "`n"
        if ([string]::IsNullOrWhiteSpace($text)) { return $null }
        return $text | ConvertFrom-Json
    }
    return $null
}

function Invoke-Docker {
    param([Parameter(Mandatory)] [string[]] $Arguments, [switch] $AlwaysRun)
    $display = Protect-Text ('docker ' + ($Arguments -join ' '))
    $script:CommandLog.Add($display)
    if ($script:DryRun -and -not $AlwaysRun) { Write-Host "  [dry-run] $display" -ForegroundColor DarkGray; return }
    Write-Host "  > $display" -ForegroundColor Gray
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "docker command failed: $display" }
}

function Set-AppSettingsFromHashtable {
    <# App settings via a temporary JSON file (secrets never appear on a command line or in the console). #>
    param([Parameter(Mandatory)] [string] $ResourceGroup, [Parameter(Mandatory)] [string] $App,
          [Parameter(Mandatory)] [hashtable] $Settings)
    $names = ($Settings.Keys | Sort-Object) -join ', '
    Write-Host "  app settings for ${App}: $names" -ForegroundColor Gray
    if ($script:DryRun) {
        $script:CommandLog.Add("az webapp config appsettings set --resource-group $ResourceGroup --name $App --settings @<temporary json: $names>")
        Write-Host "  [dry-run] az webapp config appsettings set --resource-group $ResourceGroup --name $App --settings @<temp json>" -ForegroundColor DarkGray
        return
    }
    $path = Join-Path ([System.IO.Path]::GetTempPath()) ("onboardai-settings-" + [guid]::NewGuid().ToString('N') + '.json')
    try {
        $json = ($Settings | ConvertTo-Json -Compress)
        [System.IO.File]::WriteAllText($path, $json, (New-Object System.Text.UTF8Encoding($false)))
        & icacls $path /inheritance:r /grant:r "$($env:USERNAME):(R,W,D)" | Out-Null
        Invoke-Az -Arguments @('webapp', 'config', 'appsettings', 'set', '--resource-group', $ResourceGroup,
                               '--name', $App, '--settings', "@$path")
    }
    finally {
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
    }
}

function Get-ImageName {
    <# Uses the DISCOVERED registry login server (a TenantReuse/DNL-scoped ACR has a hashed host name). #>
    param([hashtable] $Config, [ValidateSet('backend', 'frontend')] [string] $Component, [string] $Tag = '')
    $server = "$($Config.AcrName).azurecr.io"
    if ($Config.ContainsKey('AcrLoginServer') -and $Config.AcrLoginServer -and $Config.AcrLoginServer -notmatch '<') { $server = $Config.AcrLoginServer }
    if (-not $Tag) { $Tag = $Config.ImageTag }
    return "$server/onboardai-${Component}:$Tag"
}

function Set-WebAppImage {
    <# Points a Web App at an image, for BOTH App Service container models:
       * "sitecontainers" apps (linuxFxVersion = SITECONTAINERS, e.g. created in the portal since 2025): the main
         site container is updated (or created) with the image, target port and system-assigned identity for ACR;
       * classic custom-container apps (linuxFxVersion = DOCKER|...): az webapp config container set. #>
    param([Parameter(Mandatory)] [string] $ResourceGroup, [Parameter(Mandatory)] [string] $App,
          [Parameter(Mandatory)] [string] $Image, [Parameter(Mandatory)] [int] $Port, $ExistingApp = $null)
    $fx = ''
    if ($ExistingApp -and $ExistingApp.siteConfig) { $fx = [string]$ExistingApp.siteConfig.linuxFxVersion }
    if ($fx -match '^(?i)sitecontainers') {
        $containers = Find-AzResource -Arguments @('webapp', 'sitecontainers', 'list', '--resource-group', $ResourceGroup, '--name', $App)
        $main = @($containers) | Where-Object { $_ -and $_.isMain } | Select-Object -First 1
        $verb = 'create'; $containerName = 'main'
        if ($main) { $verb = 'update'; $containerName = $main.name }
        Invoke-Az -Arguments @('webapp', 'sitecontainers', $verb, '--resource-group', $ResourceGroup, '--name', $App,
            '--container-name', $containerName, '--image', $Image, '--target-port', [string]$Port, '--is-main', 'true',
            '--system-assigned-identity', 'true')
    } else {
        Invoke-Az -Arguments @('webapp', 'config', 'container', 'set', '--resource-group', $ResourceGroup, '--name', $App,
            '--container-image-name', $Image, '--container-registry-url', "https://$($Image.Split('/')[0])")
    }
}

function Find-AzResource {
    <# Read-only lookup: parsed JSON, or $null when the resource does not exist. Dry run: returns $DryRunResult. #>
    param([Parameter(Mandatory)] [string[]] $Arguments, [object] $DryRunResult = $null)
    $display = Protect-Text ('az ' + ($Arguments -join ' '))
    $script:CommandLog.Add($display)
    if ($script:DryRun) { Write-Host "  [dry-run] $display" -ForegroundColor DarkGray; return $DryRunResult }
    $all = @($Arguments) + @('--only-show-errors', '--output', 'json')
    $output = & az @all 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    $text = ($output | Where-Object { $_ -is [string] }) -join "`n"
    if ([string]::IsNullOrWhiteSpace($text)) { return $null }
    $parsed = $text | ConvertFrom-Json
    if ($parsed -is [array] -and $parsed.Count -eq 0) { return $null }
    return $parsed
}

function Get-RepositoryRoot { return (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path }

Export-ModuleMember -Function Initialize-Deployment, Test-DryRun, Get-CommandLog, Read-SecretsFile, Register-Secret,
    Protect-Text, New-RandomSecret, Invoke-Az, Invoke-Docker, Set-AppSettingsFromHashtable, Get-ImageName, Find-AzResource, Set-WebAppImage,
    Get-RepositoryRoot
