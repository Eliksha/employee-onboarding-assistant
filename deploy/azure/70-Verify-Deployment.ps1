<#
.SYNOPSIS
  Step 7 - post-deployment verification over HTTPS (read-only except one sign-in/sign-out and one chat question).
.DESCRIPTION
  Public checks: frontend health, security headers (HSTS, CSP 'self', X-Frame-Options, nosniff), API health,
  API docs and readiness not public, authentication required, generic login error, and - with -BackendUrl - that
  the backend cannot be used directly (App Service access restriction 403 or proxy-key 404).
  With -EmployeeEmail and -PasswordEnv (name of an environment variable holding the password, never a literal):
  sign-in with Secure/HttpOnly/SameSite=Strict cookie, own profile and checklist, another employee's data refused,
  a grounded GPT-4.1 answer citing handbook.pdf page 3, the out-of-scope fallback, history, sign-out.
  Exit code 0 only when every check passes. -TestCaFile trusts ONE extra root CA (local rehearsal only).
.EXAMPLE
  $env:VERIFY_PW = '<password>'; .\70-Verify-Deployment.ps1 -BaseUrl https://<frontend-host> -BackendUrl https://<backend-host> -EmployeeEmail <email> -PasswordEnv VERIFY_PW
#>
param(
    [Parameter(Mandatory)] [string] $BaseUrl,
    [string] $BackendUrl = '',
    [string] $EmployeeEmail = '',
    [string] $PasswordEnv = '',
    [string] $TestCaFile = ''
)
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$BaseUrl = $BaseUrl.TrimEnd('/')
if ($TestCaFile) {
    # Local rehearsal only: accept certificates that chain to this specific root (host name still checked).
    $root = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2((Resolve-Path $TestCaFile).Path)
    Add-Type -ReferencedAssemblies System.Net, System.Security -TypeDefinition @"
using System.Net; using System.Net.Security; using System.Security.Cryptography.X509Certificates;
public static class PinnedRoot {
    public static X509Certificate2 Root;
    public static bool Check(object s, X509Certificate c, X509Chain ch, SslPolicyErrors e) {
        if ((e & SslPolicyErrors.RemoteCertificateNameMismatch) != 0 || c == null) return false;
        var chain = new X509Chain();
        chain.ChainPolicy.RevocationMode = X509RevocationMode.NoCheck;
        chain.ChainPolicy.VerificationFlags = X509VerificationFlags.AllowUnknownCertificateAuthority;
        chain.ChainPolicy.ExtraStore.Add(Root);
        if (!chain.Build(new X509Certificate2(c))) return false;
        var top = chain.ChainElements[chain.ChainElements.Count - 1].Certificate;
        return top.Thumbprint == Root.Thumbprint;
    }
}
"@
    [PinnedRoot]::Root = $root
    [Net.ServicePointManager]::ServerCertificateValidationCallback = [System.Net.Security.RemoteCertificateValidationCallback] [PinnedRoot].GetMethod('Check').CreateDelegate([System.Net.Security.RemoteCertificateValidationCallback])
}

$results = New-Object System.Collections.Generic.List[bool]
function Test-Check([string] $Name, [bool] $Ok, [string] $Detail = '') {
    $results.Add($Ok)
    $line = $(if ($Ok) { 'PASS' } else { 'FAIL' }) + " $Name"
    if (-not $Ok -and $Detail) { $line += " :: $Detail" }
    Write-Host $line -ForegroundColor $(if ($Ok) { 'Green' } else { 'Red' })
}
function Invoke-Http([string] $Method, [string] $Url, $Body = $null, $Session = $null, [hashtable] $Headers = @{}) {
    $params = @{ Method = $Method; Uri = $Url; UseBasicParsing = $true; TimeoutSec = 90; Headers = $Headers; MaximumRedirection = 0 }
    if ($null -ne $Body) { $params.Body = ($Body | ConvertTo-Json -Compress); $params.ContentType = 'application/json' }
    if ($null -ne $Session) { $params.WebSession = $Session }
    try {
        $r = Invoke-WebRequest @params
        return [pscustomobject]@{ Status = [int]$r.StatusCode; Headers = $r.Headers; Body = $r.Content }
    } catch [System.Net.WebException] {
        $resp = $_.Exception.Response
        if ($null -eq $resp) { return [pscustomobject]@{ Status = 0; Headers = @{}; Body = $_.Exception.Message } }
        $headers = @{}; foreach ($k in $resp.Headers.AllKeys) { $headers[$k] = $resp.Headers[$k] }
        # Windows PowerShell 5.1 has usually consumed the error body already and exposes it as ErrorDetails.
        $body = if ($_.ErrorDetails -and $_.ErrorDetails.Message) { $_.ErrorDetails.Message } else {
            (New-Object System.IO.StreamReader($resp.GetResponseStream())).ReadToEnd() }
        return [pscustomobject]@{ Status = [int]$resp.StatusCode; Headers = $headers; Body = $body }
    }
}

