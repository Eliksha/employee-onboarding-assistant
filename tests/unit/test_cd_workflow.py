"""Static security checks of the continuous-delivery workflow (.github/workflows/cd.yml) and its helper.

No network, no Azure: they keep the release controls (manual trigger, main only, CI gate, approval environment,
OIDC without stored credentials, scanning, rollback, no database access) from being weakened unnoticed.
"""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CD = ROOT / ".github" / "workflows" / "cd.yml"
HELPER = ROOT / "deploy" / "azure" / "cd-release.sh"


@pytest.fixture(scope="module")
def wf():
    data = yaml.safe_load(CD.read_text(encoding="utf-8"))
    data["on"] = data.pop(True, data.get("on"))   # YAML 1.1 reads the key `on` as True
    return data


def test_manual_trigger_only(wf):
    assert set(wf["on"]) == {"workflow_dispatch"}
    assert wf["on"]["workflow_dispatch"]["inputs"]["confirm"]["required"] is True


def test_no_concurrent_releases(wf):
    assert wf["concurrency"]["group"] and wf["concurrency"]["cancel-in-progress"] is False


def test_least_privilege_token(wf):
    assert wf["permissions"] == {"contents": "read"}
    jobs = wf["jobs"]
    assert jobs["release"]["permissions"] == {"contents": "read", "id-token": "write"}
    assert "id-token" not in jobs["gate"].get("permissions", {}) and "permissions" not in jobs["build"]


def test_gate_requires_main_and_successful_ci_for_this_commit(wf):
    steps = " ".join(s.get("run", "") for s in wf["jobs"]["gate"]["steps"])
    assert 'refs/heads/main' in steps and '"deploy"' in steps
    assert "workflows/ci.yml/runs?head_sha=$GITHUB_SHA&branch=main" in steps and "status=success" in steps


def test_release_needs_build_and_protected_environment(wf):
    release = wf["jobs"]["release"]
    assert release["needs"] == "build" and wf["jobs"]["build"]["needs"] == "gate"
    assert release["environment"]["name"] == "production"


def test_oidc_login_without_stored_azure_credentials():
    text = CD.read_text(encoding="utf-8")
    assert "azure/login@v2" in text and "client-id: ${{ vars.AZURE_CLIENT_ID }}" in text
    for forbidden in ("client-secret", "creds:", "AZURE_CREDENTIALS", "publish-profile", "registry-password"):
        assert forbidden not in text, forbidden
    secrets = {part.split("}}")[0].strip() for part in text.split("secrets.")[1:]}
    assert secrets == {"VERIFY_EMPLOYEE_PASSWORD"}   # optional, owner-approved signed-in checks only


def test_images_validated_and_scanned_before_publishing(wf):
    build = " ".join(s.get("run", "") for s in wf["jobs"]["build"]["steps"])
    assert "python -m backend.services.ingest" in build and "python -m scripts.rag_eval --no-llm" in build
    assert "deploy/azure/backend.Dockerfile" in build and "deploy/azure/frontend.Dockerfile" in build
    # Separate scans: fixable HIGH/CRITICAL vulnerabilities; secrets of EVERY severity (no --ignore-unfixed there).
    assert "--scanners vuln --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1" in build
    assert "--scanners secret --severity UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL --exit-code 1" in build
    assert "@sha256:" in wf["env"]["TRIVY_IMAGE"]
    # Smoke checks may not swallow execution failures.
    assert "|| true" not in build and "SCAN_COMPLETE" in build
    release = " ".join(s.get("run", "") for s in wf["jobs"]["release"]["steps"])
    assert "needs.build.outputs.backend_id" in release and "already exists; tags are immutable" in release


def test_tags_include_run_attempt(wf):
    build = " ".join(s.get("run", "") for s in wf["jobs"]["build"]["steps"])
    release = " ".join(s.get("run", "") for s in wf["jobs"]["release"]["steps"])
    attempt_tag = "${GITHUB_SHA::12}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
    assert attempt_tag in build and attempt_tag in release   # the registry tag is computed in the release attempt


def test_health_requires_http_200_and_healthy_json():
    text = HELPER.read_text(encoding="utf-8")
    assert '[ "$code" = 200 ]' in text and '.status == "ok" and .database == "ok"' in text


def test_rollback_on_failure_and_public_verification(wf):
    steps = wf["jobs"]["release"]["steps"]
    rollback = next(s for s in steps if s.get("id") == "rollback")
    # Only after a production image update was attempted (including a failed/partial backend update).
    assert rollback["if"].startswith("failure()")
    assert "steps.deploy_backend.outcome == 'success'" in rollback["if"]
    assert "steps.deploy_backend.outcome == 'failure'" in rollback["if"]
    run = rollback["run"]
    assert "PREV_BE" in run and "PREV_FE" in run and "70-Verify-Deployment.ps1" in run
    # Verified after rollback: image references, configuration snapshot, health.
    assert "previous image references restored" in run and ".rollback.json" in run and "wait-healthy" in run
    assert any("70-Verify-Deployment.ps1" in s.get("run", "") for s in steps if s.get("id") != "rollback")


def _code(path):
    """Executable content only (comments may legitimately name what CD must NOT do)."""
    return "\n".join(line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#"))


def test_no_database_or_migration_access_in_cd():
    text = _code(CD) + _code(HELPER)
    for forbidden in ("Migrate-Database", "psql", "pg_restore", "postgres flexible-server", "firewall-rule"):
        assert forbidden not in text, forbidden


def test_helper_never_touches_secrets_or_weakens_access():
    text = HELPER.read_text(encoding="utf-8")
    for forbidden in ("appsettings", "properties.allow=true", "publicNetworkAccess=Enabled", "create-remote-connection",
                      "scm-site", "access-restriction add", "--admin-enabled"):
        assert forbidden not in text, forbidden
    assert "set -euo pipefail" in text and "::add-mask::" in text
