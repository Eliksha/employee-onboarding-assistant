<#
.SYNOPSIS
  Local validation of the deployment scripts - no Azure access, nothing executed against Azure.
.DESCRIPTION
  1. Parses every .ps1/.psm1 in deploy/azure with the PowerShell parser (syntax errors fail).
  2. Runs every step as a DRY RUN with config.example.psd1 and collects the Azure CLI commands it would run.
  3. For every distinct `az` sub-command, runs `az <sub-command> --help` locally and checks that the sub-command exists
     and that every flag used is documented by the installed Azure CLI.
  4. Checks that no dry-run output contains a value from the secrets file (redaction).
  Exit code 0 only when everything passes.
#>
param([string] $ConfigPath = (Join-Path $PSScriptRoot 'config.example.psd1'))
$ErrorActionPreference = 'Stop'
$failures = 0
function Report([string] $Name, [bool] $Ok, [string] $Detail = '') {
    if (-not $Ok) { $script:failures += 1 }
    Write-Host ($(if ($Ok) { 'PASS ' } else { 'FAIL ' }) + $Name + $(if (-not $Ok -and $Detail) { " :: $Detail" } else { '' })) -ForegroundColor $(if ($Ok) { 'Green' } else { 'Red' })
}

Write-Host '== 1. PowerShell syntax' -ForegroundColor Cyan
foreach ($file in Get-ChildItem -Path $PSScriptRoot -Include *.ps1, *.psm1 -Recurse) {
    $tokens = $null; $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors)
    Report "parse $($file.Name)" ($errors.Count -eq 0) (($errors | ForEach-Object { $_.Message }) -join '; ')
}

foreach ($data in Get-ChildItem -Path $PSScriptRoot -Filter *.psd1) {
    $ok = $true; try { $parsed = Import-PowerShellDataFile -LiteralPath $data.FullName -ErrorAction Stop; $ok = $parsed -is [hashtable] -and $parsed.Count -gt 5 } catch { $ok = $false }
    Report "data file $($data.Name) parses with settings" $ok
}

Write-Host "`n== 2. Dry run of every step" -ForegroundColor Cyan
$steps = @(
    @{ Script = '00-Preflight.ps1'; Args = @{} },
    @{ Script = '15-Provision-Network.ps1'; Args = @{} },
    @{ Script = '10-Provision-Database.ps1'; Args = @{} },
    @{ Script = '20-Provision-Registry.ps1'; Args = @{} },
    @{ Script = '30-Publish-Images.ps1'; Args = @{} },
    @{ Script = '40-Provision-AppService.ps1'; Args = @{} },
    @{ Script = '60-Migrate-Database.ps1'; Args = @{ SkipFirewall = $true } },
    @{ Script = '65-Migrate-Database-InVNet.ps1'; Args = @{ AllowTemporaryScmBasicAuth = $true } },
    @{ Script = '50-Configure-Apps.ps1'; Args = @{} },
    @{ Script = '90-Rollback.ps1'; Args = @{ PreviousTag = 'previous-tag' } }
)
$commands = New-Object System.Collections.Generic.List[string]
$allOutput = New-Object System.Text.StringBuilder
foreach ($step in $steps) {
    $arguments = $step.Args.Clone(); $arguments.ConfigPath = $ConfigPath
    try {
        $out = & (Join-Path $PSScriptRoot $step.Script) @arguments *>&1 | ForEach-Object { "$_" }
        [void]$allOutput.AppendLine(($out -join "`n"))
        $azLines = @($out | Where-Object { $_ -match '^\s*\[dry-run\] az ' } | ForEach-Object { ($_ -replace '^\s*\[dry-run\] ', '').Trim() })
        foreach ($line in $azLines) { $commands.Add($line) }
        Report "dry run $($step.Script) ($($azLines.Count) az commands, nothing executed)" $true
    } catch {
        Report "dry run $($step.Script)" $false $_.Exception.Message
    }
}

