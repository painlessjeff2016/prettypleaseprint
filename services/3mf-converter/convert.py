#!/usr/bin/env python3
"""Isolated 3MF-to-AD5X adapter. No PPP database or web access.

Usage:
  python3 services/3mf-converter/convert.py /work/input.3mf /work/result \
      --engine /engine/bambu2ad5x.py

Writes result/converted.3mf and result/conversion.report.txt on success.
Output is only published after validation. Never touches the source archive.
"""
from __future__ import annotations

import argparse
import os
import shutil
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


def convert(src: Path, destination: Path, engine: Path, timeout: int) -> None:
    if not engine.is_file():
        raise ValueError("Converter engine not found")
    if not (engine.parent / "ad5x_template.json").is_file():
        raise ValueError("Bundled ad5x_template.json must be beside the engine")
    check_archive(src)
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ppp-3mf-") as tmp:
        temporary = Path(tmp)
        output = temporary / "converted.3mf"
        result = subprocess.run(
            [sys.executable, str(engine), str(src),
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
        # /tmp is tmpfs, but /work is a bind mount. os.replace() across
        # these filesystems raises EXDEV. First stage *both* complete files
        # under the destination mount, then rename them within that mount.
        # Staging files aren't exposed as finished artifacts.
        artifacts = ((output, "converted.3mf"),
                     (report, "conversion.report.txt"))
        with tempfile.TemporaryDirectory(prefix=".ppp-stage-", dir=destination) as stage_dir:
            stage = Path(stage_dir)
            for source, name in artifacts:
                staged = stage / name
                shutil.copyfile(source, staged)
                with staged.open("rb") as handle:
                    os.fsync(handle.fileno())

            published = []
            try:
                for _, name in artifacts:
                    final = destination / name
                    # Job-specific output directory: do not overwrite reruns.
                    if final.exists():
                        raise FileExistsError(f"artifact already exists: {name}")
                    os.replace(stage / name, final)
                    published.append(final)
                directory_fd = os.open(destination, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                # Don't leave half a result if publication fails mid-run.
                for final in published:
                    final.unlink(missing_ok=True)
                raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 900:
        parser.error("--timeout must be between 1 and 900 seconds")
    try:
        convert(args.input.resolve(), args.destination.resolve(),
                args.engine.resolve(), args.timeout)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, zipfile.BadZipFile) as exc:
        print(f"3MF conversion failed: {exc}", file=sys.stderr)
        return 1
    print("3MF conversion completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
