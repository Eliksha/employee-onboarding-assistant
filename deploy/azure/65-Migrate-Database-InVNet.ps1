<#
.SYNOPSIS
  Step 6 (PRIVATE database) - migrate the local PostgreSQL database into a VNet-only Azure Database for PostgreSQL
  through the App Service SSH tunnel of the backend Web App. No public database access, no firewall rules.
.DESCRIPTION
  Prerequisites: the backend Web App has regional VNet integration, the PostgreSQL server is private (delegated
  subnet + private DNS zone linked to the VNet), the backend app settings (PG_HOST = private FQDN, ...) are set
  (50-Configure-Apps.ps1), and both images were published (30-Publish-Images.ps1).

  1. Local (read-only on the source): one-time ed25519 key pair (current user only), pg_dump -Fc without sessions and
     rate-limit rows, restore list without RLS policies (re-created by 005), source data fingerprints.
  2. Azure (-Execute): build + push the TEMPORARY migration image (<tag>-migrate = production image + key-only sshd +
     PostgreSQL client), set MIGRATION_SSH_AUTHORIZED_KEY (public key) on the backend, switch the backend to the
     migration image (maintenance 503, application not started), open the authenticated SCM tunnel
     (az webapp create-remote-connection, bound to 127.0.0.1).
  3. Upload over SFTP/scp into /tmp/onboardai-migration (mode 700) and run `onboardai-in-vnet-migrate migrate` with the
     secrets on stdin: refuses a non-empty target; one-transaction restore; identical fingerprints; 008; 005; verify
     007/008/005; application role startup checks; automatic rollback to an empty database on any failure.
  4. ALWAYS (finally): shred the uploaded files, close the tunnel, delete MIGRATION_SSH_AUTHORIZED_KEY, switch the backend
     back to the PRODUCTION image (no SSH server), delete the local key pair and dump.
  Afterwards: rotate the PostgreSQL administrator password (printed command; needs approval) and run 70-Verify.

  Rollback: -Rollback runs `onboardai-in-vnet-migrate rollback --confirm` (empty target database again) through the same
  secured path. The source database and the local backup are never changed.
  Local rehearsal: -SkipAzure -SshHost 127.0.0.1 -SshPort <port> -SshKeyPath <key> against a local migration container.
#>
param(
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'config.psd1'),
    [switch] $Execute,
    [switch] $Rollback,
    [string] $SourceContainer = 'employee-onboarding-assistant-db-1',
    [string] $SourceUser = 'onboardai',
    [string] $SourceDatabase = 'onboardai',
    [string] $AdminPasswordKey = 'AZURE_PG_ADMIN_PASSWORD',
    [string] $LocalBackendImage = '',
    [int] $TunnelPort = 52222,
    [switch] $SkipAzure,
    [string] $SshHost = '127.0.0.1',
    [int] $SshPort = 0,
    [string] $SshKeyPath = '',
    # az webapp create-remote-connection (CLI 2.91) authenticates the SCM tunnel with the app's PUBLISHING credentials
    # (HTTP Basic). With SCM basic auth disabled the tunnel is refused, so this switch (owner approval required)
    # enables SCM basic auth ONLY for the migration window; the cleanup always disables it again and regenerates the
    # publishing password, invalidating the credential the tunnel used. FTP basic auth is never enabled.
    [switch] $AllowTemporaryScmBasicAuth
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'OnboardAI.Azure.psm1') -Force
$config = Initialize-Deployment -ConfigPath $ConfigPath -Execute:$Execute
$secrets = Read-SecretsFile -Path $config.SecretsFile -Required @($AdminPasswordKey, 'ONBOARDAI_APP_DB_PASSWORD',
    'ONBOARDAI_READER_DB_PASSWORD', 'ONBOARDAI_SCOPE_SECRET')
if (-not $LocalBackendImage) { $LocalBackendImage = "onboardai-backend:$($config.ImageTag)" }
$prodImage = Get-ImageName -Config $config -Component backend
$migrateImage = Get-ImageName -Config $config -Component backend -Tag "$($config.ImageTag)-migrate"
$rg = $config.ResourceGroup; $app = $config.BackendApp
$ssh = Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'; $scp = Join-Path $env:WINDIR 'System32\OpenSSH\scp.exe'
$keygen = Join-Path $env:WINDIR 'System32\OpenSSH\ssh-keygen.exe'
$work = Join-Path ([System.IO.Path]::GetTempPath()) ('onboardai-vnet-migration-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$tables = @('employees', 'leave_balances', 'assets', 'payroll_calendar', 'checklist', 'checklist_assignments', 'tickets',
            'messages', 'feedback', 'escalations', 'user_accounts')
