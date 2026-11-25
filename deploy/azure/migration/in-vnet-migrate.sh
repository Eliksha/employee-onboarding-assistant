#!/bin/bash
# Runs INSIDE the temporary migration container (as appuser, over the SSH tunnel), i.e. inside the Azure VNet.
#
#   onboardai-in-vnet-migrate migrate             < secrets on stdin   restore + verify + roles/RLS/008 (+ auto-rollback)
#   onboardai-in-vnet-migrate rollback --confirm  < secrets on stdin   return the target to an EMPTY database
#   onboardai-in-vnet-migrate cleanup                                   shred the uploaded files
#
# Uploaded by the operator to /tmp/onboardai-migration (mode 700): onboardai.dump, restore.list, fingerprint.sql,
# source_fingerprint.txt. Secrets are read from stdin as KEY=VALUE lines (PG_ADMIN_USER, PG_ADMIN_PASSWORD,
# ONBOARDAI_APP_DB_PASSWORD, ONBOARDAI_READER_DB_PASSWORD, ONBOARDAI_SCOPE_SECRET); they live only in this process.
# Every connection uses TLS with certificate and host-name verification (sslmode=verify-full).
set -euo pipefail
umask 077
WORK=/tmp/onboardai-migration
cd /app

log() { printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
die() { log "FAILED: $*"; exit 1; }

load_config() {
    [ -r /run/onboardai-migration.env ] || die "missing /run/onboardai-migration.env (container not started by the migration entrypoint)"
    set -a; . /run/onboardai-migration.env; set +a
    export DB_BACKEND=postgresql PG_SSLMODE=verify-full PG_SSLROOTCERT="${PG_SSLROOTCERT:-/etc/ssl/certs/ca-certificates.crt}"
    [ -n "${PG_HOST:-}" ] || die "PG_HOST is not configured on the Web App"
    PG_PORT="${PG_PORT:-5432}"; PG_DATABASE="${PG_DATABASE:-onboardai}"
}

read_secrets() {
    local line key value
    # Split at the FIRST '=' only: values may contain or end with '=' (IFS-based read would strip a trailing '=').
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line#$'\xef\xbb\xbf'}"; line="${line%$'\r'}"              # BOM / CRLF from Windows senders
        [ -z "$line" ] && continue
        [[ "$line" == *=* ]] || die "malformed input line (expected KEY=VALUE)"
        key="${line%%=*}"; value="${line#*=}"
        case "$key" in
            PG_ADMIN_USER|PG_ADMIN_PASSWORD|ONBOARDAI_APP_DB_PASSWORD|ONBOARDAI_READER_DB_PASSWORD|ONBOARDAI_SCOPE_SECRET)
                export "$key=$value" ;;
            "") ;;
            *) die "unexpected input key ${key}" ;;
        esac
    done
    for key in PG_ADMIN_USER PG_ADMIN_PASSWORD ONBOARDAI_APP_DB_PASSWORD ONBOARDAI_READER_DB_PASSWORD ONBOARDAI_SCOPE_SECRET; do
        [ -n "${!key:-}" ] || die "secret ${key} was not provided on stdin"
    done
    export PGPASSWORD="$PG_ADMIN_PASSWORD"
}

dsn() { echo "host=${PG_HOST} port=${PG_PORT} dbname=${1:-$PG_DATABASE} user=${PG_ADMIN_USER} sslmode=verify-full sslrootcert=${PG_SSLROOTCERT}"; }
admin_sql() { psql "$(dsn "${2:-}")" -v ON_ERROR_STOP=1 -At -c "$1"; }

migration() {   # python migration as the administrator
    PG_ADMIN_USER="$PG_ADMIN_USER" PG_USER="$PG_ADMIN_USER" python "backend/migrations/$1" "${@:2}"
}

