#!/usr/bin/env python3
"""Run local project commands with argument lists and private setup files."""
import argparse
import base64
import importlib.util
import os
from pathlib import Path
import platform
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_args", ROOT / "scripts/build-args.py")
BUILD_ARGS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD_ARGS)
COMMANDS = (
    "build", "compose-build", "compose-up", "compose-down", "test-image",
    "test-healthcheck", "test-pgsql", "test-mysql", "test-mariadb", "test-compose",
)


def run(arguments: list[str]) -> None:
    subprocess.run(arguments, cwd=ROOT, check=True)


def native_platform() -> str:
    architecture = platform.machine().lower()
    return "linux/" + {"x86_64": "amd64", "aarch64": "arm64"}.get(architecture, architecture)


def create_secrets(root: Path, email: str) -> None:
    directory = root / ".secrets"
    directory.mkdir(mode=0o700, exist_ok=True)
    values = {
        "app-key": "base64:" + base64.b64encode(secrets.token_bytes(32)).decode(),
        "database-password": secrets.token_hex(24),
        "admin-email": email,
        "admin-password": secrets.token_urlsafe(24),
    }
    for name, value in values.items():
        path = directory / name
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        except FileExistsError:
            continue
        with os.fdopen(descriptor, "w") as stream:
            # Bind-mounted files must remain readable by container UID 33,
            # even when the invoking shell has a restrictive umask.
            os.fchmod(stream.fileno(), 0o444)
            stream.write(value)


def execute(command: str) -> None:
    image = os.environ.get("IMAGE") or "status-container-recipe:local"
    target_platform = os.environ.get("PLATFORM") or native_platform()
    if command in {"build", "compose-build"}:
        run([sys.executable, str(ROOT / "scripts/prepare-source.py")])
        arguments = ["docker", "buildx", "build", "--load", "--platform", target_platform, "--tag", image]
        for name, value in BUILD_ARGS.build_arguments(ROOT).items():
            arguments.extend(["--build-arg", f"{name}={value}"])
        run([*arguments, "."])
    elif command == "compose-up":
        create_secrets(ROOT, os.environ.get("ADMIN_EMAIL", "admin@example.com"))
        run(["docker", "compose", "up", "--detach"])
    elif command == "compose-down":
        run(["docker", "compose", "down"])
    else:
        if command in {"test-pgsql", "test-mysql", "test-mariadb"}:
            script = "test-database.py"
            extra = ["--database", command.removeprefix("test-")]
        else:
            script = command + ".py"
            extra = ["--platform", target_platform] if command == "test-healthcheck" else []
        run([sys.executable, str(ROOT / "test" / script), "--image", image, *extra])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=COMMANDS)
    execute(parser.parse_args().command)


if __name__ == "__main__":
    main()
