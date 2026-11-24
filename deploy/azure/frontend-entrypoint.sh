#!/bin/sh
# Render the nginx server block from App Service settings and start nginx (fails fast on missing settings).
set -eu
for name in BACKEND_ORIGIN BACKEND_HOST BACKEND_PROXY_SECRET; do
    eval "value=\${$name:-}"
    if [ -z "$value" ]; then
        echo "frontend: required setting $name is not set" >&2
        exit 1
    fi
done
if [ "${#BACKEND_PROXY_SECRET}" -lt 32 ]; then
    echo "frontend: BACKEND_PROXY_SECRET must be at least 32 characters" >&2
    exit 1
fi
# Re-resolve the backend through the container's own DNS servers (App Service may change backend IPs).
NGINX_LOCAL_RESOLVERS=$(awk '/^nameserver/ { printf "%s ", ($2 ~ /:/ ? "[" $2 "]" : $2) }' /etc/resolv.conf)
export NGINX_LOCAL_RESOLVERS
envsubst '${BACKEND_ORIGIN} ${BACKEND_HOST} ${BACKEND_PROXY_SECRET} ${NGINX_LOCAL_RESOLVERS}' \
    < /etc/nginx/templates/default.conf.template > /etc/nginx/http.d/default.conf
chmod 600 /etc/nginx/http.d/default.conf
nginx -t -q
exec nginx -g 'daemon off;'
