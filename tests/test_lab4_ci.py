from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ci_secret_scan_has_an_implementation():
    makefile = (ROOT / "Makefile").read_text()
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "scan-secrets:" in makefile
    assert "python scripts/scan_secrets.py" in makefile
    assert "fetch-depth: 0" in workflow
    assert "make scan-secrets" in workflow


def test_cd_uses_repository_variables_and_deletes_staging_endpoint():
    workflow = (ROOT / ".github/workflows/cd.yml").read_text()
    assert "itcs355-6688176" not in workflow
    assert "PROJECT_ID: ${{ vars.PROJECT_ID }}" in workflow
    assert "gcloud ai endpoints delete" in workflow


def test_dashboard_threshold_matches_drift_job():
    dashboard = (ROOT / "monitoring/dashboard.json").read_text()
    gcp_dashboard = (ROOT / "monitoring/gcp-dashboard.json").read_text()
    drift_workflow = (ROOT / ".github/workflows/drift.yml").read_text()
    assert '"significant": 0.20' in dashboard
    assert '"value": 0.20' in gcp_dashboard
    assert "custom.googleapis.com/itcs355/drift/psi/temp_c" in dashboard
    assert "custom.googleapis.com/itcs355/drift/psi/temp_c" in gcp_dashboard
    assert "--threshold 0.20" in drift_workflow