Write-Host "== public checks ($BaseUrl)" -ForegroundColor Cyan
$r = Invoke-Http GET "$BaseUrl/healthz"
Test-Check 'frontend /healthz 200' ($r.Status -eq 200) "$($r.Status)"
$r = Invoke-Http GET "$BaseUrl/"
$csp = [string]$r.Headers['Content-Security-Policy']
Test-Check 'SPA 200 with HSTS, CSP self-only, X-Frame-Options DENY, nosniff' ($r.Status -eq 200 -and
    ([string]$r.Headers['Strict-Transport-Security']) -match 'max-age=31536000' -and $csp.StartsWith("default-src 'self'") -and
    $csp -notmatch 'https?://' -and $r.Headers['X-Frame-Options'] -eq 'DENY' -and $r.Headers['X-Content-Type-Options'] -eq 'nosniff') "$($r.Status) $csp"
$r = Invoke-Http GET "$BaseUrl/api/health"
Test-Check 'API health 200, database ok' ($r.Status -eq 200 -and $r.Body -match '"database"\s*:\s*"ok"') "$($r.Status) $($r.Body)"
Test-Check 'API docs not public (404)' ((Invoke-Http GET "$BaseUrl/api/docs").Status -eq 404)
Test-Check 'readiness details not public (404)' ((Invoke-Http GET "$BaseUrl/api/ready").Status -eq 404)
Test-Check 'employee data requires sign-in (401)' ((Invoke-Http GET "$BaseUrl/api/employees/EMP001").Status -eq 401)
$r = Invoke-Http POST "$BaseUrl/api/auth/login" @{ email = 'nobody@example.com'; password = 'wrong-password-123' }
Test-Check 'unknown account -> generic 401' ($r.Status -eq 401 -and $r.Body -match 'Invalid email or password') "$($r.Status)"
if ($BackendUrl) {
    $r = Invoke-Http GET "$($BackendUrl.TrimEnd('/'))/auth/me"
    Test-Check 'backend not usable directly (403 access restriction or 404 proxy key)' ($r.Status -in 403, 404) "$($r.Status)"
}

if ($EmployeeEmail -and $PasswordEnv) {
    Write-Host "== signed-in checks" -ForegroundColor Cyan
    $password = [Environment]::GetEnvironmentVariable($PasswordEnv)
    if (-not $password) { throw "Environment variable $PasswordEnv is empty." }
    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $r = Invoke-Http POST "$BaseUrl/api/auth/login" @{ email = $EmployeeEmail; password = $password } $session
    $cookie = [string]$r.Headers['Set-Cookie']
    Test-Check 'sign-in; cookie Secure + HttpOnly + SameSite=Strict' ($r.Status -eq 200 -and $cookie -match '(?i)secure' -and
        $cookie -match '(?i)httponly' -and $cookie -match '(?i)samesite=strict') "$($r.Status)"
    if ($r.Status -eq 200) {
        $login = $r.Body | ConvertFrom-Json
        $csrf = @{ 'X-CSRF-Token' = $login.csrf_token }
        $employee = $login.user.employee_id
        Test-Check 'own profile readable' ((Invoke-Http GET "$BaseUrl/api/employees/$employee" $null $session).Status -eq 200)
        Test-Check 'own checklist readable' ((Invoke-Http GET "$BaseUrl/api/employees/$employee/checklist" $null $session).Status -eq 200)
        $other = if ($employee -eq 'EMP002') { 'EMP001' } else { 'EMP002' }
        Test-Check "another employee's data refused (403)" ((Invoke-Http GET "$BaseUrl/api/employees/$other/leave-balances" $null $session).Status -eq 403)
        $t = Get-Date
        $r = Invoke-Http POST "$BaseUrl/api/chat" @{ question = 'Is a cab provided if I stay late at work?' } $session $csrf
        $ms = [int]((Get-Date) - $t).TotalMilliseconds
        $chat = if ($r.Status -eq 200) { $r.Body | ConvertFrom-Json } else { $null }
        Test-Check "grounded GPT-4.1 answer cites handbook.pdf p. 3 ($ms ms, target < 5000)" ($chat -and $chat.found -and
            (@($chat.sources | Where-Object { $_.file -eq 'handbook.pdf' -and $_.page -eq 3 }).Count -ge 1) -and $ms -lt 5000) "$($r.Status) $($r.Body)"
        $r = Invoke-Http POST "$BaseUrl/api/chat" @{ question = 'What is the capital of France?' } $session $csrf
        Test-Check 'out-of-scope question -> safe fallback' ($r.Status -eq 200 -and ($r.Body | ConvertFrom-Json).found -eq $false)
        Test-Check 'history readable' ((Invoke-Http GET "$BaseUrl/api/history" $null $session).Status -eq 200)
        Test-Check 'sign-out' ((Invoke-Http POST "$BaseUrl/api/auth/logout" $null $session $csrf).Status -eq 200)
        Test-Check 'session ended (401 after sign-out)' ((Invoke-Http GET "$BaseUrl/api/auth/me" $null $session).Status -eq 401)
    }
}
$passed = @($results | Where-Object { $_ }).Count
Write-Host "`n-> $passed/$($results.Count) checks passed" -ForegroundColor $(if ($passed -eq $results.Count) { 'Green' } else { 'Red' })
if ($passed -ne $results.Count) { exit 1 }
