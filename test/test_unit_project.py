"""Regressions for local argument handling and reproducible recipe fingerprints."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROJECT = load_module("project", "project.py")
RESOLVE = load_module("resolve", "resolve.py")


class LocalCommands(unittest.TestCase):
    def test_build_preserves_each_environment_value_as_one_argument(self):
        image = "example.invalid/image:tag; $(touch NEVER)"
        target_platform = "linux/arm64; $(touch NEVER)"
        with patch.dict(os.environ, {"IMAGE": image, "PLATFORM": target_platform}), \
                patch.object(PROJECT, "run") as run, \
                patch.object(PROJECT.BUILD_ARGS, "build_arguments", return_value={"VALUE": "one two;$HOME"}):
            PROJECT.execute("build")
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args.args[0], [
            "docker", "buildx", "build", "--load", "--platform", target_platform,
            "--tag", image, "--build-arg", "VALUE=one two;$HOME", ".",
        ])

    def test_run_uses_subprocess_without_a_shell(self):
        arguments = ["docker", "image", "$(touch NEVER)"]
        with patch.object(PROJECT.subprocess, "run") as run:
            PROJECT.run(arguments)
        run.assert_called_once_with(arguments, cwd=PROJECT.ROOT, check=True)

    def test_healthcheck_keeps_image_and_platform_arguments(self):
        with patch.dict(os.environ, {"IMAGE": "tag with spaces", "PLATFORM": "linux/arm64"}), \
                patch.object(PROJECT, "run") as run:
            PROJECT.execute("test-healthcheck")
        self.assertEqual(run.call_args.args[0][-4:], ["--image", "tag with spaces", "--platform", "linux/arm64"])

    def test_database_targets_select_their_backend(self):
        for backend in ("pgsql", "mysql", "mariadb"):
            with self.subTest(backend=backend), patch.object(PROJECT, "run") as run:
                PROJECT.execute("test-" + backend)
                self.assertEqual(run.call_args.args[0][-2:], ["--database", backend])

    def test_native_architecture_aliases(self):
        for architecture, expected in (("x86_64", "linux/amd64"), ("aarch64", "linux/arm64"), ("arm64", "linux/arm64")):
            with self.subTest(architecture=architecture), patch.object(PROJECT.platform, "machine", return_value=architecture):
                self.assertEqual(PROJECT.native_platform(), expected)

    def test_secrets_preserve_literal_email_and_existing_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            email = "o'connor+$(touch NEVER)@example.com"
            PROJECT.create_secrets(root, email)
            directory = root / ".secrets"
            before = {path.name: path.read_bytes() for path in directory.iterdir()}
            PROJECT.create_secrets(root, "different@example.com")
            self.assertEqual((directory / "admin-email").read_text(), email)
            self.assertEqual({path.name: path.read_bytes() for path in directory.iterdir()}, before)
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((directory / "app-key").stat().st_mode), 0o444)
            self.assertFalse((root / "NEVER").exists())

    def test_secret_mount_permissions_do_not_depend_on_umask(self):
        with tempfile.TemporaryDirectory() as temporary:
            previous = os.umask(0o077)
            try:
                PROJECT.create_secrets(Path(temporary), "admin@example.com")
            finally:
                os.umask(previous)
            for path in (Path(temporary) / ".secrets").iterdir():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)

    def test_make_passes_environment_values_without_shell_interpolation(self):
        with tempfile.TemporaryDirectory() as temporary:
            shim = Path(temporary) / "python3"
            shim.write_text(
                "#!" + sys.executable + "\nimport json,os\n"
                "print(json.dumps({key:os.environ[key] for key in ('IMAGE','PLATFORM','ADMIN_EMAIL')}))\n"
            )
            shim.chmod(0o755)
            values = {"IMAGE": "tag; ' $(touch NEVER)", "PLATFORM": "linux/arm64", "ADMIN_EMAIL": "o'connor@example.com"}
            environment = {**os.environ, **values, "PATH": temporary + os.pathsep + os.environ["PATH"]}
            result = subprocess.run(["make", "--no-print-directory", "build"], cwd=ROOT,
                                    env=environment, capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout.splitlines()[-1]), values)


class RecipeFingerprint(unittest.TestCase):
    def test_python_caches_do_not_change_fingerprint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Dockerfile").write_text("FROM example\n")
            for folder in ("docker", "scripts", "test"):
                (root / folder).mkdir()
            source = root / "test/test_example.py"
            source.write_text("print('source')\n")
            before = RESOLVE.recipe_hash(root)
            for folder in ("scripts", "test"):
                cache = root / folder / "__pycache__"
                cache.mkdir()
                (cache / "example.cpython-314.pyc").write_bytes(b"generated cache")
                (root / folder / "loose.pyc").write_bytes(b"generated cache")
                (root / folder / "loose.pyo").write_bytes(b"generated cache")
            self.assertEqual(RESOLVE.recipe_hash(root), before)
            source.write_text("print('changed source')\n")
            self.assertNotEqual(RESOLVE.recipe_hash(root), before)


if __name__ == "__main__":
    unittest.main()
