#!/usr/bin/env python3
"""Check all image roles with isolated Compose storage and real process failures."""
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--platform", default="linux/amd64")
    args = parser.parse_args()
    (ROOT / ".test").mkdir(exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="healthcheck-", dir=ROOT / ".test"))
    project = "cachet-health-" + uuid.uuid4().hex[:10]
    private = {
        "app_key": "base64:" + base64.b64encode(secrets.token_bytes(32)).decode(),
        "admin_password": secrets.token_urlsafe(36),
        "admin_email": "healthcheck@cachet.invalid",
    }
    for name, value in private.items():
        path = workspace / name
        path.write_text(value + "\n")
        path.chmod(0o444)  # Parent is 0700; mounted files must be readable by UID 33.

    def docker(*arguments: str, check: bool = True) -> subprocess.CompletedProcess:
        result = subprocess.run(["docker", *arguments], capture_output=True, text=True, timeout=180)
        output = result.stdout + result.stderr
        if any(value in output for value in (private["app_key"], private["admin_password"])):
            raise RuntimeError("A generated credential appeared in Docker output")
        if check and result.returncode:
            raise RuntimeError(f"Docker {arguments[0]} failed ({result.returncode}): {output[-4000:]}")
        return result

    context = json.loads(docker("context", "inspect").stdout)[0]
    endpoint = os.environ.get("DOCKER_HOST") or context["Endpoints"]["docker"]["Host"]
    if not endpoint.startswith(("unix://", "npipe://")):
        raise RuntimeError("Healthcheck tests require a local Docker endpoint")

    services = {}
    for role in ("web", "worker", "scheduler", "migrate", "initialize"):
        service = {
            "image": args.image, "platform": args.platform, "init": True,
            "command": [role], "restart": "no", "user": "33:33",
            "mem_limit": "512m" if role == "web" else "256m",
            "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
            "volumes": ["storage:/app/storage"],
            "environment": {
                "APP_KEY_FILE": "/run/secrets/app_key", "APP_URL": "http://localhost",
                "DB_CONNECTION": "sqlite", "DB_DATABASE": "/app/storage/app/cachet.sqlite",
                "SESSION_SECURE_COOKIE": "false",
            },
            "secrets": ["app_key"],
        }
        if role in ("migrate", "initialize"):
            service["profiles"] = ["setup"]
        else:
            # Keep the image's actual probe; accelerate only Docker's polling.
            service["healthcheck"] = {"interval": "5s", "timeout": "5s", "retries": 2,
                                      "start_period": "15s"}
        if role == "initialize":
            service["secrets"] += ["admin_email", "admin_password"]
            service["environment"].update({
                "ADMIN_EMAIL_FILE": "/run/secrets/admin_email",
                "ADMIN_PASSWORD_FILE": "/run/secrets/admin_password",
            })
        services[role] = service
    compose_file = workspace / "compose.json"
    config = {"services": services, "volumes": {"storage": {}},
              "secrets": {name: {"file": str(workspace / name)} for name in private}}
    compose_file.write_text(json.dumps(config))

    def compose(*arguments: str, check: bool = True) -> subprocess.CompletedProcess:
        return docker("compose", "--project-name", project, "--file", str(compose_file),
                      *arguments, check=check)

    identifiers: dict[str, str] = {}

    def identifier(role: str) -> str:
        if role not in identifiers:
            identifiers[role] = compose("ps", "--all", "--quiet", role).stdout.strip()
        return identifiers[role]

    def state(role: str) -> dict:
        return json.loads(docker("inspect", "--format", "{{json .State}}", identifier(role)).stdout)

    def wait_health(expected: dict[str, str]) -> None:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            output = docker("inspect", "--format", "{{json .State}}",
                            *(identifier(role) for role in expected)).stdout
            actual = dict(zip(expected, (json.loads(line) for line in output.splitlines()), strict=True))
            if any(not value["Running"] or value["OOMKilled"] for value in actual.values()):
                raise RuntimeError("A role exited or was OOM-killed: " + json.dumps(actual))
            if all(actual[role].get("Health", {}).get("Status") == status
                   for role, status in expected.items()):
                return
            time.sleep(2)
        raise RuntimeError("Health state timeout: " + json.dumps(actual))

    try:
        metadata = json.loads(docker("image", "inspect", args.image).stdout)[0]
        platform = metadata["Os"] + "/" + metadata["Architecture"]
        if platform != args.platform:
            raise RuntimeError("Image platform differs from the requested test platform")
        print("Image platform:", platform, flush=True)
        print("Image probe:", json.dumps(metadata["Config"].get("Healthcheck")), flush=True)
        compose("run", "--rm", "migrate")
        compose("run", "--rm", "initialize")
        compose("up", "--detach", "web", "worker", "scheduler")
        expected = {role: "healthy" for role in ("web", "worker", "scheduler")}
        wait_health(expected)
        print(compose("ps").stdout, flush=True)

        # A paused process must not pass merely because its PID still exists.
        worker = identifier("worker")
        signal_code = (
            "$p=explode(' ',trim(file_get_contents('/tmp/cachet-healthcheck')));"
            "exit(posix_kill((int)$p[1],(int)$argv[1])?0:1);"
        )
        docker("exec", worker, "php", "-r", signal_code, "19")
        wait_health({"worker": "unhealthy"})
        docker("exec", worker, "php", "-r", signal_code, "18")
        wait_health(expected)
        print("PASS: stopped worker becomes unhealthy and recovers after SIGCONT", flush=True)

        # Normally exec + init exits the container when its worker dies. Keep a
        # test-only parent alive so Docker can record a health failure after death.
        services["worker"]["entrypoint"] = ["/bin/sh", "-c",
            "/usr/local/bin/cachet-entrypoint worker & child=$$!; wait \"$$child\"; exec sleep 300"]
        services["worker"]["command"] = []
        compose_file.write_text(json.dumps(config))
        compose("up", "--detach", "--force-recreate", "worker")
        identifiers.pop("worker")
        wait_health(expected)
        worker = identifier("worker")
        docker("exec", worker, "php", "-r", signal_code, "9")
        wait_health({"web": "healthy", "worker": "unhealthy", "scheduler": "healthy"})
        print("After SIGKILL of the actual queue:work process (test parent stays alive):", flush=True)
        print(compose("ps").stdout, flush=True)
        print("Worker probe failure:", json.dumps(state("worker")["Health"]["Log"][-1]), flush=True)
        services["worker"].pop("entrypoint")
        services["worker"]["command"] = ["worker"]
        compose_file.write_text(json.dumps(config))
        compose("up", "--detach", "--force-recreate", "worker")
        identifiers.pop("worker")
        wait_health(expected)
        print("Recovered normal image entrypoint:", flush=True)
        print(compose("ps").stdout, flush=True)
        compose("logs", "--no-color")  # docker() refuses any leaked test credential.
        print("PASS: all roles healthy; killed worker unhealthy; recovery healthy", flush=True)
    finally:
        # Only this randomly named test project and its synthetic data are removed.
        compose("down", "--volumes", "--remove-orphans", "--timeout", "10")
        shutil.rmtree(workspace)


if __name__ == "__main__":
    main()
