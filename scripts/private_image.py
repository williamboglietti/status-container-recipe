#!/usr/bin/env python3
"""Gate private GHCR publishing and resolve an immutable previous image."""
import argparse
import base64
import json
import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OWNER = "williamboglietti"
IMAGE = f"ghcr.io/{OWNER}/status-v3"
LEGACY_IMAGE = f"ghcr.io/{OWNER}/cachet-status"
ACCEPT = ", ".join((
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
))
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


class PrivateImageError(RuntimeError):
    """Raised when private package metadata or a registry response is unsafe."""


def private_unlinked_package(package: dict | None) -> bool:
    """Only accept a private package that does not inherit repository access."""
    return bool(package and package.get("visibility") == "private" and not package.get("repository"))


def multiarch_reference(image: str, manifest: dict, digest: str | None) -> str | None:
    """Return a previous digest only for a valid linux/amd64+arm64 manifest index."""
    if not digest or not SHA256.fullmatch(digest):
        return None
    platforms = {
        (entry.get("platform", {}).get("os"), entry.get("platform", {}).get("architecture"))
        for entry in manifest.get("manifests", [])
    }
    if not {("linux", "amd64"), ("linux", "arm64")}.issubset(platforms):
        return None
    return f"{image}@{digest}"


def request_json(url: str, headers: dict[str, str]) -> tuple[dict, object]:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response), response.headers


def github_package(image: str, token: str) -> dict | None:
    owner, package = image.removeprefix("ghcr.io/").split("/", 1)
    url = f"https://api.github.com/users/{owner}/packages/container/{package}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        package_data, _ = request_json(url, headers)
        return package_data
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        if error.code in (401, 403):
            raise PrivateImageError("GHCR package access failed; the PAT needs read:packages and write:packages") from None
        raise PrivateImageError(f"GitHub package metadata request failed with HTTP {error.code}") from None


def latest_multiarch_reference(image: str, username: str, token: str) -> str | None:
    name = image.removeprefix("ghcr.io/")
    scope = urllib.parse.urlencode({"service": "ghcr.io", "scope": f"repository:{name}:pull"})
    basic = base64.b64encode(f"{username}:{token}".encode()).decode()
    try:
        auth, _ = request_json(
            f"https://ghcr.io/token?{scope}",
            {"Authorization": f"Basic {basic}"},
        )
        manifest, headers = request_json(
            f"https://ghcr.io/v2/{name}/manifests/latest",
            {"Authorization": f"Bearer {auth['token']}", "Accept": ACCEPT},
        )
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        if error.code in (401, 403):
            return None
        raise PrivateImageError(f"GHCR manifest lookup failed with HTTP {error.code}") from None
    return multiarch_reference(image, manifest, headers.get("Docker-Content-Digest"))


def write_output(values: dict[str, str]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        raise PrivateImageError("GITHUB_OUTPUT is required")
    with open(output_path, "a", encoding="utf-8") as output:
        for key, value in values.items():
            if "\n" in value or "\r" in value:
                raise PrivateImageError(f"Unsafe multiline workflow output: {key}")
            output.write(f"{key}={value}\n")


def append_summary(message: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write(message.rstrip() + "\n")


def package_bootstrap(token: str, username: str) -> dict:
    """Create an unlinked scratch package; user-scoped GHCR packages default private."""
    temp_root = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "status-v3-ghcr-bootstrap"
    temp_root.mkdir(parents=True, exist_ok=True)
    dockerfile = temp_root / "Dockerfile"
    dockerfile.write_text("FROM scratch\n", encoding="utf-8")
    image = IMAGE + ":private-bootstrap-" + os.environ.get("GITHUB_RUN_ID", "local")
    login = subprocess.run(
        ["docker", "login", "--username", username, "--password-stdin", "ghcr.io"],
        input=token, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if login.returncode:
        raise PrivateImageError("Could not authenticate to GHCR for private package bootstrap")
    try:
        build = subprocess.run(
            ["docker", "buildx", "build", "--platform", "linux/amd64", "--push",
             "--file", str(dockerfile), "--tag", image, str(temp_root)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        if build.returncode:
            raise PrivateImageError("Could not create the private GHCR package with a scratch bootstrap image")
    finally:
        subprocess.run(["docker", "logout", "ghcr.io"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    package = github_package(IMAGE, token)
    if not private_unlinked_package(package):
        raise PrivateImageError("The new GHCR package is not private and unlinked; refusing to build or promote Cachet")
    return package


def prepare() -> None:
    token = os.environ.get("STATUS_V3_GHCR_TOKEN", "")
    username = os.environ.get("STATUS_V3_GHCR_USERNAME", OWNER)
    enabled = os.environ.get("STATUS_V3_PRIVATE_IMAGE_ENABLED", "").lower() == "true"
    if not enabled:
        write_output({"publish_enabled": "false", "previous_image": ""})
        append_summary("Private GHCR publishing is disabled; this run only validates the recipe.")
        return
    if not token:
        write_output({"publish_enabled": "false", "previous_image": ""})
        append_summary("Private GHCR publishing is enabled in settings but the required Actions secret is missing; no image will be pushed.")
        return

    package = github_package(IMAGE, token)
    if package is None:
        package = package_bootstrap(token, username)
    if not private_unlinked_package(package):
        write_output({"publish_enabled": "false", "previous_image": ""})
        append_summary("Private publishing is disabled because the status-v3 GHCR package is public or linked to repository permissions.")
        return

    previous = latest_multiarch_reference(IMAGE, username, token)
    if previous is None:
        legacy = github_package(LEGACY_IMAGE, token)
        if legacy and legacy.get("visibility") == "private":
            previous = latest_multiarch_reference(LEGACY_IMAGE, username, token)

    write_output({"publish_enabled": "true", "previous_image": previous or ""})
    if previous:
        print(f"::add-mask::{previous}")
        append_summary("The private GHCR package is ready. Migration and snapshot-restore tests will use its immutable previous digest.")
    else:
        append_summary("The private GHCR package is ready. No previous multi-architecture digest was found; this is a first-install validation.")


def verify() -> None:
    token = os.environ.get("STATUS_V3_GHCR_TOKEN", "")
    if not token:
        raise PrivateImageError("STATUS_V3_GHCR_TOKEN is required for private promotion")
    package = github_package(IMAGE, token)
    if not private_unlinked_package(package):
        raise PrivateImageError("Refusing tag promotion: status-v3 GHCR package must be private and unlinked from repository permissions")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "verify"))
    command = parser.parse_args().command
    if command == "prepare":
        prepare()
    else:
        verify()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, urllib.error.URLError, PrivateImageError) as error:
        raise SystemExit(f"private GHCR guard: {error}") from None
