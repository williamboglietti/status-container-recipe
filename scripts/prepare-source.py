#!/usr/bin/env python3
"""Materialize the immutable upstream app and our tested Composer lock."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def fetch_app(commit: str, destination: Path) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Expected an immutable Cachet app SHA")
    url = f"https://codeload.github.com/cachethq/cachet/tar.gz/{commit}"
    request = urllib.request.Request(url, headers={"User-Agent": "cachet-status-build"})
    with urllib.request.urlopen(request, timeout=120) as response:
        archive = response.read(32 * 1024 * 1024 + 1)
    if len(archive) > 32 * 1024 * 1024:
        raise ValueError("Unexpectedly large app archive")
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        members = bundle.getmembers()
        for member in members:
            parts = Path(member.name).parts
            if not parts or any(part in ("..", ".") for part in parts):
                raise ValueError("Unsafe upstream archive path")
            if member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                raise ValueError("Unexpected link or special file in app archive")
            member.name = str(Path(*parts[1:]))
            if len(parts) == 1:
                continue
            bundle.extract(member, destination, filter="data")
    # Never materialize private dotenv/DB files in a build context.
    for file in destination.glob(".env*"):
        file.unlink()
    (destination / "database/database.sqlite").unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=ROOT / "sources.lock.json")
    parser.add_argument("--lock", type=Path, default=ROOT / "composer.lock")
    parser.add_argument("--destination", type=Path, default=ROOT / ".build/source")
    args = parser.parse_args()
    metadata = json.loads(args.metadata.read_text())
    lock_bytes = args.lock.read_bytes()
    if hashlib.sha256(lock_bytes).hexdigest() != metadata["composer_lock_sha256"]:
        raise ValueError("Composer lock differs from the resolved source receipt")
    lock = json.loads(lock_bytes)
    core = next(package for package in lock["packages"] if package["name"] == "cachethq/core")
    if core["source"]["reference"] != metadata["core"]["commit"]:
        raise ValueError("Core SHA differs from the resolved source receipt")
    destination = args.destination.resolve()
    if destination != (ROOT / ".build/source").resolve():
        raise ValueError("Only the dedicated build-source directory is accepted")
    if destination.exists():
        shutil.rmtree(destination)
    fetch_app(metadata["app"]["commit"], destination)
    shutil.copyfile(args.lock, destination / "composer.lock")
    print(f"Prepared app {metadata['app']['commit']} / core {metadata['core']['commit']}")


if __name__ == "__main__":
    main()
