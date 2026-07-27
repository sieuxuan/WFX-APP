from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"


def test_release_workflow_signs_and_temporarily_trusts_private_publisher():
    source = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "WFX_SIGNING_CERTIFICATE_BASE64" in source
    assert "WFX_SIGNING_CERTIFICATE_PASSWORD" in source
    assert "signtool sign /fd SHA256 /td SHA256" in source
    assert 'Cert:\\CurrentUser\\Root' in source
    assert "signtool verify /pa /all" in source
    assert '$zipName = "WFX-Smart-v$version-win64.zip"' in source
    assert "TimeStamperCertificate" in source
    assert "$verifyCms.CheckSignature($false)" in source
    assert 'Remove-Item `' in source
    assert '"Cert:\\CurrentUser\\Root\\$thumbprint"' in source


def test_release_workflow_keeps_size_and_dependency_regression_guards():
    source = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "$buildSizeMb -gt 180" in source
    for unused in ("PyQt5", "PyQt6", "numpy", "cryptography"):
        assert f'"{unused}"' in source
