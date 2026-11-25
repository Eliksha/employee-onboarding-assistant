#!/usr/bin/env bash
# OnboardAI continuous delivery helper - called by .github/workflows/cd.yml (GitHub-hosted Ubuntu runner).
#
# Uses only the Azure management API (ARM) and the registry; never Kudu/SCM, never the database, never app-setting
# values (they are secrets and are neither read nor written). Every command is bounded; nothing secret is printed.
# JSON is processed with Python 3 (preinstalled on the runner; PY overrides the interpreter), so every subcommand can
# be exercised locally against the real resources with read-only credentials.
#
# Required environment: AZ_RG (resource group), AZ_SUB (subscription id).
# Subcommands:
#   acr-login <login-server>                  Entra ID token -> ACR refresh token -> docker login (no admin user)
#   image <app>                               print the main sitecontainer image of a Web App
#   host <app>                                print the default host name of a Web App
#   snapshot <app> <file>                     record every security/runtime setting except the image (JSON)
#   compare <before> <after>                  fail if anything except the image changed
#   set-image <app> <image> <port>            point the main sitecontainer at <image> (ARM, managed-identity pull)
#   wait-healthy <frontend-url> <seconds>     bounded wait: /healthz 200 and /api/health 200 + healthy JSON, 3x in a row
set -euo pipefail

: "${AZ_RG:?AZ_RG is required}" "${AZ_SUB:?AZ_SUB is required}"
PY=${PY:-python3}
log() { printf '%s %s\n' "$(date -u +%H:%M:%SZ)" "$*"; }
# GitHub Actions hides the value of a ::add-mask:: line; anywhere else the line would print the secret itself.
mask() { if [ "${GITHUB_ACTIONS:-}" = true ]; then echo "::add-mask::$1"; fi; }
az_() { az "$@" --subscription "$AZ_SUB" --only-show-errors; }

