#!/usr/bin/env python3
"""Print the Docker build arguments recorded in sources.lock.json, one KEY=VALUE per line."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def build_arguments(root: Path = ROOT) -> dict[str, str]:
    """Return arguments as values, without shell quoting or word splitting."""
    lock = json.loads((root / "sources.lock.json").read_text())
    images = lock["images"]
    try:
        revision = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
                                  capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        revision = "local"
    return {
        "FRANKENPHP_IMAGE": images["frankenphp"]["tag"] + "@" + images["frankenphp"]["digest"],
        "COMPOSER_IMAGE": images["composer"]["tag"] + "@" + images["composer"]["digest"],
        "CACHET_APP_REF": lock["app"]["commit"],
        "CACHET_CORE_REF": lock["core"]["commit"],
        "SOURCE_FINGERPRINT": lock["fingerprint"],
        "BUILD_REVISION": revision,
    }

def main() -> None:
    for name, value in build_arguments().items():
        print(f"{name}={value}")


if __name__ == "__main__":
    main()
