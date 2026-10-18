"""Offline smoke tests for the adapter, without a live printer or upstream engine."""
import errno
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("convert.py")
spec = importlib.util.spec_from_file_location("converter_adapter", SCRIPT)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def sample_3mf(path):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        archive.writestr("3D/3dmodel.model", "<model/>")


class ConverterSmokeTests(unittest.TestCase):
    def test_success_original_unchanged_and_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.3mf"
            output = root / "result"
            engine = root / "fake_engine.py"
            sample_3mf(source)
            before = source.read_bytes()
            (root / "ad5x_template.json").write_text("{}")
            engine.write_text(
                "from pathlib import Path\n"
                "import shutil, sys\n"
                "source = Path(sys.argv[1])\n"
                "out = Path(sys.argv[sys.argv.index('--output') + 1])\n"
                "shutil.copyfile(source, out)\n"
                "Path(str(out) + '.report.txt').write_text('test conversion report')\n"
            )
            adapter.convert(source, output, engine, timeout=10)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual((output / "converted.3mf").read_bytes(), before)
            self.assertIn("test conversion report", (output / "conversion.report.txt").read_text())

    def test_publishes_without_cross_device_rename(self):
        # Docker uses /tmp as tmpfs and /work as a host-mounted filesystem.
        # Emulate EXDEV when the rename source is outside the output mount.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.3mf"
            output = root / "result"
            engine = root / "fake_engine.py"
            sample_3mf(source)
            (root / "ad5x_template.json").write_text("{}")
            engine.write_text(
                "from pathlib import Path\n"
                "import shutil, sys\n"
                "out = Path(sys.argv[sys.argv.index('--output') + 1])\n"
                "shutil.copyfile(sys.argv[1], out)\n"
                "Path(str(out) + '.report.txt').write_text('report')\n"
            )

            original_replace = adapter.os.replace

            def rename_if_same_mount(src, dst):
                if not Path(src).is_relative_to(output):
                    raise OSError(errno.EXDEV, "Invalid cross-device link")
                return original_replace(src, dst)

            with patch.object(adapter.os, "replace", side_effect=rename_if_same_mount):
                adapter.convert(source, output, engine, timeout=10)

            self.assertEqual((output / "converted.3mf").read_bytes(), source.read_bytes())
            self.assertEqual((output / "conversion.report.txt").read_text(), "report")

    def test_reject_invalid_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "bad.3mf"
            source.write_text("not a ZIP")
            with self.assertRaises(zipfile.BadZipFile):
                adapter.check_archive(source)

    def test_does_not_overwrite_existing_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.3mf"
            target = root / "result"
            target.mkdir()
            (target / "converted.3mf").write_bytes(b"existing")
            engine = root / "fake_engine.py"
            sample_3mf(source)
            (root / "ad5x_template.json").write_text("{}")
            engine.write_text(
                "from pathlib import Path\n"
                "import shutil, sys\n"
                "out = Path(sys.argv[sys.argv.index('--output') + 1])\n"
                "shutil.copyfile(sys.argv[1], out)\n"
                "Path(str(out) + '.report.txt').write_text('report')\n"
            )
            with self.assertRaises(FileExistsError):
                adapter.convert(source, target, engine, timeout=10)
            self.assertEqual((target / "converted.3mf").read_bytes(), b"existing")


if __name__ == "__main__":
    unittest.main()
