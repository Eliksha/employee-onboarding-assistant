# OnboardAI Azure deployment settings. Copy to deploy/azure/config.psd1 (git-ignored) and replace every <...>.
# Proposed values are subject to approval (region, SKU, budget). No secret belongs in this file.
@{
    SubscriptionId = '<subscription-id>'
    ResourceGroup  = '<resource-group>'          # existing sandbox resource group
    Location       = 'southindia'                # proposed; subject to approval and to the sandbox policy
    Prefix         = 'onboardai-eliksha'

    # App Service: one shared Linux plan for both containers (P0v3 proposed; see docs/azure_readiness.md sizing)
    PlanName       = 'onboardai-plan'
    PlanSku        = 'P0V3'
    BackendApp     = 'onboardai-eliksha-backend'
    FrontendApp    = 'onboardai-eliksha-frontend'

    # Azure Container Registry (Basic, admin user disabled; App Service pulls with its managed identity)
    AcrName        = '<acr-name>'                # globally unique, 5-50 lowercase letters/digits, e.g. onboardaieliksha
    ImageTag       = '<git-short-sha>'           # e.g. the commit being deployed (git rev-parse --short HEAD)

    # Azure Database for PostgreSQL - Flexible Server (Burstable B1ms proposed, PostgreSQL 16)
    PgServer       = '<postgres-server-name>'    # globally unique, e.g. onboardai-eliksha-pg
    PgDatabase     = 'onboardai'
    PgAdminUser    = 'onboardai_admin'           # server administrator (not a superuser on Azure)
    PgSkuName      = 'Standard_B1ms'
    PgTier         = 'Burstable'
    PgStorageGb    = 32
    PgVersion      = '16'

    # External secrets file (KEY=VALUE). Needs AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT, AZURE_OPENAI_API_KEY,
    # ONBOARDAI_APP_DB_PASSWORD, ONBOARDAI_READER_DB_PASSWORD, ONBOARDAI_SCOPE_SECRET and, for the Azure server
    # administrator, AZURE_PG_ADMIN_PASSWORD (add it before running 10-Provision-Database.ps1 -Execute).
    SecretsFile    = '<path-to-secrets-file>'   # outside the repository, owner-only ACL

    # Number of proxies appending to X-Forwarded-For in front of the backend (App Service front end of the
    # frontend app, its nginx, App Service front end of the backend). Verify after deployment (README step 7).
    TrustedProxyHops = 3

    Tags = @{ project = 'onboardai'; owner = 'eliksha'; environment = 'capstone' }
}
