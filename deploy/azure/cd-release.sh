#!/usr/bin/env bash
# OnboardAI continuous delivery helper - called by .github/workflows/cd.yml (GitHub-hosted Ubuntu runner).
#
# Uses only the Azure management API (ARM) and the registry; never Kudu/SCM, never the database, never app-setting
# values (they are secrets and are neither read nor written). Every command is bounded; nothing secret is printed.
#
# Required environment: AZ_RG (resource group), AZ_SUB (subscription id).
# Subcommands:
#   acr-login <login-server>                  Entra ID token -> ACR refresh token -> docker login (no admin user)
#   image <app>                               print the main sitecontainer image of a Web App
#   host <app>                                print the default host name of a Web App
#   snapshot <app> <file>                     record every security/runtime setting except the image (JSON)
#   compare <before> <after>                  fail if anything except the image changed
#   set-image <app> <image> <port>            point the main sitecontainer at <image> (ARM, managed-identity pull)
#   wait-healthy <frontend-url> <seconds>     bounded wait: /healthz 200 and /api/health database ok, 3x in a row
set -euo pipefail

: "${AZ_RG:?AZ_RG is required}" "${AZ_SUB:?AZ_SUB is required}"
log() { printf '%s %s\n' "$(date -u +%H:%M:%SZ)" "$*"; }
az_() { az "$@" --subscription "$AZ_SUB" --only-show-errors; }

acr_login() {
  local server=$1 tenant aad refresh
  tenant=$(az account show --query tenantId -o tsv)
  aad=$(az account get-access-token --resource https://management.azure.com/ --query accessToken -o tsv)
  echo "::add-mask::$aad"
  refresh=$(curl -fsS --max-time 60 -X POST "https://$server/oauth2/exchange" \
    --data-urlencode grant_type=access_token --data-urlencode "service=$server" \
    --data-urlencode "tenant=$tenant" --data-urlencode "access_token=$aad" | jq -r .refresh_token)
  if [ -z "$refresh" ] || [ "$refresh" = null ]; then log "ACR token exchange failed"; return 1; fi
  echo "::add-mask::$refresh"
  printf '%s' "$refresh" | docker login "$server" -u 00000000-0000-0000-0000-000000000000 --password-stdin >/dev/null
  log "signed in to $server with an Entra ID token (AcrPush; admin user stays disabled)"
}

main_image() { az_ webapp sitecontainers list -g "$AZ_RG" -n "$1" --query "[?isMain].image | [0]" -o tsv; }

snapshot() {
  local app=$1 out=$2
  {
    az_ webapp sitecontainers list -g "$AZ_RG" -n "$app" -o json |
      jq -S '[.[] | del(.id, .image, .createdTime, .lastModifiedTime, .systemData)]'
    az_ webapp show -g "$AZ_RG" -n "$app" -o json |
      jq -S '{publicNetworkAccess, httpsOnly, clientCertEnabled, virtualNetworkSubnetId, keyVaultReferenceIdentity,
              identity: {type: .identity.type, principalId: .identity.principalId}}'
    az_ webapp config show -g "$AZ_RG" -n "$app" -o json |
      jq -S '{minTlsVersion, scmMinTlsVersion, ftpsState, http20Enabled, alwaysOn, vnetRouteAllEnabled, healthCheckPath,
              acrUseManagedIdentityCreds, linuxFxVersion,
              ipSecurityRestrictions: [.ipSecurityRestrictions[]? | {name, action, priority, ipAddress, vnetSubnetResourceId}],
              scmIpSecurityRestrictions: [.scmIpSecurityRestrictions[]? | {name, action, priority, ipAddress}],
              ipSecurityRestrictionsDefaultAction, scmIpSecurityRestrictionsDefaultAction, scmIpSecurityRestrictionsUseMain}'
    for p in scm ftp; do
      az_ resource show -g "$AZ_RG" --namespace Microsoft.Web --resource-type basicPublishingCredentialsPolicies \
        --parent "sites/$app" -n "$p" --query "{basicAuth_$p: properties.allow}" -o json
    done
  } | jq -s -S '.' > "$out"
  log "snapshot of $app: $(jq -r '.[1].publicNetworkAccess // "Enabled(default)"' "$out") public access," \
      "basic auth scm=$(jq -r '.[3].basicAuth_scm' "$out") ftp=$(jq -r '.[4].basicAuth_ftp' "$out")," \
      "https-only=$(jq -r '.[1].httpsOnly' "$out"), sha256 $(sha256sum "$out" | cut -c1-12)"
}

compare() {
  if diff <(jq -S . "$1") <(jq -S . "$2") >/dev/null; then log "configuration unchanged apart from the image: $(basename "$2")"
  else log "CONFIGURATION DRIFT detected ($(basename "$2")):"; diff <(jq -S . "$1") <(jq -S . "$2") | head -40 || true; return 1; fi
}

set_image() {
  local app=$1 image=$2 port=$3
  log "set $app main container -> ${image##*/} (port $port, system-assigned identity pull)"
  az_ webapp sitecontainers update -g "$AZ_RG" -n "$app" --container-name main --image "$image" \
    --target-port "$port" --is-main true --system-assigned-identity true -o none
  [ "$(main_image "$app")" = "$image" ] || { log "image reference not applied on $app"; return 1; }
}

wait_healthy() {
  local url=${1%/} limit=$2 start ok=0 h body code tmp
  start=$(date +%s); tmp=$(mktemp)
  sleep 45   # let the platform start the new container before the first probe
  while [ $(( $(date +%s) - start )) -lt "$limit" ]; do
    h=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$url/healthz" || true)
    code=$(curl -s -o "$tmp" -w '%{http_code}' --max-time 20 "$url/api/health" || true); body=$(head -c 300 "$tmp")
    # Both required: HTTP 200 from /api/health AND a JSON body reporting status ok and database ok.
    if [ "$h" = 200 ] && [ "$code" = 200 ] && printf '%s' "$body" | jq -e '.status == "ok" and .database == "ok"' >/dev/null 2>&1; then
      ok=$((ok + 1)); log "healthy probe $ok/3 (frontend 200, /api/health 200 with status ok + database ok)"
      [ "$ok" -ge 3 ] && { rm -f "$tmp"; return 0; }
    else
      ok=0; log "not healthy yet (frontend $h, /api/health $code: $(printf '%s' "$body" | head -c 80 | tr -d '\n'))"
    fi
    sleep 15
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
