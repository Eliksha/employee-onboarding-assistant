#!/bin/sh
# Migration image entrypoint: key-only sshd on 2222 (root) + maintenance responder on 8000 (appuser).
set -eu
key="${MIGRATION_SSH_AUTHORIZED_KEY:-}"
case "$key" in
    ssh-ed25519\ *) ;;
    *) echo "migration: MIGRATION_SSH_AUTHORIZED_KEY must be one ssh-ed25519 public key" >&2; exit 1 ;;
esac
if [ "$(printf '%s\n' "$key" | wc -l)" -ne 1 ]; then
    echo "migration: exactly one public key is allowed" >&2; exit 1
fi
# Fresh host key per container start (fingerprint printed for the operator to compare on first connect).
rm -f /etc/ssh/ssh_host_*
ssh-keygen -q -t ed25519 -N '' -f /etc/ssh/ssh_host_ed25519_key
echo "migration: SSH host key $(ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub | awk '{print $2}')"
umask 077
printf '%s\n' "$key" > /home/appuser/.ssh/authorized_keys
chown -R appuser:appuser /home/appuser/.ssh
# Non-secret connection settings for the migration session (SSH sessions do not inherit the container environment).
{
    for name in PG_HOST PG_PORT PG_DATABASE PG_SSLMODE PG_SSLROOTCERT PG_USER PG_READER_USER DB_BACKEND APP_ENV HF_HUB_OFFLINE FASTEMBED_CACHE_PATH; do
        eval "value=\${$name:-}"
        [ -n "$value" ] && printf '%s=%s\n' "$name" "$value"
    done
} > /run/onboardai-migration.env
chown appuser:appuser /run/onboardai-migration.env
chmod 600 /run/onboardai-migration.env
mkdir -p /tmp/onboardai-migration && chown appuser:appuser /tmp/onboardai-migration && chmod 700 /tmp/onboardai-migration
/usr/sbin/sshd -t
/usr/sbin/sshd -e
exec setpriv --reuid=10001 --regid=10001 --init-groups python /usr/local/lib/onboardai/maintenance_server.py