$fingerprintSql = (($tables | ForEach-Object {
    "SELECT '$_' AS t, count(*) AS n, md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) AS h FROM public.$_ x"
}) + "SELECT 'scope_key', count(*), md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) FROM onboardai_private.scope_key x") -join "`nUNION ALL "
$fingerprintSql += "`nORDER BY 1;"
$tunnel = $null; $switched = $false; $keySet = $false; $scmBasicEnabled = $false
$scmPolicy = @('--resource-group', $rg, '--namespace', 'Microsoft.Web', '--resource-type', 'basicPublishingCredentialsPolicies',
               '--parent', "sites/$app", '--name', 'scm')

function Write-Utf8NoBom([string] $Path, [string] $Text) {
    [System.IO.File]::WriteAllText($Path, $Text.Replace("`r`n", "`n"), (New-Object System.Text.UTF8Encoding($false)))
}
function Invoke-Native([string] $Exe, [string[]] $Arguments, [string] $StdIn = $null) {
    Write-Host ("  > " + (Split-Path $Exe -Leaf) + ' ' + (Protect-Text ($Arguments -join ' '))) -ForegroundColor Gray
    if (Test-DryRun) { return }
    # Windows PowerShell 5.1 turns any stderr line of a native tool into an error record; success is the exit code.
    $previous = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    $previousEncoding = $global:OutputEncoding
    $global:OutputEncoding = New-Object System.Text.UTF8Encoding($false)   # stdin to native tools: UTF-8 without BOM
    try {
        if ($null -ne $StdIn) { $StdIn | & $Exe @Arguments 2>&1 | ForEach-Object { "$_" } }
        else { & $Exe @Arguments 2>&1 | ForEach-Object { "$_" } }
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previous; $global:OutputEncoding = $previousEncoding }
    if ($code -ne 0) { throw "$(Split-Path $Exe -Leaf) failed (exit $code)" }
}