acr_login() {
  local server=$1 tenant aad refresh
  tenant=$(az account show --query tenantId -o tsv)
  aad=$(az account get-access-token --resource https://management.azure.com/ --query accessToken -o tsv)
  mask "$aad"
  refresh=$(curl -fsS --max-time 60 -X POST "https://$server/oauth2/exchange" \
    --data-urlencode grant_type=access_token --data-urlencode "service=$server" \
    --data-urlencode "tenant=$tenant" --data-urlencode "access_token=$aad" |
    "$PY" -c 'import json, sys; print(json.load(sys.stdin).get("refresh_token", ""))')
  if [ -z "$refresh" ]; then log "ACR token exchange failed"; return 1; fi
  mask "$refresh"
  printf '%s' "$refresh" | docker login "$server" -u 00000000-0000-0000-0000-000000000000 --password-stdin >/dev/null
  log "signed in to the registry with an Entra ID token (AcrPush; admin user stays disabled)"
}

main_image() { az_ webapp sitecontainers list -g "$AZ_RG" -n "$1" --query "[?isMain].image | [0]" -o tsv; }

snapshot() {
  local app=$1 out=$2 dir
  dir=$(mktemp -d)
  az_ webapp sitecontainers list -g "$AZ_RG" -n "$app" -o json > "$dir/sc.json"
  az_ webapp show -g "$AZ_RG" -n "$app" -o json > "$dir/site.json"
  az_ webapp config show -g "$AZ_RG" -n "$app" -o json > "$dir/cfg.json"
  for p in scm ftp; do
    az_ resource show -g "$AZ_RG" --namespace Microsoft.Web --resource-type basicPublishingCredentialsPolicies \
      --parent "sites/$app" -n "$p" --query properties.allow -o tsv > "$dir/$p.txt"
  done
  "$PY" - "$dir" "$out" <<'PY'
import json, pathlib, sys
d, out = pathlib.Path(sys.argv[1]), sys.argv[2]
load = lambda n: json.loads((d / n).read_text(encoding="utf-8"))
sc, site, cfg = load("sc.json"), load("site.json"), load("cfg.json")
pick = lambda obj, keys: {k: (obj or {}).get(k) for k in keys}
snap = {
    "sitecontainers": sorted(({k: v for k, v in c.items() if k not in ("id", "image", "createdTime", "lastModifiedTime", "systemData")}
                              for c in sc), key=lambda c: str(c.get("name"))),
    "site": {**pick(site, ["publicNetworkAccess", "httpsOnly", "clientCertEnabled", "virtualNetworkSubnetId", "keyVaultReferenceIdentity"]),
             "identity": pick(site.get("identity"), ["type", "principalId"])},
    "config": {**pick(cfg, ["minTlsVersion", "scmMinTlsVersion", "ftpsState", "http20Enabled", "alwaysOn", "vnetRouteAllEnabled",
                            "healthCheckPath", "acrUseManagedIdentityCreds", "linuxFxVersion", "ipSecurityRestrictionsDefaultAction",
                            "scmIpSecurityRestrictionsDefaultAction", "scmIpSecurityRestrictionsUseMain"]),
               "ipSecurityRestrictions": [pick(r, ["name", "action", "priority", "ipAddress", "vnetSubnetResourceId"]) for r in cfg.get("ipSecurityRestrictions") or []],
               "scmIpSecurityRestrictions": [pick(r, ["name", "action", "priority", "ipAddress"]) for r in cfg.get("scmIpSecurityRestrictions") or []]},
    "basicAuth": {p: (d / f"{p}.txt").read_text().strip() for p in ("scm", "ftp")},
}
if not snap["sitecontainers"] or not snap["config"]["minTlsVersion"]:
    sys.exit("snapshot incomplete: sitecontainers or site configuration missing")
pathlib.Path(out).write_text(json.dumps(snap, indent=1, sort_keys=True), encoding="utf-8")
s, b = snap["site"], snap["basicAuth"]
print(f"snapshot: public access {s['publicNetworkAccess'] or 'Enabled(default)'}, https-only {s['httpsOnly']}, "
      f"basic auth scm={b['scm']} ftp={b['ftp']}, {len(snap['sitecontainers'])} sitecontainer(s)")
PY
  rm -rf "$dir"
}

compare() {
  "$PY" - "$1" "$2" <<'PY'
import json, sys
a, b = (json.load(open(p, encoding="utf-8")) for p in sys.argv[1:3])
if a == b:
    print(f"configuration unchanged apart from the image ({sys.argv[2].replace(chr(92), '/').rsplit('/', 1)[-1]})")
    sys.exit(0)
def diff(x, y, path=""):
    if isinstance(x, dict) and isinstance(y, dict):
        for k in sorted(set(x) | set(y)):
            yield from diff(x.get(k), y.get(k), f"{path}.{k}")
    elif x != y:
        yield f"{path or '.'}: {json.dumps(x)[:120]} -> {json.dumps(y)[:120]}"
print("CONFIGURATION DRIFT detected:")
for line in list(diff(a, b))[:40]:
    print("  " + line)
sys.exit(1)
PY
}

set_image() {
  local app=$1 image=$2 port=$3
  log "set $app main container -> ${image##*/} (port $port, system-assigned identity pull)"
  az_ webapp sitecontainers update -g "$AZ_RG" -n "$app" --container-name main --image "$image" \
    --target-port "$port" --is-main true --system-assigned-identity true -o none
  [ "$(main_image "$app")" = "$image" ] || { log "image reference not applied on $app"; return 1; }
}

healthy_json() {   # stdin: /api/health body -> exit 0 only for {"status": "ok", "database": "ok"}
  "$PY" -c 'import json, sys
try:
    d = json.load(sys.stdin)
except ValueError:
    sys.exit(1)
sys.exit(0 if isinstance(d, dict) and d.get("status") == "ok" and d.get("database") == "ok" else 1)'
}

wait_healthy() {
  local url=${1%/} limit=$2 start ok=0 h body code tmp
  start=$(date +%s); tmp=$(mktemp)
  sleep "${HEALTH_INITIAL_WAIT:-45}"   # let the platform start the new container before the first probe
  while [ $(( $(date +%s) - start )) -lt "$limit" ]; do
    h=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$url/healthz" || true)
    code=$(curl -s -o "$tmp" -w '%{http_code}' --max-time 20 "$url/api/health" || true); body=$(head -c 300 "$tmp")
    # Both required: HTTP 200 from /api/health AND a JSON body reporting status ok and database ok.
    if [ "$h" = 200 ] && [ "$code" = 200 ] && printf '%s' "$body" | healthy_json; then
      ok=$((ok + 1)); log "healthy probe $ok/3 (frontend 200, /api/health 200 with status ok + database ok)"
      [ "$ok" -ge 3 ] && { rm -f "$tmp"; return 0; }
    else
      ok=0; log "not healthy yet (frontend $h, /api/health $code: $(printf '%s' "$body" | head -c 80 | tr -d '\n'))"
    fi
    sleep "${HEALTH_INTERVAL:-15}"
  done
  rm -f "$tmp"; log "NOT HEALTHY within ${limit}s"; return 1
}

cmd=${1:-}; shift || true
case "$cmd" in
  acr-login) acr_login "$@" ;;
  image) main_image "$@" ;;
  host) az_ webapp show -g "$AZ_RG" -n "$1" --query defaultHostName -o tsv ;;
  snapshot) snapshot "$@" ;;
  compare) compare "$@" ;;
  set-image) set_image "$@" ;;
  wait-healthy) wait_healthy "$@" ;;
  *) echo "usage: $0 {acr-login|image|host|snapshot|compare|set-image|wait-healthy} ..." >&2; exit 2 ;;
esac
