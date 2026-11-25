# OnboardAI frontend - production image for Azure App Service (Linux, custom container).
#
# Build from the repository root (BuildKit uses deploy/azure/frontend.Dockerfile.dockerignore):
#   docker build -f deploy/azure/frontend.Dockerfile -t onboardai-frontend:<tag> .
#
# nginx serves the SPA and proxies /api/* to the backend Web App over HTTPS (same-origin for the browser, so no
# CORS and the session cookie stays first-party). Runtime settings (App Service application settings), rendered
# into the config at container start - never baked into the image:
#   BACKEND_ORIGIN        https://<backend>.azurewebsites.net   (no trailing slash)
#   BACKEND_HOST          <backend>.azurewebsites.net           (Host/SNI for App Service routing)
#   BACKEND_PROXY_SECRET  same value as the backend's BACKEND_PROXY_SECRET (>= 32 characters)
# Base: Alpine's own nginx package (security fixes are backported there; the official nginx:1.28-alpine and
# 1.29-alpine images still carried fixable CRITICAL/HIGH nginx findings in the Trivy scan of 24 Nov 2026).
FROM node:24-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM alpine:3.23
RUN apk upgrade --no-cache \
    && apk add --no-cache nginx gettext-envsubst ca-certificates \
    && mkdir -p /run/nginx /etc/nginx/templates /etc/nginx/http.d \
    && rm -f /etc/nginx/http.d/default.conf
COPY deploy/azure/nginx-main.conf /etc/nginx/nginx.conf
COPY deploy/azure/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --chmod=0755 deploy/azure/frontend-entrypoint.sh /usr/local/bin/frontend-entrypoint.sh
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD wget -qO /dev/null http://127.0.0.1/healthz || exit 1
ENTRYPOINT ["/usr/local/bin/frontend-entrypoint.sh"]
