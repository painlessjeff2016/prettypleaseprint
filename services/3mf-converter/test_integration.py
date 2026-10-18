"""Full PPP adapter integration tests using the pinned HueForge-safe AD5X engine.

Normal unit tests remain networkless. CI fetches the reviewed engine first and
sets AD5X_ENGINE_DIR. HUEFORGE_SAMPLE additionally enables the large real-file
test without checking customers' model files into the repository.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

from convert import convert

COLORS = ["#000000", "#4F4F4F", "#FF0000", "#E17100", "#FFFF00"]
LAYER_CHANGES = b'''<?xml version="1.0" encoding="utf-8"?>
<custom_gcodes_per_layer><plate><plate_info id="1"/>
<layer top_z="1.12" type="2" extruder="2" color="#4F4F4F" gcode="tool_change"/>
<layer top_z="1.60" type="2" extruder="3" color="#FF0000" gcode="tool_change"/>
<layer top_z="2.00" type="2" extruder="4" color="#E17100" gcode="tool_change"/>
<layer top_z="2.56" type="2" extruder="5" color="#FFFF00" gcode="tool_change"/>
<mode value="MultiAsSingle"/></plate></custom_gcodes_per_layer>'''
CONTENT_TYPES = b'''<?xml version="1.0"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
<Default Extension="config" ContentType="application/octet-stream"/>
<Default Extension="xml" ContentType="application/xml"/>
</Types>'''
OBJECT_CONFIG = b'''<?xml version="1.0"?>
<config><object id="1"><metadata key="extruder" value="1"/></object></config>'''
MODEL = b'''<?xml version="1.0"?>
<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
<resources><object id="1" type="model"><mesh>
<vertices><vertex x="0" y="0" z="0"/><vertex x="10" y="0" z="0"/><vertex x="0" y="10" z="0"/></vertices>
<triangles><triangle v1="0" v2="1" v3="2"/></triangles>
</mesh></object></resources><build><item objectid="1"/></build></model>'''


@unittest.skipUnless(os.getenv("AD5X_ENGINE_DIR"), "Set AD5X_ENGINE_DIR to run pinned-engine tests")
class PinnedHueForgeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = Path(os.environ["AD5X_ENGINE_DIR"]) / "bambu2ad5x.py"
        cls.template = json.loads((cls.engine.parent / "ad5x_template.json").read_text())

    def assert_result(self, original, output):
        with zipfile.ZipFile(original) as before, zipfile.ZipFile(output) as after:
            old = json.loads(before.read("Metadata/project_settings.config"))
            new = json.loads(after.read("Metadata/project_settings.config"))
            self.assertEqual(new["filament_colour"], old["filament_colour"])
            self.assertEqual(len(new["filament_settings_id"]), len(old["filament_colour"]))
            self.assertEqual(
                before.read("Metadata/custom_gcode_per_layer.xml"),
                after.read("Metadata/custom_gcode_per_layer.xml")
            )
            for key in ("layer_height", "initial_layer_print_height", "sparse_infill_density"):
                self.assertEqual(new.get(key), old.get(key), key)
            self.assertEqual(new["printer_settings_id"], "Flashforge AD5X")
            self.assertTrue(new["machine_start_gcode"].startswith("LED_ON\\nSTART_PRINT"))
            self.assertEqual(new["machine_end_gcode"], "END_PRINT\\nLED_OFF")

    def test_generated_hueforge_five_filaments_and_source_unchanged(self):
        settings = self.template.copy()
        settings.update({
            "printer_model": "Bambu Lab X1 Carbon",
            "filament_colour": COLORS,
            "filament_type": ["PLA"] * len(COLORS),
            "filament_settings_id": ["Generic PLA"] * len(COLORS),
            "layer_height": "0.08",
            "initial_layer_print_height": "0.16",
            "sparse_infill_density": "100%",
            "print_settings_id": "0.08mm High Quality @BBL X1C",
        })
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original, dest = root / "original.3mf", root / "converted"
            with zipfile.ZipFile(original, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("[Content_Types].xml", CONTENT_TYPES)
                z.writestr("Metadata/project_settings.config", json.dumps(settings))
                z.writestr("Metadata/model_settings.config", OBJECT_CONFIG)
                z.writestr("Metadata/custom_gcode_per_layer.xml", LAYER_CHANGES)
                z.writestr("3D/3dmodel.model", MODEL)
            before_hash = hashlib.sha256(original.read_bytes()).digest()
            convert(original, dest, self.engine, timeout=180)
            self.assert_result(original, dest / "converted.3mf")
            self.assertEqual(hashlib.sha256(original.read_bytes()).digest(), before_hash)
            self.assertTrue((dest / "conversion.report.txt").is_file())

    @unittest.skipUnless(os.getenv("HUEFORGE_SAMPLE"), "Set HUEFORGE_SAMPLE for real original")
    def test_real_hueforge_source(self):
        source = Path(os.environ["HUEFORGE_SAMPLE"])
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "converted"
            source_hash = hashlib.sha256(source.read_bytes()).digest()
            convert(source, output, self.engine, timeout=180)
            self.assert_result(source, output / "converted.3mf")
            self.assertEqual(hashlib.sha256(source.read_bytes()).digest(), source_hash)


if __name__ == "__main__":
    unittest.main()
