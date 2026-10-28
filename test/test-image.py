#!/usr/bin/env python3
"""Exercise new install, persistence, processes and previous-image DB upgrade."""
import argparse
import base64
import html
import http.cookiejar
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import urllib.parse
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--previous", help="Immutable previous image reference, never a mutable latest tag")
    parser.add_argument("--report", type=Path, default=ROOT / ".build/test-report.json")
    args = parser.parse_args()
    args.report.unlink(missing_ok=True)
    if args.previous and not re.search(r"@sha256:[0-9a-f]{64}$", args.previous):
        parser.error("--previous must be an immutable registry digest")
    (ROOT / ".test").mkdir(exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="cachet-", dir=ROOT / ".test"))
    name = "cachet-ci-" + uuid.uuid4().hex[:12]
    volumes: list[str] = []
    containers: list[str] = []
    results: list[str] = []
    key = "base64:" + base64.b64encode(secrets.token_bytes(32)).decode()
    password = secrets.token_urlsafe(36)
    # Parent directory is 0700. The individual bind-mounted files must be readable by UID 33.
    for filename, value in {"key": key, "email": "ci-admin@cachet.invalid", "password": password}.items():
        path = workspace / filename
        path.write_text(value + "\n")
        path.chmod(0o444)
    env = workspace / "runtime.env"
    env.write_text("\n".join([
        "APP_ENV=production", "APP_DEBUG=false", "APP_URL=http://localhost", "APP_NAME=Cachet CI",
        "APP_KEY_FILE=/run/secrets/key", "ADMIN_EMAIL_FILE=/run/secrets/email",
        "ADMIN_PASSWORD_FILE=/run/secrets/password", "ADMIN_NAME=CI administrator",
        "DB_CONNECTION=sqlite", "DB_DATABASE=/app/storage/app/cachet.sqlite",
        "SESSION_SECURE_COOKIE=false", "CACHET_TITLE=Cachet CI",
        "CACHET_DEMO_MODE=false", "CACHET_BEACON=false", "CACHET_FEED_URI=",
    ]) + "\n")
    env.chmod(0o600)

    def command(arguments: list[str], *, check: bool = True, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
        completed = subprocess.run(["docker", *arguments], input=input_bytes,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if check and completed.returncode:
            safe = (completed.stdout + completed.stderr).decode(errors="replace")
            safe = safe.replace(password, "[redacted]").replace(key, "[redacted]")
            raise RuntimeError(f"Docker {arguments[0]} failed ({completed.returncode}):\n{safe[-6000:]}")
        return completed

    def new_volume(suffix: str) -> str:
        volume = name + "-" + suffix
        command(["volume", "create", volume])
        volumes.append(volume)
        return volume

    def runtime(volume: str) -> list[str]:
        options = ["--env-file", str(env), "--volume", volume + ":/app/storage",
                   "--cap-drop=ALL", "--security-opt=no-new-privileges:true"]
        for filename in ("key", "email", "password"):
            options.extend(["--mount", f"type=bind,src={workspace / filename},dst=/run/secrets/{filename},readonly"])
        options.extend(["--mount", f"type=bind,src={ROOT / 'test/fixture.php'},dst=/test/fixture.php,readonly"])
        return options

    def cli(image: str, volume: str, *mode: str, check: bool = True,
            variables: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        extra = [item for name, value in (variables or {}).items() for item in ("--env", f"{name}={value}")]
        return command(["run", "--rm", *runtime(volume), *extra, image, *mode], check=check)

    def cachet2_variables(volume: str) -> None:
        legacy = {"DB_DRIVER": "sqlite", "CACHE_DRIVER": "file", "QUEUE_DRIVER": "sync",
                  "MAIL_DRIVER": "smtp", "MAIL_ADDRESS": "status@example.com", "MAIL_NAME": "Status",
                  "REDIS_DATABASE": "2", "APP_LOG": "errorlog", "TRUSTED_PROXIES": "*"}
        current = ["DB_CONNECTION", "CACHE_STORE", "QUEUE_CONNECTION", "MAIL_MAILER", "MAIL_FROM_ADDRESS",
                   "MAIL_FROM_NAME", "REDIS_DB", "LOG_CHANNEL", "CACHET_TRUSTED_PROXIES"]
        mapped = cli(args.image, volume, "exec", "printenv", *current, variables=legacy).stdout.decode()
        if mapped.splitlines() != list(legacy.values()):
            raise RuntimeError("Cachet 2 variable names were not mapped onto Cachet 3 settings")
        ignored = cli(args.image, volume, "exec", "true", variables={"DB_PREFIX": "chq_"}).stderr.decode()
        if "DB_PREFIX" not in ignored:
            raise RuntimeError("An ignored Cachet 2 variable produced no warning")
        for refused in ({"DB_DRIVER": "pgsql"}, {"CACHE_DRIVER": "apc"}, {"MAIL_DRIVER": "sendmail"}):
            if cli(args.image, volume, "exec", "true", check=False, variables=refused).returncode == 0:
                raise RuntimeError("A conflicting or unsupported Cachet 2 setting was accepted: " + json.dumps(refused))

    def snapshot(image: str, volume: str, *, fixture: bool = False) -> dict:
        raw = cli(image, volume, "exec", "php", "/test/fixture.php", "fixture" if fixture else "snapshot").stdout.decode()
        return json.loads(raw.strip().splitlines()[-1])

    def preserved(before: dict, after: dict) -> None:
        if before["tables"] != after["tables"] or before["upload_sha256"] != after["upload_sha256"]:
            raise RuntimeError("Account, component, incident or upload changed across a restart/migration")
        for setting, value in before["settings"].items():
            if after["settings"].get(setting) != value:
                raise RuntimeError(f"Existing setting changed across a migration: {setting}")

    def start(image: str, volume: str, mode: str = "web") -> tuple[str, str | None]:
        container = name + "-" + mode
        options = ["run", "--detach", "--name", container, *runtime(volume)]
        if mode == "web":
            options.extend(["--publish", "127.0.0.1::8000"])
        command([*options, image, mode])
        containers.append(container)
        if mode != "web":
            time.sleep(3)
            state = json.loads(command(["inspect", container]).stdout)[0]["State"]
            if not state["Running"]:
                raise RuntimeError(f"{mode} exited: " + command(["logs", container], check=False).stdout.decode()[-2000:])
            return container, None
        bindings = json.loads(command(["inspect", container]).stdout)[0]["NetworkSettings"]["Ports"]["8000/tcp"]
        if not bindings:
            raise RuntimeError("Loopback port publication missing")
        url = "http://127.0.0.1:" + bindings[0]["HostPort"]
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url + "/up", timeout=3) as response:
                    if response.status == 200:
                        return container, url
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                time.sleep(1)
        logs = command(["logs", container], check=False)
        raise RuntimeError("HTTP readiness failed: " + (logs.stdout + logs.stderr).decode()[-3000:])

    def stop(container: str) -> None:
        command(["stop", "--time", "70", container])
        logs = command(["logs", container], check=False)
        if password.encode() in logs.stdout + logs.stderr or key.encode() in logs.stdout + logs.stderr:
            raise RuntimeError("A private test credential leaked to container logs")
        command(["rm", container])
        containers.remove(container)

    def check_http(url: str) -> None:
        public = urllib.request.urlopen(url + "/", timeout=15).read().decode()
        login = urllib.request.urlopen(url + "/dashboard/login", timeout=15).read().decode()
        if "livewire" not in login.lower() or "password" not in login.lower():
            raise RuntimeError("Admin login page is missing")
        assets = set(re.findall(r'(?:src|href)=["\']([^"\']+\.(?:css|js)(?:\?[^"\']*)?)["\']', public + login))
        internal = 0
        for asset in assets:
            asset = html.unescape(asset)
            parsed = urllib.parse.urlparse(asset)
            if asset.startswith("/") or parsed.hostname in {"localhost", "127.0.0.1"}:
                path = parsed.path + ("?" + parsed.query if parsed.query else "")
                with urllib.request.urlopen(url + path, timeout=15) as response:
                    if response.status != 200:
                        raise RuntimeError("Packaged asset failed: " + path)
                internal += 1
        if internal < 2:
            raise RuntimeError("No packaged public/admin assets found")
        for path in ("/api/components", "/mcp", "/.env", "/composer.lock"):
            try:
                response = urllib.request.urlopen(url + path, timeout=15)
                response.close()
                raise RuntimeError("Protected/non-public path answered successfully: " + path)
            except urllib.error.HTTPError as error:
                if error.code not in (403, 404, 405):
                    raise RuntimeError(f"Unexpected HTTP {error.code} on {path}") from error
        # An anonymous dashboard request must end on the login page.
        with urllib.request.urlopen(url + "/dashboard", timeout=15) as response:
            if "/login" not in response.url:
                raise RuntimeError("Anonymous request reached the dashboard")
        # Exercise the real Filament/Livewire login with a disposable administrator.
        cookies = http.cookiejar.CookieJar()
        browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
        login = browser.open(url + "/dashboard/login", timeout=15).read().decode()
        csrf = re.search(r'<meta name="csrf-token" content="([^\"]+)"', login)
        update_uri = re.search(r'data-update-uri="([^\"]+)"', login)
        snapshots = [html.unescape(item) for item in re.findall(r'wire:snapshot="([^\"]+)"', login)]
        form = next((item for item in snapshots if json.loads(item)["memo"]["name"].endswith("Login")), None)
        if not csrf or not form or not update_uri:
            raise RuntimeError("Livewire login contract changed; update the authentication check")
        payload = json.dumps({"_token": html.unescape(csrf.group(1)), "components": [{
            "snapshot": form, "updates": {"data.email": "ci-admin@cachet.invalid", "data.password": password},
            "calls": [{"path": "", "method": "authenticate", "params": []}],
        }]}).encode()
        update_path = urllib.parse.urlparse(html.unescape(update_uri.group(1))).path
        if not update_path.startswith("/livewire") or not update_path.endswith("/update"):
            raise RuntimeError("Unexpected Livewire update path")
        request = urllib.request.Request(url + update_path, data=payload, headers={
            "Content-Type": "application/json", "Accept": "application/json", "X-Livewire": "true",
            "Origin": url, "Referer": url + "/dashboard/login",
        })
        response = json.loads(browser.open(request, timeout=20).read())
        redirect = response["components"][0]["effects"].get("redirect")
        if not redirect or urllib.parse.urlparse(redirect).path != "/dashboard":
            raise RuntimeError("Real administrator authentication failed")
        with browser.open(url + "/dashboard", timeout=20) as response:
            content = response.read().decode()
            if "/login" in response.url or "CI administrator" not in content:
                raise RuntimeError("Authenticated administrator dashboard failed")

    def refused_service(volume: str, mode: str) -> None:
        container = name + "-guard-" + mode
        command(["run", "--detach", "--name", container, *runtime(volume), args.image, mode])
        containers.append(container)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = json.loads(command(["inspect", container]).stdout)[0]["State"]
            if not state["Running"]:
                if state["ExitCode"] == 0:
                    raise RuntimeError("Service guard failure returned success: " + mode)
                command(["rm", container])
                containers.remove(container)
                return
            time.sleep(0.5)
        raise RuntimeError("Service started without explicit initialization: " + mode)

    try:
        candidate = new_volume("fresh")
        facts = json.loads(cli(args.image, candidate, "exec", "php", "-r",
            "$s=file_get_contents('/proc/self/status'); preg_match('/^Uid:\\s+(\\d+)/m',$s,$u); preg_match('/^CapEff:\\s+([a-f0-9]+)/m',$s,$c); echo json_encode(['uid'=>(int)$u[1],'cap_eff'=>$c[1],'pdo'=>PDO::getAvailableDrivers()]);").stdout)
        if facts["uid"] != 33 or int(facts["cap_eff"], 16) != 0 or not {"sqlite", "pgsql", "mysql"}.issubset(facts["pdo"]):
            raise RuntimeError("Runtime user/capability/PDO contract failed")
        cachet2_variables(candidate)
        results.append("cachet2_variable_names_mapped")
        for mode in ("web", "worker", "scheduler"):
            refused_service(candidate, mode)
        cli(args.image, candidate, "migrate")
        refused_service(candidate, "web")
        cli(args.image, candidate, "initialize")
        empty = snapshot(args.image, candidate)
        if empty["tables"]["users"]["count"] != 1 or empty["tables"]["components"]["count"] or empty["tables"]["incidents"]["count"]:
            raise RuntimeError("Fresh install contains demo data")
        results.append("fresh_install_without_demo_data")
        results.append("unmigrated_uninitialized_services_refused")
        before = snapshot(args.image, candidate, fixture=True)
        cli(args.image, candidate, "initialize")
        preserved(before, snapshot(args.image, candidate))
        # Lost marker must not permit reinitialization of an existing database.
        cli(args.image, candidate, "exec", "php", "-r", "unlink('/app/storage/app/cachet-initialized.json');")
        refused = cli(args.image, candidate, "initialize", check=False)
        if refused.returncode == 0:
            raise RuntimeError("Second initialize did not refuse the populated database")
        preserved(before, snapshot(args.image, candidate))
        cli(args.image, candidate, "migrate")
        preserved(before, snapshot(args.image, candidate))
        results.extend(["initialize_refuses_populated_database", "replayed_migration_preserves_data"])
        for _ in range(2):
            web, url = start(args.image, candidate)
            check_http(url)
            stop(web)
            preserved(before, snapshot(args.image, candidate))
        results.extend(["public_admin_assets_http", "real_administrator_login", "api_mcp_disabled", "nonroot_capabilities_dropped", "restart_preserves_data"])
        for mode in ("worker", "scheduler"):
            process, _ = start(args.image, candidate, mode)
            stop(process)
        preserved(before, snapshot(args.image, candidate))
        results.append("worker_scheduler_start_and_stop")
        if args.previous:
            cached_previous = command(["image", "inspect", args.previous], check=False)
            if cached_previous.returncode:
                command(["pull", args.previous])
            old = new_volume("upgrade")
            cli(args.previous, old, "migrate")
            cli(args.previous, old, "initialize")
            old_data = snapshot(args.previous, old, fixture=True)
            backup = command(["run", "--rm", "--user", "0", "--entrypoint", "tar",
                              "--volume", old + ":/data:ro", args.previous, "cf", "-", "-C", "/data", "."]).stdout
            cli(args.image, old, "migrate")
            preserved(old_data, snapshot(args.image, old))
            web, url = start(args.image, old)
            check_http(url)
            stop(web)
            restored = new_volume("restore")
            command(["run", "--rm", "--interactive", "--user", "0", "--entrypoint", "tar",
                     "--volume", restored + ":/app/storage", args.previous, "xf", "-", "-C", "/app/storage"], input_bytes=backup)
            preserved(old_data, snapshot(args.previous, restored))
            results.extend(["previous_image_database_upgrade", "snapshot_restore_with_previous_image"])
        else:
            results.append("first_publication_no_previous_image")
        args.report.parent.mkdir(exist_ok=True, parents=True)
        args.report.write_text(json.dumps({"image": args.image, "previous_image_tested": bool(args.previous),
                                          "checks": results, "passed": True}, indent=2) + "\n")
        print(json.dumps({"passed": True, "checks": results}, indent=2))
    except Exception as error:
        args.report.parent.mkdir(exist_ok=True, parents=True)
        args.report.write_text(json.dumps({"image": args.image, "previous_image_tested": bool(args.previous),
            "checks": results, "passed": False, "failure_type": type(error).__name__}, indent=2) + "\n")
        raise
    finally:
        for container in list(containers):
            command(["rm", "--force", container], check=False)
        for volume in volumes:
            command(["volume", "rm", volume], check=False)
        shutil.rmtree(workspace)


if __name__ == "__main__":
    main()
