<#
.SYNOPSIS
  Step 6 - copy the local PostgreSQL database to Azure Database for PostgreSQL and provision roles, RLS and grants.
.DESCRIPTION
  Works with a NON-superuser administrator (as on Azure Flexible Server). All tools run in containers
  (postgres:16-alpine for pg_dump/pg_restore/psql, the production backend image for migrations 005/007/008).
    1. pg_dump (custom format, read-only) of the source container: no owners, no grants, without session rows
       (user_sessions) and rate-limit rows (login_failures). Accounts, Argon2 password hashes, the signed-scope key
       (onboardai_private.scope_key), chat history, feedback, escalations and all reference data are kept.
    2. pg_restore into the empty target database in ONE transaction, as the administrator (who becomes the owner),
       without the row-level-security policies (re-created by migration 005 for the target's roles).
    3. Data fingerprints (row count + MD5 of all rows, per table, plus the scope key) of source and target must be
       identical, otherwise the step stops.
    4. Migration 005 --apply (creates onboardai_app / onboardai_reader with the secrets-file passwords, grants, RLS,
       signed-scope verifier; the restored scope key is kept, not rotated), 007 --verify, 008 --apply/--verify,
       005 --verify (also proves the restored scope key matches ONBOARDAI_SCOPE_SECRET).
    5. The application role connects over TLS (verify-full) and passes the backend's startup checks.
  Every connection to the target uses sslmode=verify-full. The local dump is deleted at the end (-KeepDump keeps it).
  NOT for Azure: the OnboardAI database is private (VNet-only), so this script refuses to run without -SkipFirewall and never
  opens a firewall rule; use 65-Migrate-Database-InVNet.ps1 (App Service SSH tunnel) for Azure.
  For a local rehearsal (no Azure): -Execute -SkipFirewall -TargetHost/-TargetPort/-DockerNetwork/-CaBundle.
#>
param(
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'config.psd1'),
    [switch] $Execute,
    [string] $SourceContainer = 'employee-onboarding-assistant-db-1',
    [string] $SourceUser = 'onboardai',
    [string] $SourceDatabase = 'onboardai',
    [string] $TargetHost = '',
    [int] $TargetPort = 5432,
    [string] $TargetAdminUser = '',
    [string] $TargetDatabase = '',
    [string] $AdminPasswordKey = 'AZURE_PG_ADMIN_PASSWORD',
    [string] $CaBundle = '',
    [string] $DockerNetwork = '',
    [string] $BackendImage = '',
    [string] $OperatorIp = '',
    [switch] $SkipFirewall,
    [switch] $KeepDump
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'OnboardAI.Azure.psm1') -Force
$config = Initialize-Deployment -ConfigPath $ConfigPath -Execute:$Execute
$secrets = Read-SecretsFile -Path $config.SecretsFile -Required @($AdminPasswordKey, 'ONBOARDAI_APP_DB_PASSWORD',
    'ONBOARDAI_READER_DB_PASSWORD', 'ONBOARDAI_SCOPE_SECRET')
if (-not $TargetHost) {
    $TargetHost = "$($config.PgServer).postgres.database.azure.com"
    if ($config.ContainsKey('PgHost') -and $config.PgHost -and $config.PgHost -notmatch '<') { $TargetHost = $config.PgHost }
}
if (-not $TargetAdminUser) { $TargetAdminUser = $config.PgAdminUser }
if (-not $TargetDatabase) { $TargetDatabase = $config.PgDatabase }
if (-not $BackendImage) { $BackendImage = "onboardai-backend:$($config.ImageTag)" }

