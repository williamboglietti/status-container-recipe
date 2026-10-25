#!/usr/bin/env python3
"""Poll Cachet v3, PHP bases and Composer; record exactly what will be built."""
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "sources.lock.json"
LOCK = ROOT / "composer.lock"
SPEC = importlib.util.spec_from_file_location("prepare_source", ROOT / "scripts/prepare-source.py")
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)


def run(command: list[str], *, capture: bool = False) -> str:
    result = subprocess.run(command, cwd=ROOT, check=True, text=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else ""


def branch_sha(repository: str, branch: str) -> str:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "cachet-status-build",
               "X-GitHub-Api-Version": "2022-11-28"}
    # Read-only upstream request; never forward this token to Composer or Docker.
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"https://api.github.com/repos/{repository}/commits/{branch}", headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        sha = json.load(response)["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Invalid upstream SHA")
    return sha


def image_digest(tag: str) -> str:
    inspection = run(["docker", "buildx", "imagetools", "inspect", tag], capture=True)
    match = re.search(r"^Digest:\s+(sha256:[0-9a-f]{64})$", inspection, re.MULTILINE)
    if not match:
        raise ValueError(f"Could not resolve immutable image digest for {tag}")
    return match.group(1)


def recipe_hash(root: Path = ROOT) -> str:
    paths = [root / "Dockerfile", root / "Makefile", root / "docker-compose.yml",
             *(root / "docker").rglob("*"), *(root / "scripts").rglob("*"),
             *(root / "test").rglob("*")]
    digest = hashlib.sha256()
    for path in sorted(paths):
        relative = path.relative_to(root)
        if path.is_file() and "__pycache__" not in relative.parts and path.suffix not in {".pyc", ".pyo"}:
            digest.update(str(relative).encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Re-resolve and rebuild even without upstream changes")
    parser.add_argument("--refresh-dependencies", action="store_true", help="Daily Composer dependency refresh")
    args = parser.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    today = now.date().isoformat()
    week = f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"
    previous = json.loads(METADATA.read_text()) if METADATA.exists() else {}
    metadata = {
        "schema_version": 1,
        "app": {"repository": "cachethq/cachet", "branch": "3.x", "commit": branch_sha("cachethq/cachet", "3.x")},
        "core": {"repository": "cachethq/core", "branch": "main", "commit": branch_sha("cachethq/core", "main")},
        "images": {},
        "recipe_sha256": recipe_hash(),
        "os_rebuild_week": week,
    }
    for key, tag in {"frankenphp": "dunglas/frankenphp:1-php8.4-bookworm", "composer": "composer:2"}.items():
        metadata["images"][key] = {"tag": tag, "digest": image_digest(tag)}
    weekly = previous.get("os_rebuild_week") != week
    needs_resolution = args.force or args.refresh_dependencies or not LOCK.exists()
    for key in ("app", "core", "images", "recipe_sha256", "os_rebuild_week"):
        needs_resolution = needs_resolution or previous.get(key) != metadata[key]
    if needs_resolution:
        source = ROOT / ".build/resolve"
        if source.exists():
            shutil.rmtree(source)
        PREPARE.fetch_app(metadata["app"]["commit"], source)
        # Preserve the previous lock as the update starting point if the app manifest hasn't changed.
        if LOCK.exists() and previous.get("app") == metadata["app"]:
            shutil.copyfile(LOCK, source / "composer.lock")
        bases = ["--build-arg", "FRANKENPHP_IMAGE=" + reference(metadata, "frankenphp"),
                 "--build-arg", "COMPOSER_IMAGE=" + reference(metadata, "composer")]
        command = ["docker", "build", "--target", "toolchain", "--tag", "cachet-status-toolchain:local", *bases]
        if weekly or args.force:
            command.append("--no-cache")
        run([*command, "."])
        run(["docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}",
             "--env", "COMPOSER_HOME=/tmp/composer", "--env", "COMPOSER_ALLOW_SUPERUSER=1",
             "--mount", f"type=bind,src={source},dst=/work", "--workdir", "/work",
             "--entrypoint", "composer", "cachet-status-toolchain:local",
             "update", "--no-install", "--no-dev", "--no-scripts", "--no-plugins",
             "--prefer-dist", "--no-interaction", "--no-progress"])
        new_lock = json.loads((source / "composer.lock").read_text())
        core = next(package for package in new_lock["packages"] if package["name"] == "cachethq/core")
        if core["source"]["reference"] != metadata["core"]["commit"]:
            raise ValueError("Upstream core advanced while resolving; retry with a fresh snapshot")
        shutil.copyfile(source / "composer.lock", LOCK)
        metadata["dependency_checked_on"] = today
    else:
        metadata["dependency_checked_on"] = previous["dependency_checked_on"]
    metadata["composer_lock_sha256"] = hashlib.sha256(LOCK.read_bytes()).hexdigest()
    payload = {key: value for key, value in metadata.items() if key != "dependency_checked_on"}
    metadata["fingerprint"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    changed = args.force or metadata["fingerprint"] != previous.get("fingerprint")
    write_json(METADATA, metadata)
    outputs = {
        "changed": str(changed).lower(), "fingerprint": metadata["fingerprint"],
        "app_ref": metadata["app"]["commit"], "core_ref": metadata["core"]["commit"],
        "frankenphp_image": reference(metadata, "frankenphp"), "composer_image": reference(metadata, "composer"),
        "force_rebuild": str(weekly or args.force).lower(),
    }
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a") as handle:
            for key, value in outputs.items():
                handle.write(f"{key}={value}\n")
    print(json.dumps(outputs, indent=2))


def reference(metadata: dict, key: str) -> str:
    image = metadata["images"][key]
    return image["tag"] + "@" + image["digest"]


if __name__ == "__main__":
    main()
