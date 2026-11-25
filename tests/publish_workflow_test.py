#!/usr/bin/env python3
"""Regression checks for immutable Hadal package releases."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import zipfile
from urllib.error import HTTPError
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PUBLISH = (ROOT / ".github" / "workflows" / "publish.yml").read_text()
CHECK = (ROOT / ".github" / "workflows" / "check.yml").read_text()
MANIFEST = json.loads((ROOT / "package.json").read_text())
KIND = "vscode" if MANIFEST["name"] == "hadal-theme" else "inkdrop"
SECRET_NAMES = {"INKDROP_ACCESS_KEY_ID", "INKDROP_SECRET_ACCESS_KEY"}

SPEC = importlib.util.spec_from_file_location("release", ROOT / "scripts" / "release.py")
assert SPEC and SPEC.loader
RELEASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RELEASE)


def jobs(workflow: str) -> dict[str, str]:
    result = {}
    current = None
    in_jobs = False

    for line in workflow.splitlines(keepends=True):
        if line.rstrip() == "jobs:":
            in_jobs = True
            continue
        if not in_jobs:
            continue
        if not line.strip():
            if current is not None:
                result[current] += line
            continue
        if line and not line.startswith(" "):
            break
        match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if match:
            current = match.group(1)
            result[current] = line
        elif current is not None:
            result[current] += line

    return result


def test_metadata_validation() -> None:
    with tempfile.TemporaryDirectory(prefix="hadal-release-metadata-") as temp:
        root = Path(temp)
        root.joinpath("package.json").write_text(
            json.dumps(
                {
                    "name": MANIFEST["name"],
                    "version": "1.2.3",
                    **({"publisher": MANIFEST["publisher"]} if KIND == "vscode" else {}),
                }
            )
        )
        root.joinpath("CHANGELOG.md").write_text("# Changelog\n\n## 1.2.3\n")

        metadata = RELEASE.read_metadata(root, KIND, "v1.2.3")
        assert metadata["package"] == MANIFEST["name"]
        assert metadata["version"] == "1.2.3"
        assert metadata["artifact"].endswith(
            f"-1.2.3.{'vsix' if KIND == 'vscode' else 'tgz'}"
        )
        if KIND == "vscode":
            assert metadata["identifier"] == "tcagriz.hadal-theme"

        for invalid in ("1.2.3", "v1.2", "v01.2.3", "v1.2.3-rc1"):
            try:
                RELEASE.read_metadata(root, KIND, invalid)
            except RELEASE.ReleaseError:
                pass
            else:
                raise AssertionError(f"accepted invalid tag: {invalid}")

        root.joinpath("package.json").write_text(
            json.dumps(
                {
                    "name": MANIFEST["name"],
                    "version": "2.0.0",
                    **({"publisher": MANIFEST["publisher"]} if KIND == "vscode" else {}),
                }
            )
        )
        try:
            RELEASE.read_metadata(root, KIND, "v1.2.3")
        except RELEASE.ReleaseError:
            pass
        else:
            raise AssertionError("accepted manifest/tag mismatch")

        root.joinpath("package.json").write_text(
            json.dumps(
                {
                    "name": MANIFEST["name"],
                    "version": "1.2.3",
                    **({"publisher": MANIFEST["publisher"]} if KIND == "vscode" else {}),
                }
            )
        )
        root.joinpath("CHANGELOG.md").write_text("# Changelog\n\n## 1.2.2\n")
        try:
            RELEASE.read_metadata(root, KIND, "v1.2.3")
        except RELEASE.ReleaseError:
            pass
        else:
            raise AssertionError("accepted missing changelog entry")

        if KIND == "vscode":
            root.joinpath("package.json").write_text(
                json.dumps({"name": MANIFEST["name"], "version": "1.2.3"})
            )
            root.joinpath("CHANGELOG.md").write_text("# Changelog\n\n## 1.2.3\n")
            try:
                RELEASE.read_metadata(root, KIND, "v1.2.3")
            except RELEASE.ReleaseError:
                pass
            else:
                raise AssertionError("accepted missing VS Code publisher")


def test_archive_manifest() -> None:
    with tempfile.TemporaryDirectory(prefix="hadal-release-archive-") as temp:
        root = Path(temp)
        first = root / "first.tgz"
        second = root / "second.tgz"
        for archive, prefix in ((first, "package/"), (second, "./")):
            with tarfile.open(archive, "w:gz") as package:
                for name, content in {
                    "package.json": b'{"name":"hadal"}',
                    "styles/ui.css": b"body {}",
                }.items():
                    data = content
                    entry = tarfile.TarInfo(f"{prefix}{name}")
                    entry.size = len(data)
                    package.addfile(entry, io.BytesIO(data))

        assert RELEASE.normalize_archive_members(first) == (
            RELEASE.normalize_archive_members(second)
        )

        zipped = root / "extension.vsix"
        with zipfile.ZipFile(zipped, "w") as package:
            package.writestr("extension/package.json", '{"name":"hadal"}')
            package.writestr("extension/themes/hadal.json", "{}")
        assert len(RELEASE.artifact_manifest(zipped)) == 2


def completed(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_release_asset_idempotence() -> None:
    with tempfile.TemporaryDirectory(prefix="hadal-release-idempotence-") as temp:
        root = Path(temp)
        artifact = root / "hadal-1.2.3.tgz"
        existing = root / "existing.tgz"
        data = b'{"name":"hadal","version":"1.2.3"}'
        for path, mtime in ((artifact, 1), (existing, 2)):
            with tarfile.open(path, "w:gz") as package:
                entry = tarfile.TarInfo("package/package.json")
                entry.size = len(data)
                entry.mtime = mtime
                package.addfile(entry, io.BytesIO(data))
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        existing_digest = hashlib.sha256(existing.read_bytes()).hexdigest()
        assert digest != existing_digest
        release = {"draft": False, "assets": [{"name": artifact.name}]}
        calls = []

        def fake_run(command: list[str], **kwargs):
            calls.append(command)
            if command[:3] == ["gh", "api", "--hostname"]:
                return completed(stdout=json.dumps(release))
            if command[:3] == ["gh", "release", "download"]:
                destination = Path(command[command.index("--dir") + 1]) / artifact.name
                destination.write_bytes(existing.read_bytes())
                return completed()
            if command[:3] == ["gh", "release", "create"]:
                raise AssertionError("idempotent rerun attempted to recreate release")
            raise AssertionError(f"unexpected command: {command}")

        with mock.patch.object(RELEASE, "run", side_effect=fake_run):
            resolved = RELEASE.ensure_release(
                "tcagriz/hadal-inkdrop",
                "v1.2.3",
                "Hadal 1.2.3",
                artifact,
                digest,
            )
        assert resolved == existing_digest
        assert not any(command[2] == "create" for command in calls if len(command) > 2)


def test_inkdrop_registry_status() -> None:
    with tempfile.TemporaryDirectory(prefix="hadal-registry-status-") as temp:
        root = Path(temp)
        artifact = root / "hadal-1.2.3.tgz"
        with tarfile.open(artifact, "w:gz") as package:
            data = b'{"name":"hadal","version":"1.2.3"}'
            entry = tarfile.TarInfo("package/package.json")
            entry.size = len(data)
            package.addfile(entry, io.BytesIO(data))

        archive_bytes = artifact.read_bytes()
        responses = [
            io.BytesIO(
                json.dumps(
                    {
                        "dist": {
                            "tarball": "https://api.inkdrop.invalid/hadal.tar.gz"
                        }
                    }
                ).encode()
            ),
            io.BytesIO(archive_bytes),
        ]

        with mock.patch.object(RELEASE, "urlopen", side_effect=responses):
            assert RELEASE.compare_inkdrop_registry(
                "https://api.inkdrop.invalid",
                "hadal",
                "1.2.3",
                artifact,
            )

        with mock.patch.object(
            RELEASE,
            "urlopen",
            side_effect=HTTPError(
                "https://api.inkdrop.invalid/v1/packages/hadal/versions/1.2.3",
                404,
                "Not Found",
                {},
                None,
            ),
        ):
            assert not RELEASE.compare_inkdrop_registry(
                "https://api.inkdrop.invalid",
                "hadal",
                "1.2.3",
                artifact,
            )

        with mock.patch.object(
            RELEASE,
            "urlopen",
            return_value=io.BytesIO(
                json.dumps(
                    {"dist": {"tarball": "https://untrusted.invalid/hadal.tar.gz"}}
                ).encode()
            ),
        ):
            try:
                RELEASE.compare_inkdrop_registry(
                    "https://api.inkdrop.invalid",
                    "hadal",
                    "1.2.3",
                    artifact,
                )
            except RELEASE.ReleaseError:
                pass
            else:
                raise AssertionError("accepted a tarball from another host")


def test_marketplace_status() -> None:
    digest = "a" * 64
    extension = {
        "versions": [
            {
                "version": "1.2.3",
                "properties": [
                    {
                        "key": "Microsoft.VisualStudio.Services.VsixSha256",
                        "value": digest,
                    }
                ],
            }
        ]
    }
    with mock.patch.object(
        RELEASE,
        "run",
        return_value=completed(stdout=json.dumps(extension)),
    ):
        assert RELEASE.compare_marketplace(
            "tcagriz.hadal-theme",
            "1.2.3",
            digest,
        )
        assert not RELEASE.compare_marketplace(
            "tcagriz.hadal-theme",
            "1.2.4",
            digest,
        )

    extension["versions"][0]["properties"][0]["value"] = "b" * 64
    with mock.patch.object(
        RELEASE,
        "run",
        return_value=completed(stdout=json.dumps(extension)),
    ):
        try:
            RELEASE.compare_marketplace(
                "tcagriz.hadal-theme",
                "1.2.3",
                digest,
            )
        except RELEASE.ReleaseError:
            pass
        else:
            raise AssertionError("accepted a different Marketplace VSIX")


def test_workflow_shape() -> None:
    workflow_jobs = jobs(PUBLISH)
    assert set(workflow_jobs) == {"validate", "release", "publish"}, workflow_jobs

    validate = workflow_jobs["validate"]
    release = workflow_jobs["release"]
    publish = workflow_jobs["publish"]

    assert "push:" in PUBLISH and "'v*.*.*'" in PUBLISH
    assert "workflow_dispatch:" not in PUBLISH
    assert "git merge-base --is-ancestor" in validate
    assert "scripts/release.py metadata" in validate
    assert "actions/upload-artifact@v4" in validate
    assert "environment:" not in validate
    assert "secrets." not in validate

    assert "needs: validate" in release
    assert "contents: write" in release
    assert "scripts/release.py ensure-release" in release
    assert "--github-output" in release
    assert "environment:" not in release
    assert "secrets." not in release

    assert "needs:" in publish and "- validate" in publish and "- release" in publish
    assert "environment: production" in publish or "name: production" in publish
    assert "scripts/release.py download-asset" in publish
    assert "needs.release.outputs.sha256" in publish
    assert "skip-duplicate" in publish if KIND == "vscode" else "inkdrop-status" in publish
    assert "--clobber" not in PUBLISH

    if KIND == "vscode":
        ignore = (ROOT / ".vscodeignore").read_text()
        assert "scripts/**" in ignore and "tests/**" in ignore
        assert "RELEASING.md" in ignore
        assert "--packagePath" in publish
        assert "--oidc" in publish
        assert "marketplace-status" in publish
        assert "published != 'true'" in publish
        assert "secrets." not in PUBLISH
        assert "id-token: write" in publish
    else:
        assert set(re.findall(r"secrets\.([A-Z0-9_]+)", PUBLISH)) == SECRET_NAMES
        assert all(
            "secrets." not in block
            for name, block in workflow_jobs.items()
            if name != "publish"
        )
        assert "published != 'true'" in publish
        assert "ipm-cli@1.0.6 publish" in publish
        assert "dist/publish/package" in publish
        assert "protected production environment" in publish

    assert PUBLISH.count("push:") == 1
    assert "pull_request:" not in PUBLISH
    assert "secrets." not in CHECK
    assert all("environment:" not in job for job in jobs(CHECK).values())
    assert "python3 tests/publish_workflow_test.py" in CHECK


def main() -> None:
    test_metadata_validation()
    test_archive_manifest()
    test_release_asset_idempotence()
    test_inkdrop_registry_status()
    test_marketplace_status()
    test_workflow_shape()


if __name__ == "__main__":
    main()
