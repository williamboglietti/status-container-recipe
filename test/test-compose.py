#!/usr/bin/env python3
"""Run the repository's docker-compose.yml end to end with an already built image."""
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    (ROOT / ".test").mkdir(exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="compose-", dir=ROOT / ".test"))
    project = "cachet-compose-" + uuid.uuid4().hex[:10]
    port = free_port()
    private = {
        "app-key": "base64:" + base64.b64encode(secrets.token_bytes(32)).decode(),
        "database-password": secrets.token_hex(24),
        "admin-email": "compose@cachet.invalid",
        "admin-password": secrets.token_urlsafe(24),
    }
    secrets_directory = workspace / ".secrets"
    secrets_directory.mkdir(mode=0o700)
    for name, value in private.items():
        path = secrets_directory / name
        path.write_text(value)
        path.chmod(0o444)
    environment = {**os.environ, "CACHET_IMAGE": args.image, "CACHET_HTTP": f"127.0.0.1:{port}",
                   "APP_URL": f"http://127.0.0.1:{port}"}
    url = f"http://127.0.0.1:{port}"

    def compose(*arguments: str, check: bool = True) -> subprocess.CompletedProcess:
        result = subprocess.run(["docker", "compose", "--project-name", project,
                                 "--project-directory", str(workspace), "--file", str(ROOT / "docker-compose.yml"),
                                 *arguments], env=environment, capture_output=True, text=True, timeout=600)
        output = result.stdout + result.stderr
        if any(private[name] in output for name in ("app-key", "database-password", "admin-password")):
            raise RuntimeError("A generated credential appeared in Docker Compose output")
        if check and result.returncode:
            raise RuntimeError(f"docker compose {arguments[0]} failed ({result.returncode}): {output[-4000:]}")
        return result

    def states() -> dict[str, dict]:
        lines = compose("ps", "--all", "--format", "json").stdout.splitlines()
        return {entry["Service"]: entry for entry in map(json.loads, filter(None, lines))}

    def wait_until_ready() -> None:
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            current = states()
            for step in ("migrate", "initialize"):
                if current.get(step, {}).get("State") == "exited" and current[step].get("ExitCode") != 0:
                    raise RuntimeError(step + " failed: " + compose("logs", "--no-color", step).stdout[-3000:])
            if all(current.get(role, {}).get("Health") == "healthy" for role in ("web", "worker", "scheduler")):
                return
            time.sleep(3)
        raise RuntimeError("Compose services did not become healthy: " + json.dumps(states()))

    def status(path: str) -> int:
        try:
            with urllib.request.urlopen(url + path, timeout=15) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    try:
        compose("up", "--detach", "--no-build")
        wait_until_ready()
        expected = {"/up": 200, "/": 200, "/dashboard/login": 200, "/api/components": 404}
        actual = {path: status(path) for path in expected}
        if actual != expected:
            raise RuntimeError("Unexpected HTTP statuses: " + json.dumps(actual))
        print("PASS: docker-compose.yml migrates, initializes and serves Cachet", flush=True)
        # A second start must leave the existing administrator and schema alone.
        compose("up", "--detach", "--no-build", "--force-recreate")
        wait_until_ready()
        if "Existing initialization preserved" not in compose("logs", "--no-color", "initialize").stdout:
            raise RuntimeError("The second initialize run did not preserve the existing installation")
        if status("/up") != 200:
            raise RuntimeError("Cachet did not answer after a restart")
        compose("logs", "--no-color")
        print("PASS: restart keeps the initialized installation", flush=True)
    finally:
        # Only this randomly named project and its synthetic data are removed.
        compose("down", "--volumes", "--remove-orphans", "--timeout", "20", check=False)
        shutil.rmtree(workspace)


if __name__ == "__main__":
    main()