shred_files() {
    for f in "$WORK"/*; do [ -f "$f" ] && shred -u "$f" 2>/dev/null || rm -f "$f"; done
    log "uploaded migration files removed from the container"
}

rollback() {
    log "ROLLBACK: recreating an EMPTY database ${PG_DATABASE} and removing the application roles"
    admin_sql "DROP DATABASE IF EXISTS \"${PG_DATABASE}\" WITH (FORCE)" postgres
    admin_sql "CREATE DATABASE \"${PG_DATABASE}\"" postgres
    admin_sql "DROP ROLE IF EXISTS onboardai_app" postgres || true
    admin_sql "DROP ROLE IF EXISTS onboardai_reader" postgres || true
    log "ROLLBACK complete: target is empty again (source database and local backup are unchanged)"
}

do_migrate() {
    for f in onboardai.dump restore.list fingerprint.sql source_fingerprint.txt; do
        [ -s "$WORK/$f" ] || die "missing upload $WORK/$f"
    done
    log "target: ${PG_HOST}:${PG_PORT}/${PG_DATABASE} as ${PG_ADMIN_USER} (TLS verify-full)"
    psql "$(dsn)" -At -c "SELECT 'TLS ' || version FROM pg_stat_ssl WHERE pid = pg_backend_pid()" || die "cannot connect over verified TLS"
    tables=$(admin_sql "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
    [ "$tables" = "0" ] || die "target database already has ${tables} table(s); refusing to overwrite existing data (use rollback first if this is a failed earlier attempt)"

    trap 'log "error - rolling back"; rollback; shred_files' ERR
    log "[1/5] restore (one transaction, owners and grants re-created by migration 005)"
    # pg_restore (client 17) renders the SQL; the one PostgreSQL-17-only setting it emits (transaction_timeout) is
    # removed for the 16 server; psql applies everything in ONE transaction and stops at the first error.
    pg_restore --no-owner --no-privileges -L "$WORK/restore.list" -f - "$WORK/onboardai.dump" \
        | grep -v -x 'SET transaction_timeout = 0;' \
        | psql "$(dsn)" -v ON_ERROR_STOP=1 --single-transaction -q -o /dev/null
    log "[2/5] data fingerprints"
    psql "$(dsn)" -v ON_ERROR_STOP=1 -At -F '|' -f "$WORK/fingerprint.sql" > "$WORK/target_fingerprint.txt"
    if ! diff -q "$WORK/source_fingerprint.txt" "$WORK/target_fingerprint.txt" >/dev/null; then
        diff "$WORK/source_fingerprint.txt" "$WORK/target_fingerprint.txt" | sed 's/|[0-9a-f]\{32\}$/|<md5>/' || true
        false   # -> ERR trap -> rollback
    fi
    awk -F'|' '{ printf "      %-22s rows %5s  identical\n", $1, $2 }' "$WORK/target_fingerprint.txt"
    log "[3/5] migration 008 (HR/IT queue, shared rate limit), then 005 (roles, grants, RLS, signed scope; key kept)"
    migration 008_hr_escalation_queue.py --apply
    migration 005_least_privilege_roles.py --apply | tail -3
    log "[4/5] verification 007 / 008 / 005"
    migration 007_data_integrity.py --verify > /dev/null
    migration 008_hr_escalation_queue.py --verify > /dev/null
    migration 005_least_privilege_roles.py --verify | grep -E '"key_matches_secret": true' > /dev/null
    migration 005_least_privilege_roles.py --verify | grep -E '"problems": \[\]' > /dev/null
    log "[5/5] application role: startup checks over verified TLS"
    PG_USER=onboardai_app PG_PASSWORD="$ONBOARDAI_APP_DB_PASSWORD" PG_READER_USER=onboardai_reader \
        PG_READER_PASSWORD="$ONBOARDAI_READER_DB_PASSWORD" PG_SCOPE_SECRET="$ONBOARDAI_SCOPE_SECRET" \
        python -c "from backend.services import db; db.init_db(); print('      startup checks passed')"
    trap - ERR
    shred_files
    log "MIGRATION SUCCEEDED"
}

load_config
case "${1:-}" in
    migrate) read_secrets; do_migrate ;;
    rollback) [ "${2:-}" = "--confirm" ] || die "rollback empties the target database: pass --confirm"; read_secrets; rollback; shred_files ;;
    cleanup) shred_files ;;
    *) echo "usage: onboardai-in-vnet-migrate migrate|rollback --confirm|cleanup (secrets on stdin)" >&2; exit 2 ;;
esac
