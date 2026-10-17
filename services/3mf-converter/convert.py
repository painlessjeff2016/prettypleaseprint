#!/usr/bin/env python3
"""Isolated 3MF-to-AD5X adapter. No PPP database or web access.

Usage:
  python3 services/3mf-converter/convert.py /work/input.3mf /work/result \
      --template /templates/ad5x.3mf --engine /engine/bambu2ad5x.py

Writes result/converted.3mf and result/conversion.report.txt on success.
Output is only published after validation. Never touches the source archive.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

MAX_INPUT = 250 * 1024 * 1024
MAX_UNCOMPRESSED = 1024 * 1024 * 1024
MAX_MEMBERS = 20_000
MAX_RATIO = 200


def check_archive(path: Path) -> None:
    if not path.is_file() or path.suffix.lower() != ".3mf":
        raise ValueError("Input must be a .3mf file")
    if path.stat().st_size > MAX_INPUT:
        raise ValueError("Archive exceeds 250 MiB")
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_MEMBERS:
            raise ValueError("Archive contains too many entries")
        total = 0
        for entry in entries:
            total += entry.file_size
            if total > MAX_UNCOMPRESSED:
                raise ValueError("Archive uncompressed size exceeds limit")
            if entry.file_size and entry.file_size / max(1, entry.compress_size) > MAX_RATIO:
                raise ValueError("Archive compression ratio exceeds limit")
        if "[Content_Types].xml" not in archive.namelist():
            raise ValueError("Archive is missing 3MF content types")


def convert(src: Path, destination: Path, template: Path, engine: Path, timeout: int) -> None:
    if not template.is_file() or template.suffix.lower() not in (".3mf", ".json"):
        raise ValueError("Custom AD5X template (.3mf or .json) is required")
    if not engine.is_file():
        raise ValueError("Converter engine not found")
    check_archive(src)
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ppp-3mf-") as tmp:
        temporary = Path(tmp)
        output = temporary / "converted.3mf"
        result = subprocess.run(
            [sys.executable, str(engine), str(src), "--template", str(template),
             "--output", str(output), "--report"],
            cwd=str(temporary), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=timeout, check=False,
        )
        if result.returncode:
            raise RuntimeError(f"converter failed ({result.returncode}): {result.stderr[-2000:]}")
        report = Path(str(output) + ".report.txt")
        if not output.is_file() or not report.is_file():
            raise RuntimeError("converter did not produce both requested artifacts")
        check_archive(output)
        # Destination is a job-specific directory. Fail rather than replace artifacts.
        for name in ("converted.3mf", "conversion.report.txt"):
            if (destination / name).exists():
                raise FileExistsError(f"artifact already exists: {name}")
        # Move completed artifacts from temporary workspace, never modify src.
        os.replace(output, destination / "converted.3mf")
        os.replace(report, destination / "conversion.report.txt")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 900:
        parser.error("--timeout must be between 1 and 900 seconds")
    try:
        convert(args.input.resolve(), args.destination.resolve(),
                args.template.resolve(), args.engine.resolve(), args.timeout)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, zipfile.BadZipFile) as exc:
        print(f"3MF conversion failed: {exc}", file=sys.stderr)
        return 1
    print("3MF conversion completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
