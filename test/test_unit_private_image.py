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
    @staticmethod
    def workflow_step(workflow, name):
        start = workflow.index(f"      - name: {name}")
        end = workflow.find("\n      - name:", start + 1)
        if end < 0:
            end = workflow.find("\n  record-locks:", start + 1)
        return workflow[start:end if end >= 0 else None]

    def test_candidate_push_uses_the_configured_private_image(self):
        workflow = (ROOT / ".github/workflows/image.yml").read_text()
        self.assertIn('candidate="$PRIVATE_IMAGE:candidate-', workflow)
        self.assertNotIn('candidate="$IMAGE:candidate-', workflow)

    def test_only_private_unlinked_packages_are_accepted(self):
        self.assertTrue(PRIVATE_IMAGE.private_unlinked_package({"visibility": "private"}))
        self.assertFalse(PRIVATE_IMAGE.private_unlinked_package({"visibility": "public"}))
        self.assertFalse(PRIVATE_IMAGE.private_unlinked_package({
            "visibility": "private", "repository": {"full_name": "williamboglietti/status-v3"},
        }))
        self.assertFalse(PRIVATE_IMAGE.private_unlinked_package(None))

    def test_previous_digest_requires_linux_amd64_but_not_suspended_arm64(self):
        digest = "sha256:" + "a" * 64
        manifest = {"manifests": [
            {"platform": {"os": "linux", "architecture": "amd64"}},
            {"platform": {"os": "linux", "architecture": "arm64"}},
        ]}
        self.assertEqual(
            PRIVATE_IMAGE.amd64_reference("ghcr.io/williamboglietti/status-v3", manifest, digest),
            "ghcr.io/williamboglietti/status-v3@" + digest,
        )
        amd_only = {"manifests": [{"platform": {"os": "linux", "architecture": "amd64"}}]}
        self.assertEqual(
            PRIVATE_IMAGE.amd64_reference("ghcr.io/williamboglietti/status-v3", amd_only, digest),
            "ghcr.io/williamboglietti/status-v3@" + digest,
        )
        arm_only = {"manifests": [{"platform": {"os": "linux", "architecture": "arm64"}}]}
        self.assertIsNone(PRIVATE_IMAGE.amd64_reference("ghcr.io/williamboglietti/status-v3", arm_only, digest))
        self.assertIsNone(PRIVATE_IMAGE.amd64_reference("ghcr.io/williamboglietti/status-v3", manifest, "latest"))

    def test_missing_private_package_disables_publishing_without_bootstrap_push(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            summary = Path(temporary) / "summary"
            environment = {
                "STATUS_V3_GHCR_TOKEN": "read-write-token",
                "STATUS_V3_GHCR_USERNAME": "williamboglietti",
                "GITHUB_OUTPUT": str(output),
                "GITHUB_STEP_SUMMARY": str(summary),
            }
            with patch.dict(os.environ, environment, clear=True), \
                    patch.object(PRIVATE_IMAGE, "github_package", return_value=None), \
                    patch.object(PRIVATE_IMAGE, "latest_amd64_reference") as latest_reference:
                PRIVATE_IMAGE.prepare()
            self.assertIn("publish_enabled=false", output.read_text())
            self.assertIn("does not exist", summary.read_text())
            latest_reference.assert_not_called()

    def test_scan_policy_runs_both_severity_steps_without_unfixed_filter(self):
        workflow = (ROOT / ".github/workflows/image.yml").read_text()
        self.assertIn("severity: MEDIUM,LOW", workflow)
        self.assertIn("severity: HIGH,CRITICAL", workflow)
        self.assertNotIn("ignore-unfixed", workflow)
        self.assertNotIn("ubuntu-24.04-arm", workflow)

    def test_registry_writes_are_explicitly_main_only(self):
        workflow = (ROOT / ".github/workflows/image.yml").read_text()
        self.assertIn("if: github.ref == 'refs/heads/main' && needs.resolve.outputs.build_required == 'true'", workflow)
        private_package = workflow[workflow.index("  private-package:"):workflow.index("  build-test:")]
        self.assertIn("github.ref == 'refs/heads/main'", private_package)
        publisher = workflow[workflow.index("  publish-private-image:"):]
        self.assertIn("github.ref == 'refs/heads/main'", publisher)
        for name in (
            "Log in to pull the previous private image",
            "Pull the previous image for migration tests",
            "Log in to publish the tested private candidate",
            "Push exactly the locally tested image",
            "Share the tested candidate digest",
        ):
            with self.subTest(step=name):
                self.assertIn("if: github.ref == 'refs/heads/main'", self.workflow_step(workflow, name))

    def test_missing_publisher_secret_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            summary = Path(temporary) / "summary"
            environment = {
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
