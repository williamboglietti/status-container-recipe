"""Tests for the private GHCR publication guard."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("private_image", ROOT / "scripts/private_image.py")
PRIVATE_IMAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PRIVATE_IMAGE)


class PrivatePackageGuard(unittest.TestCase):
    def test_only_private_unlinked_packages_are_accepted(self):
        self.assertTrue(PRIVATE_IMAGE.private_unlinked_package({"visibility": "private"}))
        self.assertFalse(PRIVATE_IMAGE.private_unlinked_package({"visibility": "public"}))
        self.assertFalse(PRIVATE_IMAGE.private_unlinked_package({
            "visibility": "private", "repository": {"full_name": "williamboglietti/status-v3"},
        }))
        self.assertFalse(PRIVATE_IMAGE.private_unlinked_package(None))

    def test_previous_digest_requires_both_linux_architectures(self):
        digest = "sha256:" + "a" * 64
        manifest = {"manifests": [
            {"platform": {"os": "linux", "architecture": "amd64"}},
            {"platform": {"os": "linux", "architecture": "arm64"}},
        ]}
        self.assertEqual(
            PRIVATE_IMAGE.multiarch_reference("ghcr.io/williamboglietti/status-v3", manifest, digest),
            "ghcr.io/williamboglietti/status-v3@" + digest,
        )
        amd_only = {"manifests": [{"platform": {"os": "linux", "architecture": "amd64"}}]}
        self.assertIsNone(PRIVATE_IMAGE.multiarch_reference("ghcr.io/williamboglietti/status-v3", amd_only, digest))
        self.assertIsNone(PRIVATE_IMAGE.multiarch_reference("ghcr.io/williamboglietti/status-v3", manifest, "latest"))

    def test_missing_publisher_secret_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            summary = Path(temporary) / "summary"
            environment = {
                "STATUS_V3_PRIVATE_IMAGE_ENABLED": "true",
                "STATUS_V3_GHCR_TOKEN": "",
                "GITHUB_OUTPUT": str(output),
                "GITHUB_STEP_SUMMARY": str(summary),
            }
            with patch.dict(os.environ, environment, clear=True):
                PRIVATE_IMAGE.prepare()
            self.assertIn("publish_enabled=false", output.read_text())
            self.assertIn("secret is missing", summary.read_text())


if __name__ == "__main__":
    unittest.main()
