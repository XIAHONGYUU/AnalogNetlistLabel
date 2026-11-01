from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from netlistlabel.compare import compare_files
from netlistlabel.evaluate import evaluate
from netlistlabel.infer import annotate
from netlistlabel.spice import parse_file

# Keep this path relative: the repository must not contain a personal home path.
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT.parent / "project_analog2layout" / "examples" / "sky130_ldo_01v8"
LDO_DIR = Path(os.environ.get("NETLISTLABEL_LDO_DIR", DEFAULT_DIR))
RAW = LDO_DIR / "ldo.sp"
REFERENCE = LDO_DIR / "ldo.annotated.sp"
SKIP = not RAW.exists()


@unittest.skipIf(SKIP, "external SKY130 LDO benchmark not available")
class Sky130LdoBenchmarkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.annotation = annotate(parse_file(RAW))
        cls.devices = cls.annotation.device_map()

    def test_key_roles(self) -> None:
        expected = {
            "XM52": "input_pair",
            "XM53": "input_pair",
            "XM54": "tail_current",
            "XM46": "current_mirror",
            "XM56": "current_mirror",
            "XM57": "cascode",
            "XM58": "cascode",
            "XM61": "pass_device",
            "XM59": "output_stage",
            "XR4": "feedback",
            "XR5": "feedback",
            "XM77": "adj_switch",
            "XM78": "adj_switch",
            "XM83": "logic",
            "XM85": "enable_switch",
        }
        for name, role in expected.items():
            self.assertEqual(self.devices[name].role, role, name)
        self.assertIn("source_follower", self.devices["XM59"].structures)
        self.assertIn("common_source", self.devices["XM55"].structures)
        self.assertNotIn("common_source", self.devices["XM48"].structures)

    def test_blocks(self) -> None:
        blocks = {block.id for block in self.annotation.blocks}
        for required in ("AMP", "OUT", "BIAS", "REF", "START", "CTRL_EN", "CTRL_SEL", "FB"):
            self.assertIn(required, blocks)

    def test_coverage(self) -> None:
        coverage = self.annotation.coverage
        self.assertEqual(coverage["mos_total"], 41)
        self.assertEqual(coverage["mos_role_coverage"], 1.0)
        self.assertLessEqual(coverage["review_items"], 10)

    def test_match_groups(self) -> None:
        expected = {
            "XM52": "DP_AMP",
            "XM53": "DP_AMP",
            "XM46": "LOAD_AMP",
            "XM56": "LOAD_AMP",
            "XM57": "CAS_AMP",
            "XM58": "CAS_AMP",
            "XM62": "MIR_BIAS_VBIAS_P",
            "XM64": "MIR_BIAS_VBIAS_P",
            "XM66": "MIR_BIAS_DEG",
            "XM67": "MIR_BIAS_DEG",
        }
        for name, match in expected.items():
            self.assertEqual(self.devices[name].match, match, name)

    def test_human_gold_smoke(self) -> None:
        gold = ROOT / "benchmarks" / "gold" / "ldo_quick.gold.json"
        result = evaluate(self.annotation.to_dict(), json.loads(gold.read_text(encoding="utf-8")))
        self.assertEqual(result["reviewed_total"], 24)
        self.assertEqual(result["device_strict_accuracy"], 1.0)
        self.assertEqual(result["net_class_accuracy"], 1.0)
        self.assertEqual(result["port_direction_accuracy"], 1.0)

    def test_reviewed_ldo_gold(self) -> None:
        gold = ROOT / "benchmarks" / "gold" / "ldo_reviewed.gold.json"
        result = evaluate(self.annotation.to_dict(), json.loads(gold.read_text(encoding="utf-8")))
        self.assertEqual(result["reviewed_total"], 58)
        self.assertEqual(result["device_strict_accuracy"], 1.0)
        self.assertEqual(result["net_class_accuracy"], 1.0)
        self.assertEqual(result["port_direction_accuracy"], 1.0)

    @unittest.skipIf(not REFERENCE.exists(), "reference annotation not available")
    def test_reference_agreement(self) -> None:
        _, result = compare_files(RAW, REFERENCE)
        summary = result["summary"]
        self.assertGreaterEqual(summary["a2l_role_rate"], 0.85)
        self.assertGreaterEqual(summary["match_group_recall"], 0.80)


if __name__ == "__main__":
    unittest.main()