Write-Host "`n== 3. Azure CLI sub-commands and flags (az ... --help, local)" -ForegroundColor Cyan
$help = @{}
$checked = 0
foreach ($command in ($commands | Sort-Object -Unique)) {
    $tokens = @([regex]::Matches($command, '"[^"]*"|\S+') | ForEach-Object { $_.Value.Trim('"') })
    $sub = @(); $flags = @()
    foreach ($t in $tokens[1..($tokens.Count - 1)]) {
        if ($t.StartsWith('--')) { $flags += $t } elseif ($flags.Count -eq 0 -and -not $t.StartsWith('@') -and $t -match '^[a-z][a-z0-9-]*$') { $sub += $t } elseif ($flags.Count -eq 0) { break }
    }
    $key = $sub -join ' '
    if (-not $help.ContainsKey($key)) {
        $text = (& az @sub --help 2>&1 | Out-String)
        $help[$key] = @{ Ok = ($LASTEXITCODE -eq 0 -and $text -match 'Arguments'); Text = $text }
    }
    $missing = @($flags | Where-Object { $help[$key].Text -notmatch ('(?m)\s' + [regex]::Escape($_) + '(\s|$)') } | Sort-Object -Unique)
    $checked += 1
    Report "az $key $(($flags | Sort-Object -Unique) -join ' ')" ($help[$key].Ok -and $missing.Count -eq 0) ("unknown: " + ($missing -join ', '))
}
# Commands that only appear when Azure returns existing resources (not reached in a dry run).
$conditional = @(
    @{ Sub = @('postgres', 'flexible-server', 'restore'); Flags = @('--resource-group', '--name', '--source-server', '--restore-time'); Why = 'printed by 90-Rollback' },
    @{ Sub = @('webapp', 'sitecontainers', 'update'); Flags = @('--resource-group', '--name', '--container-name', '--image', '--target-port', '--is-main', '--system-assigned-identity'); Why = 'Set-WebAppImage, sitecontainers apps' },
    @{ Sub = @('webapp', 'sitecontainers', 'create'); Flags = @('--resource-group', '--name', '--container-name', '--image', '--target-port', '--is-main', '--system-assigned-identity'); Why = 'Set-WebAppImage, sitecontainers apps' },
    @{ Sub = @('webapp', 'sitecontainers', 'list'); Flags = @('--resource-group', '--name'); Why = 'Set-WebAppImage' },
    @{ Sub = @('webapp', 'identity', 'assign'); Flags = @('--resource-group', '--name'); Why = '40, existing app' },
    @{ Sub = @('role', 'assignment', 'list'); Flags = @('--assignee', '--scope', '--role'); Why = '40, existing app' },
    @{ Sub = @('role', 'assignment', 'create'); Flags = @('--assignee-object-id', '--assignee-principal-type', '--role', '--scope'); Why = '40, existing app' },
    @{ Sub = @('acr', 'update'); Flags = @('--name', '--admin-enabled'); Why = '20, existing registry' },
    @{ Sub = @('webapp', 'create-remote-connection'); Flags = @('--resource-group', '--name', '--port'); Why = '65 SCM tunnel' },
    @{ Sub = @('webapp', 'config', 'appsettings', 'delete'); Flags = @('--resource-group', '--name', '--setting-names'); Why = '65 key removal' },
    @{ Sub = @('postgres', 'flexible-server', 'update'); Flags = @('--resource-group', '--name', '--admin-password'); Why = 'printed: admin password rotation' },
    @{ Sub = @('network', 'vnet', 'subnet', 'show'); Flags = @('--resource-group', '--vnet-name', '--name'); Why = '15 reuse check' },
    @{ Sub = @('network', 'private-dns', 'link', 'vnet', 'show'); Flags = @('--resource-group', '--zone-name', '--name'); Why = '15 reuse check' },
    @{ Sub = @('webapp', 'config', 'access-restriction', 'show'); Flags = @('--resource-group', '--name'); Why = '50 isolation check' }
)
foreach ($c in $conditional) {
    $text = (& az @($c.Sub) --help 2>&1 | Out-String)
    $missing = @($c.Flags | Where-Object { $text -notmatch ('(?m)\s' + [regex]::Escape($_) + '(\s|$)') })
    Report "az $($c.Sub -join ' ') $($c.Flags -join ' ') ($($c.Why))" ($text -match 'Arguments' -and $missing.Count -eq 0) ("unknown: " + ($missing -join ', '))
}

Write-Host "`n== 4. Redaction" -ForegroundColor Cyan
$config = Import-PowerShellDataFile -LiteralPath $ConfigPath
$leaks = 0
if (Test-Path -LiteralPath $config.SecretsFile) {
    foreach ($line in Get-Content -LiteralPath $config.SecretsFile) {
        if ($line -match '^\s*([A-Z0-9_]*(PASSWORD|SECRET|KEY|TOKEN|ENDPOINT)[A-Z0-9_]*)\s*=\s*(.+)$') {
            $value = $Matches[3].Trim().Trim('"').Trim("'")
            if ($value.Length -ge 8 -and $allOutput.ToString().Contains($value)) { $leaks += 1 }
        }
    }
}
Report "no secrets-file value appears in any dry-run output" ($leaks -eq 0) "$leaks value(s) visible"

Write-Host "`n== 5. Private database only" -ForegroundColor Cyan
$public = @($commands | Where-Object { $_ -match 'postgres flexible-server firewall-rule' -or $_ -match '--public-access' })
Report 'no database firewall rule and no public database access in any step' ($public.Count -eq 0) ($public -join ' | ')

Write-Host "`n$checked distinct az command lines checked; failures: $failures" -ForegroundColor $(if ($failures) { 'Red' } else { 'Green' })
if ($failures) { exit 1 }