try {
    Write-Host "`n[1/4] Prepare locally (source is only read)" -ForegroundColor Cyan
    if (-not (Test-DryRun)) {
        New-Item -ItemType Directory -Path $work -Force | Out-Null
        & icacls $work /inheritance:r /grant:r "$($env:USERNAME):(OI)(CI)F" | Out-Null
    }
    $key = $SshKeyPath
    if (-not $key) {
        $key = Join-Path $work 'id_migration'
        Invoke-Native $keygen @('-q', '-t', 'ed25519', '-N', '""', '-C', 'onboardai-migration', '-f', $key)
    }
    $sshOptions = @('-i', $key, '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=accept-new',
                    '-o', "UserKnownHostsFile=$(Join-Path $work 'known_hosts')", '-o', 'PreferredAuthentications=publickey',
                    '-o', 'PasswordAuthentication=no', '-o', 'ConnectTimeout=20', '-o', 'ServerAliveInterval=30', '-o', 'LogLevel=ERROR')
    if (-not $Rollback) {
        Invoke-Docker -Arguments @('exec', $SourceContainer, 'pg_dump', '-U', $SourceUser, '-d', $SourceDatabase, '-Fc', '--no-owner',
            '--no-privileges', '--exclude-table-data=public.user_sessions', '--exclude-table-data=public.login_failures',
            '-f', '/tmp/onboardai_vnet_migration.dump')
        Invoke-Docker -Arguments @('cp', "${SourceContainer}:/tmp/onboardai_vnet_migration.dump", (Join-Path $work 'onboardai.dump'))
        Invoke-Docker -Arguments @('exec', $SourceContainer, 'rm', '-f', '/tmp/onboardai_vnet_migration.dump')
        if (-not (Test-DryRun)) {
            Write-Utf8NoBom (Join-Path $work 'fingerprint.sql') $fingerprintSql
            & docker cp (Join-Path $work 'fingerprint.sql') "${SourceContainer}:/tmp/onboardai_fingerprint.sql" | Out-Null
            $print = (& docker exec $SourceContainer psql -U $SourceUser -d $SourceDatabase -At -F '|' -f /tmp/onboardai_fingerprint.sql) -join "`n"
            & docker exec $SourceContainer rm -f /tmp/onboardai_fingerprint.sql | Out-Null
            if (-not $print) { throw 'Could not fingerprint the source database.' }
            Write-Utf8NoBom (Join-Path $work 'source_fingerprint.txt') ($print + "`n")
            $list = (& docker run --rm -v "${work}:/work" postgres:16-alpine pg_restore -l /work/onboardai.dump) |
                    Where-Object { $_ -notmatch ' (POLICY|ROW SECURITY) ' }
            Write-Utf8NoBom (Join-Path $work 'restore.list') (($list -join "`n") + "`n")
            Write-Host "  source fingerprints: $(@($print -split "`n").Count) objects; dump $([math]::Round((Get-Item (Join-Path $work 'onboardai.dump')).Length / 1KB, 1)) KB"
        }
    }

    if (-not $SkipAzure) {
        Write-Host "`n[2/4] Temporary migration image and SCM tunnel" -ForegroundColor Cyan
        Invoke-Az -Arguments @('account', 'set', '--subscription', $config.SubscriptionId)
        $root = Get-RepositoryRoot
        Invoke-Docker -Arguments @('build', '-f', (Join-Path $root 'deploy/azure/migration/migration.Dockerfile'), '--build-arg',
            "BASE_IMAGE=$LocalBackendImage", '-t', $migrateImage, $root)
        Invoke-Az -Arguments @('acr', 'login', '--name', $config.AcrName)
        Invoke-Docker -Arguments @('push', $migrateImage)
        $publicKey = if (Test-DryRun) { 'ssh-ed25519 <one-time public key>' } else { (Get-Content -LiteralPath "$key.pub" -Raw).Trim() }
        Set-AppSettingsFromHashtable -ResourceGroup $rg -App $app -Settings @{ MIGRATION_SSH_AUTHORIZED_KEY = $publicKey }
        $keySet = $true
        $existing = Find-AzResource -Arguments @('webapp', 'show', '--resource-group', $rg, '--name', $app)
        Set-WebAppImage -ResourceGroup $rg -App $app -Image $migrateImage -Port 8000 -ExistingApp $existing
        $switched = $true
        Invoke-Az -Arguments @('webapp', 'restart', '--resource-group', $rg, '--name', $app)
        if ($AllowTemporaryScmBasicAuth) {
            Write-Host '  temporarily enabling SCM basic auth for the tunnel (disabled again + password regenerated in cleanup)' -ForegroundColor Yellow
            Invoke-Az -Arguments (@('resource', 'update') + $scmPolicy + @('--set', 'properties.allow=true'))
            $scmBasicEnabled = $true
        } else {
            Write-Warning 'SCM basic auth stays disabled; az webapp create-remote-connection (CLI 2.91) needs it. Re-run with -AllowTemporaryScmBasicAuth (approval) if the tunnel is refused.'
        }
        Write-Host "  starting tunnel: az webapp create-remote-connection --resource-group $rg --name $app --port $TunnelPort"
        if (-not (Test-DryRun)) {
            Start-Sleep -Seconds 90   # image pull + container start
            $tunnel = Start-Process -FilePath 'az' -ArgumentList @('webapp', 'create-remote-connection', '--resource-group', $rg,
                '--name', $app, '--port', [string]$TunnelPort) -PassThru -WindowStyle Hidden
            $deadline = (Get-Date).AddMinutes(4)
            while (-not (Test-NetConnection -ComputerName 127.0.0.1 -Port $TunnelPort -InformationLevel Quiet -WarningAction SilentlyContinue)) {
                if ((Get-Date) -gt $deadline) { throw 'The SCM tunnel did not open within 4 minutes.' }
                Start-Sleep -Seconds 5
            }
        }
        $SshHost = '127.0.0.1'; $SshPort = $TunnelPort
    }
    if ($SshPort -le 0) { throw 'No SSH port: use the Azure tunnel (default) or -SkipAzure -SshPort for a rehearsal.' }
    $target = "appuser@$SshHost"
    $portArgs = @('-p', [string]$SshPort)

    # Parenthesised: in PowerShell the comma binds tighter than '+' (unparenthesised, all values became one line).
    $stdin = (@(('PG_ADMIN_USER=' + $config.PgAdminUser), ('PG_ADMIN_PASSWORD=' + $secrets[$AdminPasswordKey]),
                ('ONBOARDAI_APP_DB_PASSWORD=' + $secrets['ONBOARDAI_APP_DB_PASSWORD']),
                ('ONBOARDAI_READER_DB_PASSWORD=' + $secrets['ONBOARDAI_READER_DB_PASSWORD']),
                ('ONBOARDAI_SCOPE_SECRET=' + $secrets['ONBOARDAI_SCOPE_SECRET'])) -join "`n") + "`n"
    if ($Rollback) {
        Write-Host "`n[3/4] ROLLBACK: empty the target database (source and backups unchanged)" -ForegroundColor Yellow
        Invoke-Native $ssh ($sshOptions + $portArgs + @($target, 'onboardai-in-vnet-migrate', 'rollback', '--confirm')) $stdin
    } else {
        Write-Host "`n[3/4] Upload (scp over the tunnel) and migrate inside the VNet" -ForegroundColor Cyan
        $files = @('onboardai.dump', 'restore.list', 'fingerprint.sql', 'source_fingerprint.txt') | ForEach-Object { Join-Path $work $_ }
        Invoke-Native $scp ($sshOptions + @('-P', [string]$SshPort) + $files + @("${target}:/tmp/onboardai-migration/"))
        Invoke-Native $ssh ($sshOptions + $portArgs + @($target, 'onboardai-in-vnet-migrate', 'migrate')) $stdin
    }
}
finally {
    Write-Host "`n[4/4] Cleanup (always)" -ForegroundColor Cyan
    if ($SshPort -gt 0 -and -not (Test-DryRun) -and (Test-Path -LiteralPath $key -ErrorAction SilentlyContinue)) {
        try { Invoke-Native $ssh ($sshOptions + @('-p', [string]$SshPort, "appuser@$SshHost", 'onboardai-in-vnet-migrate', 'cleanup')) } catch { Write-Warning "remote cleanup: $_" }
    }
    if ($tunnel -and -not $tunnel.HasExited) { Stop-Process -Id $tunnel.Id -Force; Write-Host '  tunnel closed' }
    if ($scmBasicEnabled -or ((Test-DryRun) -and $AllowTemporaryScmBasicAuth)) {
        Invoke-Az -Arguments (@('resource', 'update') + $scmPolicy + @('--set', 'properties.allow=false'))
        $site = Find-AzResource -Arguments @('webapp', 'show', '--resource-group', $rg, '--name', $app) -DryRunResult ([pscustomobject]@{ id = '<site-resource-id>' })
        Invoke-Az -Arguments @('resource', 'invoke-action', '--ids', $site.id, '--action', 'newpassword') -AllowFailure
        Write-Host '  SCM basic auth disabled again; publishing password regenerated'
    }
    if (-not $SkipAzure) {
        if ($keySet -or (Test-DryRun)) {
            Invoke-Az -Arguments @('webapp', 'config', 'appsettings', 'delete', '--resource-group', $rg, '--name', $app,
                '--setting-names', 'MIGRATION_SSH_AUTHORIZED_KEY') -AllowFailure
        }
        if ($switched -or (Test-DryRun)) {
            $existing = Find-AzResource -Arguments @('webapp', 'show', '--resource-group', $rg, '--name', $app)
            Set-WebAppImage -ResourceGroup $rg -App $app -Image $prodImage -Port 8000 -ExistingApp $existing
            Invoke-Az -Arguments @('webapp', 'restart', '--resource-group', $rg, '--name', $app)
            Write-Host '  backend switched back to the production image (no SSH server)'
        }
    }
    if (Test-Path -LiteralPath $work) { Remove-Item -LiteralPath $work -Recurse -Force; Write-Host '  local key pair, dump and fingerprints deleted' }
    Write-Host "`nNext (needs approval): rotate the PostgreSQL administrator password, e.g." -ForegroundColor Yellow
    Write-Host "  az postgres flexible-server update --resource-group $rg --name $($config.PgServer) --admin-password <new value from the secrets file>"
}
