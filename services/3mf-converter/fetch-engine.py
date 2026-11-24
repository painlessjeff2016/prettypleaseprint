#!/usr/bin/env python3
"""Fetch the verified 3MF-to-AD5X fork at image *build* time only.

The immutable revision and SHA-256 checksums are deliberate: never execute a
moving upstream branch in a production conversion worker. A new revision
requires an explicit review and checksum update.

Converter source: https://github.com/painlessjeff2016/3MF-to-AD5X
License: MIT (the matching LICENSE is bundled in the image).
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
from urllib.request import urlopen

SOURCE_REPO = "painlessjeff2016/3MF-to-AD5X"
REVISION = "153f8a80040a24a585b9986d27f6c0a8341f02a4"
SHA256 = {
    "bambu2ad5x.py": "ec16a434e576bd41c2e1d4f61f8342cbe9d68829a71b39d09b39679df84645f8",
    "ad5x_template.json": "850175cdf2ade9375b6a9ab9550f11f11cc7e149a6f75702cc70c47ea79b00f1",
    "LICENSE": "9792c3346386090c9912c1650951afadf098ec031ab59b1b65b79a29439a03e4",
}


def install(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name, digest in SHA256.items():
        url = f"https://raw.githubusercontent.com/{SOURCE_REPO}/{REVISION}/{name}"
        with urlopen(url, timeout=60) as response:
            data = response.read()
        actual = hashlib.sha256(data).hexdigest()
        if actual != digest:
            raise RuntimeError(f"{name}: pinned SHA-256 mismatch (expected {digest}, got {actual})")
        (destination / name).write_bytes(data)
        print(f"verified {SOURCE_REPO}@{REVISION[:12]}/{name}: {digest}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: fetch-engine.py OUTPUT_DIRECTORY")
    install(Path(sys.argv[1]).resolve())
