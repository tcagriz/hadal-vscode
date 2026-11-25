#!/usr/bin/env python3
"""Validate, attach and retrieve immutable Hadal package release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


TAG_PATTERN = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
KINDS = {"vscode": "vsix", "inkdrop": "tgz"}
INKDROP_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Hadal-release-check/1.0",
    "X-API-KEY": "1",
    "X-CLIENT-VERSION": "6.0.0",
}


class ReleaseError(RuntimeError):
    """A release precondition or artifact invariant failed."""


def parse_tag(tag: str) -> str:
    match = TAG_PATTERN.fullmatch(tag)
    if match is None:
        raise ReleaseError(f"release tag must match vX.Y.Z, got: {tag}")
    return ".".join(match.groups())


def read_metadata(root: Path, kind: str, tag: str) -> dict[str, str]:
    if kind not in KINDS:
        raise ReleaseError(f"unsupported package kind: {kind}")

    version = parse_tag(tag)
    manifest = json.loads((root / "package.json").read_text())
    manifest_version = manifest.get("version")
    if manifest_version != version:
        raise ReleaseError(
            f"tag version {version} does not match package.json {manifest_version}"
        )

    changelog = (root / "CHANGELOG.md").read_text()
    heading = re.compile(rf"^##\s+{re.escape(version)}\s*$", re.MULTILINE)
    if heading.search(changelog) is None:
        raise ReleaseError(f"CHANGELOG.md has no {version} section")

    package_name = manifest.get("name")
    if not isinstance(package_name, str) or not package_name:
        raise ReleaseError("package.json has no valid name")
    if kind == "vscode":
        publisher = manifest.get("publisher")
        if not isinstance(publisher, str) or not publisher:
            raise ReleaseError("package.json has no valid publisher")
    else:
        publisher = None
    artifact_name = f"{package_name.rsplit('/', 1)[-1]}-{version}.{KINDS[kind]}"

    return {
        "package": package_name,
        "version": version,
        "artifact": artifact_name,
        "title": f"Hadal {version}",
        **({"identifier": f"{publisher}.{package_name}"} if publisher else {}),
    }


def append_github_output(path: str, **values: str) -> None:
    with Path(path).open("a") as output:
        for key, value in values.items():
            if "\n" in value or "\r" in value:
                raise ReleaseError(f"GitHub output {key} must be one line")
            output.write(f"{key}={value}\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path: Path, expected: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ReleaseError(f"invalid SHA-256 digest: {expected}")
    if not path.is_file():
        raise ReleaseError(f"release artifact does not exist: {path}")
    actual = sha256(path)
    if actual != expected:
        raise ReleaseError(
            f"release artifact digest mismatch for {path.name}: "
            f"expected {expected}, got {actual}"
        )


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, **kwargs)


def validate_repository(repository: str) -> None:
    if REPOSITORY_PATTERN.fullmatch(repository) is None:
        raise ReleaseError(f"invalid GitHub repository: {repository}")


def get_release(repository: str, tag: str) -> dict | None:
    validate_repository(repository)
    result = run(
        ["gh", "api", "--hostname", "github.com", f"repos/{repository}/releases/tags/{tag}"],
        capture_output=True,
    )
    if result.returncode == 0:
        return json.loads(result.stdout)
    if "HTTP 404" in result.stderr or "Not Found" in result.stderr:
        return None
    raise ReleaseError(result.stderr.strip() or f"failed to inspect release {tag}")


def download_asset(
    repository: str,
    tag: str,
    asset: str,
    expected_sha256: str | None,
    destination: Path,
) -> Path:
    validate_repository(repository)
    if Path(asset).name != asset:
        raise ReleaseError(f"release asset name must be a basename: {asset}")
    if destination.exists():
        raise ReleaseError(f"download destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="hadal-release-asset-") as temp:
        temp_dir = Path(temp)
        result = run(
            [
                "gh",
                "release",
                "download",
                tag,
                "--repo",
                repository,
                "--pattern",
                asset,
                "--dir",
                str(temp_dir),
            ],
            capture_output=True,
        )
        if result.returncode != 0:
            raise ReleaseError(result.stderr.strip() or f"failed to download {asset}")
        downloaded = temp_dir / asset
        if expected_sha256 is not None:
            verify_sha256(downloaded, expected_sha256)
        shutil.copy2(downloaded, destination)

    return destination


def ensure_release(
    repository: str, tag: str, title: str, artifact: Path, expected_sha256: str
) -> str:
    parse_tag(tag)
    validate_repository(repository)
    verify_sha256(artifact, expected_sha256)
    asset_name = artifact.name

    release = get_release(repository, tag)
    if release is None:
        result = run(
            [
                "gh",
                "release",
                "create",
                tag,
                str(artifact),
                "--repo",
                repository,
                "--verify-tag",
                "--title",
                title,
                "--generate-notes",
            ],
            capture_output=True,
        )
        if result.returncode != 0:
            release = get_release(repository, tag)
            if release is None:
                raise ReleaseError(
                    result.stderr.strip() or f"failed to create release {tag}"
                )
        else:
            release = get_release(repository, tag)

    if release is None:
        raise ReleaseError(f"release {tag} was not created")
    if release.get("draft"):
        raise ReleaseError(f"release {tag} is still a draft")

    assets = {item.get("name"): item for item in release.get("assets", [])}
    if asset_name not in assets:
        raise ReleaseError(f"release {tag} is missing artifact {asset_name}")

    with tempfile.TemporaryDirectory(prefix="hadal-release-check-") as temp:
        existing = Path(temp) / asset_name
        download_asset(repository, tag, asset_name, None, existing)
        if artifact_manifest(existing) != artifact_manifest(artifact):
            raise ReleaseError(
                f"release {tag} contains a different artifact manifest for {asset_name}"
            )
        return sha256(existing)


def normalize_archive_members(archive: Path) -> list[tuple[str, str, str]]:
    members: list[tuple[str, str, str]] = []
    with tarfile.open(archive, "r:gz") as package:
        entries = []
        for member in package.getmembers():
            name = member.name
            while name.startswith("./"):
                name = name[2:]
            if not name or name == "." or name.startswith("/") or ".." in Path(name).parts:
                if not name or name == ".":
                    continue
                raise ReleaseError(f"unsafe archive member in {archive.name}: {member.name}")
            entries.append((member, name))

        names = [name for member, name in entries if member.isfile() or member.issym() or member.islnk()]
        strip_package = bool(names) and all(name.startswith("package/") for name in names)

        for member, name in entries:
            relative = name[len("package/") :] if strip_package else name
            if member.isfile():
                stream = package.extractfile(member)
                if stream is None:
                    raise ReleaseError(f"cannot read archive member: {member.name}")
                members.append(
                    (
                        relative,
                        "file",
                        hashlib.sha256(stream.read()).hexdigest(),
                    )
                )
            elif member.issym() or member.islnk():
                members.append(
                    (
                        relative,
                        "link",
                        hashlib.sha256(member.linkname.encode()).hexdigest(),
                    )
                )
    return sorted(members)


def normalize_zip_members(archive: Path) -> list[tuple[str, str, str]]:
    members: list[tuple[str, str, str]] = []
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            name = member.filename.removeprefix("./")
            if member.is_dir():
                continue
            path = Path(name)
            if not name or name.startswith("/") or ".." in path.parts:
                raise ReleaseError(f"unsafe archive member in {archive.name}: {member.filename}")
            members.append(
                (
                    name,
                    "file",
                    hashlib.sha256(package.read(member)).hexdigest(),
                )
            )
    return sorted(members)


def artifact_manifest(artifact: Path) -> list[tuple[str, str, str]]:
    if artifact.suffix == ".vsix":
        return normalize_zip_members(artifact)
    if artifact.suffix == ".tgz":
        return normalize_archive_members(artifact)
    raise ReleaseError(f"unsupported release artifact: {artifact.name}")


def compare_inkdrop_registry(
    base_url: str, package_name: str, version: str, artifact: Path
) -> bool:
    endpoint = (
        f"{base_url.rstrip('/')}/v1/packages/{quote(package_name, safe='')}"
        f"/versions/{quote(version, safe='')}"
    )
    try:
        with urlopen(Request(endpoint, headers=INKDROP_HEADERS), timeout=30) as response:
            metadata = json.load(response)
    except HTTPError as error:
        if error.code == 404:
            return False
        raise ReleaseError(
            f"failed to inspect Inkdrop registry version: HTTP {error.code}"
        ) from error

    tarball_url = (metadata.get("dist") or {}).get("tarball")
    if not isinstance(tarball_url, str) or not tarball_url:
        raise ReleaseError("Inkdrop registry version has no tarball URL")
    base = urlsplit(base_url)
    tarball = urlsplit(tarball_url)
    if (
        base.scheme != "https"
        or tarball.scheme != "https"
        or not base.hostname
        or tarball.hostname != base.hostname
        or tarball.username
        or tarball.password
    ):
        raise ReleaseError("Inkdrop registry returned an unexpected tarball URL")

    with tempfile.TemporaryDirectory(prefix="hadal-inkdrop-registry-") as temp:
        downloaded = Path(temp) / "registry.tar.gz"
        request = Request(tarball_url, headers=INKDROP_HEADERS)
        with urlopen(request, timeout=60) as response:
            downloaded.write_bytes(response.read())

        expected = normalize_archive_members(artifact)
        published = normalize_archive_members(downloaded)
        if expected != published:
            missing = sorted(set(expected) - set(published))
            extra = sorted(set(published) - set(expected))
            raise ReleaseError(
                "Inkdrop registry version exists with different content: "
                f"missing={missing}, extra={extra}"
            )
    return True


def compare_marketplace(identifier: str, version: str, expected_sha256: str) -> bool:
    if not re.fullmatch(
        r"[A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+",
        identifier,
    ):
        raise ReleaseError(f"invalid VS Code Marketplace identifier: {identifier}")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ReleaseError(f"invalid SHA-256 digest: {expected_sha256}")

    result = run(
        [
            "npx",
            "--yes",
            "@vscode/vsce@4.1.1",
            "show",
            identifier,
            "--json",
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise ReleaseError(result.stderr.strip() or f"failed to inspect {identifier}")

    extension = json.loads(result.stdout)
    version_info = next(
        (
            item
            for item in extension.get("versions", [])
            if item.get("version") == version
        ),
        None,
    )
    if version_info is None:
        return False

    properties = {
        item.get("key"): item.get("value")
        for item in version_info.get("properties", [])
    }
    published_sha256 = properties.get(
        "Microsoft.VisualStudio.Services.VsixSha256"
    )
    if not isinstance(published_sha256, str):
        raise ReleaseError(
            f"Marketplace version {version} has no VSIX SHA-256 property"
        )
    if published_sha256.lower() != expected_sha256.lower():
        raise ReleaseError(
            "Marketplace version exists with a different VSIX: "
            f"expected {expected_sha256}, got {published_sha256}"
        )
    return True


def command_metadata(args: argparse.Namespace) -> None:
    metadata = read_metadata(args.root.resolve(), args.kind, args.tag)
    if args.github_output:
        append_github_output(args.github_output, **metadata)
    else:
        print(json.dumps(metadata, sort_keys=True))


def command_fingerprint(args: argparse.Namespace) -> None:
    artifact = args.artifact.resolve()
    if not artifact.is_file():
        raise ReleaseError(f"artifact does not exist: {artifact}")
    digest = sha256(artifact)
    if args.github_output:
        append_github_output(args.github_output, sha256=digest)
    else:
        print(digest)


def command_ensure_release(args: argparse.Namespace) -> None:
    resolved_sha256 = ensure_release(
        args.repo,
        args.tag,
        args.title,
        args.artifact.resolve(),
        args.sha256,
    )
    if args.github_output:
        append_github_output(args.github_output, sha256=resolved_sha256)
    else:
        print(resolved_sha256)


def command_download_asset(args: argparse.Namespace) -> None:
    artifact = download_asset(
        args.repo,
        args.tag,
        args.asset,
        args.sha256,
        args.output.resolve(),
    )
    if artifact.name != args.asset:
        raise ReleaseError(f"downloaded artifact name changed: {artifact.name}")


def command_inkdrop_status(args: argparse.Namespace) -> None:
    published = compare_inkdrop_registry(
        args.base_url,
        args.name,
        args.version,
        args.artifact.resolve(),
    )
    value = "true" if published else "false"
    if args.github_output:
        append_github_output(args.github_output, published=value)
    else:
        print(value)


def command_marketplace_status(args: argparse.Namespace) -> None:
    published = compare_marketplace(args.identifier, args.version, args.sha256)
    value = "true" if published else "false"
    if args.github_output:
        append_github_output(args.github_output, published=value)
    else:
        print(value)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    commands = result.add_subparsers(dest="command", required=True)

    metadata = commands.add_parser("metadata")
    metadata.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    metadata.add_argument("--kind", choices=sorted(KINDS), required=True)
    metadata.add_argument("--tag", required=True)
    metadata.add_argument("--github-output")
    metadata.set_defaults(func=command_metadata)

    fingerprint = commands.add_parser("fingerprint")
    fingerprint.add_argument("--artifact", type=Path, required=True)
    fingerprint.add_argument("--github-output")
    fingerprint.set_defaults(func=command_fingerprint)

    release = commands.add_parser("ensure-release")
    release.add_argument("--repo", required=True)
    release.add_argument("--tag", required=True)
    release.add_argument("--title", required=True)
    release.add_argument("--artifact", type=Path, required=True)
    release.add_argument("--sha256", required=True)
    release.add_argument("--github-output")
    release.set_defaults(func=command_ensure_release)

    download = commands.add_parser("download-asset")
    download.add_argument("--repo", required=True)
    download.add_argument("--tag", required=True)
    download.add_argument("--asset", required=True)
    download.add_argument("--sha256", required=True)
    download.add_argument("--output", type=Path, required=True)
    download.set_defaults(func=command_download_asset)

    registry = commands.add_parser("inkdrop-status")
    registry.add_argument("--base-url", default="https://api.inkdrop.app")
    registry.add_argument("--name", required=True)
    registry.add_argument("--version", required=True)
    registry.add_argument("--artifact", type=Path, required=True)
    registry.add_argument("--github-output")
    registry.set_defaults(func=command_inkdrop_status)

    marketplace = commands.add_parser("marketplace-status")
    marketplace.add_argument("--identifier", required=True)
    marketplace.add_argument("--version", required=True)
    marketplace.add_argument("--sha256", required=True)
    marketplace.add_argument("--github-output")
    marketplace.set_defaults(func=command_marketplace_status)
    return result


def main() -> None:
    try:
        args = parser().parse_args()
        args.func(args)
    except (ReleaseError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"release error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