$work = Join-Path ([System.IO.Path]::GetTempPath()) ('onboardai-migration-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$network = @(); if ($DockerNetwork) { $network = @('--network', $DockerNetwork) }
$caMount = @(); $caPath = 'system'; $appCa = '/etc/ssl/certs/ca-certificates.crt'
if ($CaBundle) { $caMount = @('-v', "$((Resolve-Path -LiteralPath $CaBundle).Path):/ca/ca.pem:ro"); $caPath = '/ca/ca.pem'; $appCa = '/ca/ca.pem' }
$targetDsn = "host=$TargetHost port=$TargetPort dbname=$TargetDatabase user=$TargetAdminUser sslmode=verify-full sslrootcert=$caPath"
$tables = @('employees', 'leave_balances', 'assets', 'payroll_calendar', 'checklist', 'checklist_assignments', 'tickets',
            'messages', 'feedback', 'escalations', 'user_accounts')
$fingerprintSql = (($tables | ForEach-Object {
    "SELECT '$_' AS t, count(*) AS n, md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) AS h FROM public.$_ x"
}) + "SELECT 'scope_key', count(*), md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) FROM onboardai_private.scope_key x") -join "`nUNION ALL "
$fingerprintSql += "`nORDER BY 1;"

$envNames = @('PGPASSWORD', 'PG_ADMIN_PASSWORD', 'PG_PASSWORD', 'PG_READER_PASSWORD', 'PG_SCOPE_SECRET',
              'ONBOARDAI_APP_DB_PASSWORD', 'ONBOARDAI_READER_DB_PASSWORD', 'ONBOARDAI_SCOPE_SECRET')


function Invoke-Migration([string[]] $Command, [switch] $AsApp) {
    $base = @('run', '--rm') + $network + $caMount + @('-e', 'DB_BACKEND=postgresql', '-e', "PG_HOST=$TargetHost",
        '-e', "PG_PORT=$TargetPort", '-e', "PG_DATABASE=$TargetDatabase", '-e', 'PG_SSLMODE=verify-full',
        '-e', "PG_SSLROOTCERT=$appCa", '-e', 'HF_HUB_OFFLINE=1')
    if ($AsApp) {
        $base += @('-e', 'PG_USER=onboardai_app', '-e', 'PG_PASSWORD', '-e', 'PG_READER_USER=onboardai_reader',
                   '-e', 'PG_READER_PASSWORD', '-e', 'PG_SCOPE_SECRET')
    } else {
        $base += @('-e', "PG_ADMIN_USER=$TargetAdminUser", '-e', 'PG_ADMIN_PASSWORD', '-e', "PG_USER=$TargetAdminUser",
                   '-e', 'ONBOARDAI_APP_DB_PASSWORD', '-e', 'ONBOARDAI_READER_DB_PASSWORD', '-e', 'ONBOARDAI_SCOPE_SECRET')
    }
    Invoke-Docker -Arguments ($base + @($BackendImage) + $Command)
}

try {
    if (-not (Test-DryRun)) {
        New-Item -ItemType Directory -Path $work -Force | Out-Null
        & icacls $work /inheritance:r /grant:r "$($env:USERNAME):(OI)(CI)F" | Out-Null
        [System.IO.File]::WriteAllText((Join-Path $work 'fingerprint.sql'), $fingerprintSql, (New-Object System.Text.UTF8Encoding($false)))
        $env:PGPASSWORD = $secrets[$AdminPasswordKey]; $env:PG_ADMIN_PASSWORD = $secrets[$AdminPasswordKey]
        $env:ONBOARDAI_APP_DB_PASSWORD = $secrets['ONBOARDAI_APP_DB_PASSWORD']; $env:PG_PASSWORD = $secrets['ONBOARDAI_APP_DB_PASSWORD']
        $env:ONBOARDAI_READER_DB_PASSWORD = $secrets['ONBOARDAI_READER_DB_PASSWORD']; $env:PG_READER_PASSWORD = $secrets['ONBOARDAI_READER_DB_PASSWORD']
        $env:ONBOARDAI_SCOPE_SECRET = $secrets['ONBOARDAI_SCOPE_SECRET']; $env:PG_SCOPE_SECRET = $secrets['ONBOARDAI_SCOPE_SECRET']
    }

    if (-not $SkipFirewall) {
        # No public database access exists in this deployment, so this script never opens a firewall rule.
        throw ('The OnboardAI database is PRIVATE (VNet-only): no public firewall rules. Use 65-Migrate-Database-InVNet.ps1 ' +
               '(migration through the App Service SSH tunnel). This script is kept for local rehearsals only (-SkipFirewall).')
    }

    Write-Host "`n[1/5] Dump the source database (read-only)" -ForegroundColor Cyan
    Invoke-Docker -Arguments @('exec', $SourceContainer, 'pg_dump', '-U', $SourceUser, '-d', $SourceDatabase, '-Fc', '--no-owner',
        '--no-privileges', '--exclude-table-data=public.user_sessions', '--exclude-table-data=public.login_failures',
        '-f', '/tmp/onboardai_migration.dump')
    Invoke-Docker -Arguments @('cp', "${SourceContainer}:/tmp/onboardai_migration.dump", (Join-Path $work 'onboardai.dump'))
    Invoke-Docker -Arguments @('exec', $SourceContainer, 'rm', '-f', '/tmp/onboardai_migration.dump')
    Invoke-Docker -Arguments @('cp', (Join-Path $work 'fingerprint.sql'), "${SourceContainer}:/tmp/onboardai_fingerprint.sql")
    $sourcePrint = $null
    if (-not (Test-DryRun)) {
        $sourcePrint = (& docker exec $SourceContainer psql -U $SourceUser -d $SourceDatabase -At -F '|' -f /tmp/onboardai_fingerprint.sql) -join "`n"
        & docker exec $SourceContainer rm -f /tmp/onboardai_fingerprint.sql | Out-Null
        if ($LASTEXITCODE -ne 0 -or -not $sourcePrint) { throw 'Could not fingerprint the source database.' }
    }

    Write-Host "`n[2/5] Restore into $TargetHost/$TargetDatabase (one transaction, TLS verify-full)" -ForegroundColor Cyan
    $workMount = @('-v', "${work}:/work")
    Invoke-Docker -Arguments (@('run', '--rm') + $workMount + @('postgres:16-alpine', 'sh', '-c',
        "pg_restore -l /work/onboardai.dump | grep -v -E ' (POLICY|ROW SECURITY) ' > /work/restore.list"))
    Invoke-Docker -Arguments (@('run', '--rm') + $network + $caMount + $workMount + @('-e', 'PGPASSWORD', 'postgres:16-alpine',
        'pg_restore', '--no-owner', '--no-privileges', '--exit-on-error', '--single-transaction', '-L', '/work/restore.list',
        '-d', $targetDsn, '/work/onboardai.dump'))

    Write-Host "`n[3/5] Compare data fingerprints" -ForegroundColor Cyan
    if (-not (Test-DryRun)) {
        $targetPrint = (& docker run --rm @network @caMount @workMount -e PGPASSWORD postgres:16-alpine psql $targetDsn -At -F '|' -f /work/fingerprint.sql) -join "`n"
        if ($LASTEXITCODE -ne 0) { throw 'Could not fingerprint the target database.' }
        if ($targetPrint -ne $sourcePrint) {
            throw "Data fingerprints differ between source and target. Source:`n$sourcePrint`nTarget:`n$targetPrint"
        }
        foreach ($line in $targetPrint -split "`n") { $p = $line -split '\|'; Write-Host ("  {0,-22} rows {1,5}  identical" -f $p[0], $p[1]) }
    } else { Write-Host '  [dry-run] psql fingerprint.sql on source and target; stop unless identical' -ForegroundColor DarkGray }

    Write-Host "`n[4/5] Migration 008, roles, grants, row-level security; verify 005/007/008" -ForegroundColor Cyan
    # 008 first: 005 grants on every application table, including the ones 008 creates.
    Invoke-Migration @('python', 'backend/migrations/008_hr_escalation_queue.py', '--apply')
    Invoke-Migration @('python', 'backend/migrations/005_least_privilege_roles.py', '--apply')
    Invoke-Migration @('python', 'backend/migrations/007_data_integrity.py', '--verify')
    Invoke-Migration @('python', 'backend/migrations/008_hr_escalation_queue.py', '--verify')
    Invoke-Migration @('python', 'backend/migrations/005_least_privilege_roles.py', '--verify')

    Write-Host "`n[5/5] Application role: TLS connection and startup checks" -ForegroundColor Cyan
    Invoke-Migration @('python', '-c', "from backend.services import db; db.init_db(); print('application startup checks passed (TLS verify-full, least-privilege role, migrations 004/007/008)')") -AsApp
    Write-Host "`nMigration completed." -ForegroundColor Green
}
finally {
    foreach ($name in $envNames) { Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue }
    if ((Test-Path -LiteralPath $work) -and -not $KeepDump) { Remove-Item -LiteralPath $work -Recurse -Force }
    elseif (Test-Path -LiteralPath $work) { Write-Warning "Dump kept in $work (contains password hashes and the scope key: delete it after use)." }
}
