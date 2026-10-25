#!/usr/bin/env python3
"""Exercise Cachet on a database server: install, migration, upgrade and snapshot restore."""

import argparse
import base64
import datetime
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
import uuid


ROOT = Path(__file__).resolve().parents[1]
OWNER_LABEL = "org.cachet-status.database-test"
CLIENT_CONFIG = "--defaults-extra-file=/run/secrets/client.cnf"
ENGINES = {
    "pgsql": {"label": "PostgreSQL", "image": "postgres:17-bookworm", "port": "5432",
              "data": "/var/lib/postgresql/data"},
    "mysql": {"label": "MySQL", "image": "mysql:8.4", "port": "3306", "data": "/var/lib/mysql",
              "client": "mysql", "dump": "mysqldump", "admin": "mysqladmin", "env_prefix": "MYSQL"},
    "mariadb": {"label": "MariaDB", "image": "mariadb:11.4", "port": "3306", "data": "/var/lib/mysql",
                "client": "mariadb", "dump": "mariadb-dump", "admin": "mariadb-admin", "env_prefix": "MARIADB"},
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--database", choices=sorted(ENGINES), default="pgsql")
    parser.add_argument("--previous", help="Previous application image as an immutable registry digest")
    parser.add_argument("--report", type=Path, help="Default: .build/database-<database>-test-report.json")
    args = parser.parse_args()
    if args.previous and not re.search(r"@sha256:[0-9a-f]{64}$", args.previous):
        parser.error("--previous must be an immutable registry digest")
    if not (ROOT / "test/fixture.php").is_file():
        parser.error("The checked-in test fixture helper is required")
    engine = ENGINES[args.database]
    label = engine["label"]
    postgres = args.database == "pgsql"
    report_path = args.report or ROOT / f".build/database-{args.database}-test-report.json"

    test_id = uuid.uuid4().hex
    prefix = f"cachet-{args.database}-ci-" + test_id[:12]
    (ROOT / ".test").mkdir(exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix=prefix + "-", dir=ROOT / ".test"))
    workspace.chmod(0o700)
    containers: list[str] = []
    volumes: list[str] = []
    networks: list[str] = []
    checks: list[str] = []
    notes: list[str] = []
    database_id: str | None = None
    network_id: str | None = None
    database_image_id: str | None = None
    failure: BaseException | None = None
    cleanup_errors: list[str] = []
    passed = False
    sequence = 0

    key = "base64:" + base64.b64encode(secrets.token_bytes(32)).decode()
    admin_password = secrets.token_urlsafe(36)
    database_password = secrets.token_urlsafe(36)
    root_password = secrets.token_urlsafe(36)
    application_secrets = {
        "key": key,
        "email": "ci-admin@cachet.invalid",
        "password": admin_password,
        "database-password": database_password,
    }
    server_secrets = {"database-password": database_password}
    if not postgres:
        server_secrets["root-password"] = root_password
        server_secrets["client.cnf"] = "\n".join([
            "[client]", "user=root", "password=" + root_password, "host=127.0.0.1", "protocol=tcp",
        ])
    for filename, value in {**application_secrets, **server_secrets}.items():
        path = workspace / filename
        path.write_text(value + "\n")
        # The parent 0700 directory protects these files on the host. Docker mounts
        # each individual file, which must be readable by application UID 33.
        path.chmod(0o444)
    environment = workspace / "runtime.env"
    environment.write_text("\n".join([
        "APP_ENV=production", "APP_DEBUG=false", "APP_URL=http://localhost",
        f"APP_NAME=Cachet {label} CI", "APP_KEY_FILE=/run/secrets/key",
        "ADMIN_EMAIL_FILE=/run/secrets/email", "ADMIN_PASSWORD_FILE=/run/secrets/password",
        "ADMIN_NAME=CI administrator", f"DB_CONNECTION={args.database}", "DB_HOST=database",
        f"DB_PORT={engine['port']}", "DB_USERNAME=cachet", "DB_PASSWORD_FILE=/run/secrets/database-password",
        "SESSION_SECURE_COOKIE=false", "MAIL_MAILER=log", "CACHE_STORE=database",
        "QUEUE_CONNECTION=database", "CACHET_DEMO_MODE=false", "CACHET_BEACON=false",
        "CACHET_FEED_URI=", "NIGHTWATCH_ENABLED=false",
    ]) + "\n")
    environment.chmod(0o600)
    private_values = (admin_password, database_password, root_password, key, key.removeprefix("base64:"))

    def redact(value: str) -> str:
        for secret in private_values:
            value = value.replace(secret, "[redacted]")
        return value

    def command(arguments: list[str], *, check: bool = True,
                input_bytes: bytes | None = None, timeout: int = 300) -> subprocess.CompletedProcess:
        completed = subprocess.run(["docker", *arguments], input=input_bytes,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        if check and completed.returncode:
            # Archive stdout is binary and can contain DB values; never quote it.
            stderr = redact(completed.stderr.decode(errors="replace"))
            raise RuntimeError(f"Docker {arguments[0]} failed ({completed.returncode}): {stderr[-4000:]}")
        return completed

    def owned(kind: str, identifier: str) -> bool:
        arguments = ["inspect", identifier] if kind == "container" else [kind, "inspect", identifier]
        result = command(arguments, check=False, timeout=30)
        if result.returncode:
            return False
        metadata = json.loads(result.stdout)[0]
        labels = metadata.get("Config", {}).get("Labels", {}) if kind == "container" else metadata.get("Labels", {})
        return (labels or {}).get(OWNER_LABEL) == test_id

    def create_volume(suffix: str) -> str:
        name = prefix + "-" + suffix
        if command(["volume", "inspect", name], check=False).returncode == 0:
            raise RuntimeError("A proposed test volume already exists; refusing to reuse it")
        command(["volume", "create", "--label", OWNER_LABEL + "=" + test_id, name])
        if not owned("volume", name):
            raise RuntimeError("The created volume does not carry this test's ownership label")
        volumes.append(name)
        return name

    def create_container(image: str, options: list[str], *mode: str) -> str:
        nonlocal sequence
        sequence += 1
        name = prefix + "-" + str(sequence)
        result = command(["create", "--name", name, "--label", OWNER_LABEL + "=" + test_id,
                          *options, image, *mode])
        identifier = result.stdout.decode().strip()
        containers.append(identifier)
        if not owned("container", identifier):
            raise RuntimeError("The created container does not carry this test's ownership label")
        return identifier

    def mounts(filenames) -> list[str]:
        options = []
        for filename in filenames:
            options.extend(["--mount", f"type=bind,src={workspace / filename},dst=/run/secrets/{filename},readonly"])
        return options

    def application_options(volume: str, database: str) -> list[str]:
        if not network_id:
            raise RuntimeError("The isolated test network is not available")
        options = ["--network", network_id, "--env-file", str(environment),
                   "--env", "DB_DATABASE=" + database, "--volume", volume + ":/app/storage",
                   "--user", "33:33", "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
                   "--memory=512m", "--cpus=1.0", *mounts(application_secrets)]
        options.extend(["--mount", f"type=bind,src={ROOT / 'test/fixture.php'},dst=/test/fixture.php,readonly"])
        return options

    def database_exec(*arguments: str, input_bytes: bytes | None = None, check: bool = True) -> subprocess.CompletedProcess:
        interactive = ["--interactive"] if input_bytes is not None else []
        return command(["exec", *interactive, database_id, *arguments], input_bytes=input_bytes, check=check)

    def server_ready() -> bool:
        # Initialization-only servers accept local sockets only; require TCP
        # readiness so application containers never race that temporary server.
        if postgres:
            probe = ["pg_isready", "--host=127.0.0.1", "--username=cachet", "--dbname=cachet_fresh"]
        else:
            probe = [engine["admin"], CLIENT_CONFIG, "ping"]
        return database_exec(*probe, check=False).returncode == 0

    def create_database(name: str) -> None:
        if postgres:
            database_exec("createdb", "--username=cachet", "--owner=cachet", name)
        else:
            database_exec(engine["client"], CLIENT_CONFIG, "--execute",
                          f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
                          f" GRANT ALL PRIVILEGES ON `{name}`.* TO 'cachet'@'%';")

    def dump_database(name: str) -> bytes:
        if postgres:
            dump = database_exec("pg_dump", "--username=cachet", "--dbname=" + name,
                                 "--format=custom", "--no-owner", "--no-acl").stdout
            complete = dump.startswith(b"PGDMP")
        else:
            dump = database_exec(engine["dump"], CLIENT_CONFIG, "--single-transaction", "--hex-blob",
                                 "--no-tablespaces", "--routines", name).stdout
            complete = b"CREATE TABLE" in dump
        if not complete:
            raise RuntimeError(f"The {label} dump is incomplete")
        return dump

    def restore_database(name: str, dump: bytes) -> None:
        if postgres:
            database_exec("pg_restore", "--exit-on-error", "--no-owner", "--no-acl",
                          "--username=cachet", "--dbname=" + name, input_bytes=dump)
        else:
            database_exec(engine["client"], CLIENT_CONFIG, name, input_bytes=dump)

    def check_no_secret_logs(identifier: str) -> None:
        result = command(["logs", identifier], check=False)
        content = result.stdout + result.stderr
        if any(value.encode() in content for value in private_values[:4]):
            raise RuntimeError("A generated private test credential appeared in container logs")

    def remove_container(identifier: str) -> None:
        if not owned("container", identifier):
            raise RuntimeError("Refusing to remove a container without this test's ownership label")
        command(["rm", "--force", identifier], timeout=90)
        containers.remove(identifier)

    def cli(image: str, volume: str, database: str, *mode: str) -> bytes:
        identifier = create_container(image, application_options(volume, database), *mode)
        result = command(["start", "--attach", identifier], check=False)
        state = json.loads(command(["inspect", identifier]).stdout)[0]["State"]
        logs = command(["logs", identifier], check=False)
        check_no_secret_logs(identifier)
        if result.returncode or state["Running"] or state["ExitCode"] != 0:
            raise RuntimeError("Application CLI refused or failed: " + redact(logs.stderr.decode(errors="replace"))[-4000:])
        remove_container(identifier)
        return logs.stdout

    def snapshot(image: str, volume: str, database: str, *, fixture: bool = False) -> dict:
        stdout = cli(image, volume, database, "exec", "php", "/test/fixture.php",
                     "fixture" if fixture else "snapshot")
        return json.loads(stdout.decode().strip().splitlines()[-1])

    def preserved(before: dict, after: dict) -> None:
        if before["tables"] != after["tables"] or before["upload_sha256"] != after["upload_sha256"]:
            raise RuntimeError(f"{label} account/component/incident or upload was not preserved")
        for setting, value in before["settings"].items():
            if after["settings"].get(setting) != value:
                raise RuntimeError(f"An existing {label}-backed setting changed: " + setting)

    def checked(name: str) -> None:
        checks.append(name)
        print(f"{label} check passed: " + name, flush=True)

    def check_web(image: str, volume: str, database: str) -> None:
        identifier = create_container(image, [*application_options(volume, database),
                                             "--publish", "127.0.0.1::8000"], "web")
        command(["start", identifier])
        metadata = json.loads(command(["inspect", identifier]).stdout)[0]
        binding = metadata["NetworkSettings"]["Ports"].get("8000/tcp")
        if not binding or binding[0]["HostIp"] != "127.0.0.1":
            raise RuntimeError("Application HTTP did not publish only on loopback")
        url = "http://127.0.0.1:" + binding[0]["HostPort"]
        deadline = time.monotonic() + 90
        ready = False
        while time.monotonic() < deadline:
            state = json.loads(command(["inspect", identifier]).stdout)[0]["State"]
            if not state["Running"]:
                raise RuntimeError(f"{label}-backed web process exited before readiness")
            try:
                with urllib.request.urlopen(url + "/up", timeout=3) as response:
                    if response.status == 200:
                        ready = True
                        break
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                time.sleep(1)
        if not ready:
            raise RuntimeError(f"{label}-backed HTTP readiness timed out")
        with urllib.request.urlopen(url + "/", timeout=20) as response:
            if response.status != 200:
                raise RuntimeError(f"{label}-backed public page did not return 200")
            response.read()
        try:
            with urllib.request.urlopen(url + "/api/components", timeout=15) as response:
                response.read()
            raise RuntimeError(f"Disabled {label}-backed API answered successfully")
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise RuntimeError(f"Disabled {label}-backed API did not return 404") from error
        command(["stop", "--time=30", identifier], timeout=45)
        check_no_secret_logs(identifier)
        remove_container(identifier)

    def archive_storage(image: str, volume: str) -> bytes:
        identifier = create_container(image, [
            "--network=none", "--user=0", "--entrypoint=tar",
            "--volume", volume + ":/data:ro",
        ], "cf", "-", "-C", "/data", ".")
        result = command(["start", "--attach", identifier], check=False)
        state = json.loads(command(["inspect", identifier]).stdout)[0]["State"]
        if result.returncode or state["Running"] or state["ExitCode"] != 0:
            raise RuntimeError("Archiving the owned application storage failed")
        remove_container(identifier)
        # Binary archives must come from attach, never from a text log driver.
        return result.stdout

    def restore_storage(image: str, volume: str, archive: bytes) -> None:
        identifier = create_container(image, [
            "--interactive", "--network=none", "--user=0", "--entrypoint=tar",
            "--volume", volume + ":/app/storage",
        ], "xf", "-", "-C", "/app/storage")
        result = command(["start", "--attach", "--interactive", identifier],
                         input_bytes=archive, check=False)
        state = json.loads(command(["inspect", identifier]).stdout)[0]["State"]
        if result.returncode or state["Running"] or state["ExitCode"] != 0:
            raise RuntimeError("Restoring the owned application storage failed")
        remove_container(identifier)

    try:
        docker_host = os.environ.get("DOCKER_HOST")
        if docker_host and not docker_host.startswith(("unix://", "npipe://")):
            raise RuntimeError("Database integration tests require a local Docker endpoint")
        context = json.loads(command(["context", "inspect"]).stdout)[0]
        if not context["Endpoints"]["docker"]["Host"].startswith(("unix://", "npipe://")):
            raise RuntimeError("Database integration tests require a local Docker context")
        command(["image", "inspect", args.image])
        command(["pull", engine["image"]], timeout=600)
        if args.previous:
            command(["pull", args.previous], timeout=600)
        database_image_id = json.loads(command(["image", "inspect", engine["image"]]).stdout)[0]["Id"]

        result = command(["network", "create", "--label", OWNER_LABEL + "=" + test_id, prefix + "-net"])
        network_id = result.stdout.decode().strip()
        if not owned("network", network_id):
            raise RuntimeError("The created network does not carry this test's ownership label")
        networks.append(network_id)
        if postgres:
            server_environment = ["POSTGRES_USER=cachet", "POSTGRES_DB=cachet_fresh",
                                  "POSTGRES_PASSWORD_FILE=/run/secrets/database-password"]
        else:
            variable = engine["env_prefix"]
            server_environment = [f"{variable}_ROOT_PASSWORD_FILE=/run/secrets/root-password",
                                  f"{variable}_USER=cachet", f"{variable}_DATABASE=cachet_fresh",
                                  f"{variable}_PASSWORD_FILE=/run/secrets/database-password"]
        database_id = create_container(engine["image"], [
            "--network", network_id, "--network-alias", "database",
            *(item for value in server_environment for item in ("--env", value)),
            *mounts(server_secrets),
            "--volume", create_volume("server") + ":" + engine["data"], "--memory=1g", "--cpus=1.0",
        ])
        command(["start", database_id])
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            state = json.loads(command(["inspect", database_id]).stdout)[0]["State"]
            if not state["Running"]:
                raise RuntimeError(f"The disposable {label} server exited before readiness")
            if server_ready():
                break
            time.sleep(1)
        else:
            raise RuntimeError(f"The disposable {label} server was not ready")
        published = json.loads(command(["inspect", database_id]).stdout)[0]["NetworkSettings"]["Ports"]
        if any(bindings for bindings in published.values()):
            raise RuntimeError("The disposable database unexpectedly published a host port")
        checked("database_isolated_without_published_port")

        fresh = create_volume("fresh-storage")
        cli(args.image, fresh, "cachet_fresh", "migrate")
        cli(args.image, fresh, "cachet_fresh", "initialize")
        empty = snapshot(args.image, fresh, "cachet_fresh")
        if empty["tables"]["users"]["count"] != 1 or empty["tables"]["components"]["count"] or empty["tables"]["incidents"]["count"]:
            raise RuntimeError(f"Fresh {label} installation contains unexpected demonstration records")
        checked("fresh_install_without_demo_data")
        baseline = snapshot(args.image, fresh, "cachet_fresh", fixture=True)
        cli(args.image, fresh, "cachet_fresh", "initialize")
        preserved(baseline, snapshot(args.image, fresh, "cachet_fresh"))
        checked("initialize_idempotent")
        cli(args.image, fresh, "cachet_fresh", "migrate")
        preserved(baseline, snapshot(args.image, fresh, "cachet_fresh"))
        checked("replayed_migration_preserves_accounts_settings_and_uploads")
        check_web(args.image, fresh, "cachet_fresh")
        preserved(baseline, snapshot(args.image, fresh, "cachet_fresh"))
        checked("public_http_and_disabled_api")

        if args.previous:
            create_database("cachet_upgrade")
            old_volume = create_volume("previous-storage")
            cli(args.previous, old_volume, "cachet_upgrade", "migrate")
            cli(args.previous, old_volume, "cachet_upgrade", "initialize")
            old = snapshot(args.previous, old_volume, "cachet_upgrade", fixture=True)
            database_backup = dump_database("cachet_upgrade")
            storage_backup = archive_storage(args.previous, old_volume)
            if not storage_backup:
                raise RuntimeError("The storage snapshot is empty")
            cli(args.image, old_volume, "cachet_upgrade", "migrate")
            preserved(old, snapshot(args.image, old_volume, "cachet_upgrade"))
            check_web(args.image, old_volume, "cachet_upgrade")
            preserved(old, snapshot(args.image, old_volume, "cachet_upgrade"))
            checked("previous_image_upgrade_preserves_data")
            create_database("cachet_restore")
            restored = create_volume("restored-storage")
            restore_database("cachet_restore", database_backup)
            restore_storage(args.previous, restored, storage_backup)
            preserved(old, snapshot(args.previous, restored, "cachet_restore"))
            checked("dump_and_storage_restored_for_previous_image")
        else:
            notes.append("No previous digest supplied; cross-version upgrade and snapshot restore were not exercised.")
        check_no_secret_logs(database_id)
        checked("generated_credentials_absent_from_container_logs")
        passed = True
    except BaseException as error:
        failure = error
    finally:
        for identifier in reversed(containers):
            try:
                if owned("container", identifier):
                    command(["rm", "--force", identifier], timeout=90)
                else:
                    cleanup_errors.append("Container ownership could not be confirmed: " + identifier)
            except Exception as error:
                cleanup_errors.append("Container cleanup failed: " + type(error).__name__)
        for volume in reversed(volumes):
            try:
                if owned("volume", volume):
                    command(["volume", "rm", volume], timeout=90)
                else:
                    cleanup_errors.append("Volume ownership could not be confirmed: " + volume)
            except Exception as error:
                cleanup_errors.append("Volume cleanup failed: " + type(error).__name__)
        for identifier in reversed(networks):
            try:
                if owned("network", identifier):
                    command(["network", "rm", identifier], timeout=90)
                else:
                    cleanup_errors.append("Network ownership could not be confirmed: " + identifier)
            except Exception as error:
                cleanup_errors.append("Network cleanup failed: " + type(error).__name__)
        if cleanup_errors:
            passed = False
            if failure is None:
                failure = RuntimeError("One or more owned test resources could not be cleaned up")
        report = {
            "image": args.image, "previous": args.previous, "database": args.database,
            "database_image": engine["image"], "database_image_id": database_image_id,
            "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "checks": checks, "notes": notes, "passed": passed, "cleanup_complete": not cleanup_errors,
        }
        if failure is not None:
            report["failure_type"] = type(failure).__name__
        if cleanup_errors:
            report["cleanup_errors"] = cleanup_errors
        report_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(report_path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(json.dumps(report, indent=2) + "\n")
        report_path.chmod(0o600)
        shutil.rmtree(workspace)
    if failure is not None:
        raise RuntimeError(f"{label} integration checks failed; inspect the private report.") from failure
    print(json.dumps({"passed": True, "database": args.database, "checks": checks, "notes": notes}, indent=2))


if __name__ == "__main__":
    main()
