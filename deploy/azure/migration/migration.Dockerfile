# OnboardAI TEMPORARY migration image - used only while the database is migrated through the App Service SSH tunnel.
#
#   docker build -f deploy/azure/migration/migration.Dockerfile --build-arg BASE_IMAGE=<backend image> -t <backend image>-migrate .
#
# = the production backend image + OpenSSH server + PostgreSQL client tools + the in-VNet migration script.
# Security model (see deploy/azure/README.md, "Private database migration"):
#   * SSH is KEY-ONLY with a one-time ed25519 key: the public key comes from the app setting MIGRATION_SSH_AUTHORIZED_KEY,
#     the private key never leaves the operator's machine. No passwords, no root login, only `appuser` may log in,
#     no forwarding of any kind. sshd listens on 2222, which App Service exposes ONLY through the authenticated SCM tunnel
#     (az webapp create-remote-connection); it is never a public port.
#   * The application does NOT start in this image (maintenance 503 on port 8000), so nothing uses a half-migrated database.
#   * No secret is baked in or stored: the database administrator password and role secrets are sent on stdin over SSH.
#   * After the migration the Web App is switched back to the production image, which contains no SSH server at all.
ARG BASE_IMAGE=onboardai-backend:azure-local
FROM ${BASE_IMAGE}

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-server postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/ssh/ssh_host_* \
    && mkdir -p /run/sshd /home/appuser/.ssh \
    && install -d -m 0755 /usr/local/lib/onboardai \
    && chown appuser:appuser /home/appuser/.ssh && chmod 700 /home/appuser/.ssh \
    && usermod -p '*' appuser
COPY deploy/azure/migration/sshd_config /etc/ssh/sshd_config
COPY --chmod=0755 deploy/azure/migration/migration-entrypoint.sh /usr/local/bin/migration-entrypoint.sh
COPY --chmod=0755 deploy/azure/migration/in-vnet-migrate.sh /usr/local/bin/onboardai-in-vnet-migrate
COPY --chmod=0644 deploy/azure/migration/maintenance_server.py /usr/local/lib/onboardai/maintenance_server.py

EXPOSE 8000 2222
HEALTHCHECK NONE
ENTRYPOINT ["/usr/local/bin/migration-entrypoint.sh"]
