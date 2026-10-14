"""Verify a release excludes personal files and known locally saved secrets.

Run under the Windows account owning the vault. Output contains only relative
filenames/counts, never the secret values being searched for.
"""

import json
from zipfile import ZipFile
from jobpilot.config import BASE_DIR, DATA_DIR
from jobpilot.vault import Vault


def audit():
    values = Vault(DATA_DIR / "credentials.dpapi").read().values()
    secrets = [value.encode() for value in values if len(value) >= 6]
    archive_path = BASE_DIR / "dist/jobpraapti-source.zip"
    findings = []
    with ZipFile(archive_path) as archive:
        names = archive.namelist()
        for name in names:
            normalized = "/" + name.replace("\\", "/")
            forbidden = any(
                part in normalized
                for part in ("/data/", "/node_modules/", "/.venv/", "/scratch/")
            ) or normalized.endswith(
                ("/.env", "/config/profile.yaml", ".dpapi", ".pdf")
            )
            if forbidden or any(value in archive.read(name) for value in secrets):
                findings.append(name)
    print(
        json.dumps(
            {
                "archive_files": len(names),
                "known_secrets_checked": len(secrets),
                "findings": findings,
            }
        )
    )
    if findings:
        raise SystemExit(1)


if __name__ == "__main__":
    audit()
