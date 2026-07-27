from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"


def test_release_workflow_signs_package_with_pinned_private_publisher():
    source = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "WFX_SIGNING_CERTIFICATE_BASE64" in source
    assert "WFX_SIGNING_CERTIFICATE_PASSWORD" in source
    assert "shell: pwsh" in source
    assert "signtool" not in source
    assert "Import-Certificate" not in source
    assert '$zipName = "WFX-Smart-v$version-win64.zip"' in source
    assert "tar.exe -a -c -f" in source
    assert '$archiveEntries -notcontains "./WFX-Panel.exe"' in source
    assert "$verifyCms.CheckSignature($true)" in source
    assert "$actualCmsSigner -ne $expectedCmsSigner" in source
    assert 'Remove-Item `' in source


def test_release_workflow_keeps_size_and_dependency_regression_guards():
    source = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "$buildSizeMb -gt 180" in source
    for unused in ("PyQt5", "PyQt6", "numpy", "cryptography"):
        assert f'"{unused}"' in source
