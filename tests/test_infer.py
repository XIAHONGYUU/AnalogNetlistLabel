from __future__ import annotations

import unittest
from pathlib import Path

from netlistlabel.infer import annotate
from netlistlabel.spice import parse_file

ROOT = Path(__file__).resolve().parents[1]


class GenericOtaInferenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.netlist = parse_file(ROOT / "examples" / "generic_ota" / "generic_ota.sp")
        cls.annotation = annotate(cls.netlist)
        cls.devices = cls.annotation.device_map()

    def test_roles(self) -> None:
        expected = {
            "XM1": "input_pair",
            "XM2": "input_pair",
            "XM3": "tail_current",
            "XM4": "current_mirror",
            "XM5": "current_mirror",
            "XM6": "output_stage",
            "XM7": "current_mirror",
            "XM8": "current_mirror",
            "XC1": "compensation",
        }
        for name, role in expected.items():
            self.assertEqual(self.devices[name].role, role, name)

    def test_match_groups(self) -> None:
        self.assertEqual(self.devices["XM1"].match, "DP_AMP")
        self.assertEqual(self.devices["XM2"].match, "DP_AMP")
        self.assertEqual(self.devices["XM4"].match, "LOAD_AMP")
        self.assertEqual(self.devices["XM5"].match, "LOAD_AMP")

    def test_blocks(self) -> None:
        blocks = {block.id: block for block in self.annotation.blocks}
        self.assertIn("AMP", blocks)
        self.assertIn("OUT", blocks)
        self.assertIn("BIAS", blocks)
        self.assertEqual(blocks["AMP"].devices, ["XM1", "XM2", "XM3", "XM4", "XM5"])
        self.assertEqual(blocks["OUT"].devices, ["XM6", "XM7"])
        self.assertEqual(blocks["BIAS"].devices, ["XM8"])

    def test_coverage_and_evidence(self) -> None:
        self.assertEqual(self.annotation.coverage["mos_role_coverage"], 1.0)
        self.assertEqual(self.annotation.coverage["roles_known"], self.annotation.coverage["devices_total"])
        for device in self.annotation.devices:
            self.assertTrue(device.evidence, device.name)
        self.assertTrue(all(device.role != "unknown" for device in self.annotation.devices))

    def test_cap_review_is_explicit(self) -> None:
        queue = {
            item.get("device") or item.get("name")
            for item in self.annotation.review_queue
        }
        self.assertIn("XC1", queue)


if __name__ == "__main__":
    unittest.main()