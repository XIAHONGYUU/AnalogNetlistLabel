from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from netlistlabel.cli import main

ROOT = Path(__file__).resolve().parents[1]


class OutputContractTest(unittest.TestCase):
    def test_analyze_writes_three_artifacts_and_preserves_source(self) -> None:
        source = ROOT / "examples" / "generic_ota" / "generic_ota.sp"
        before = source.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            code = main(["analyze", str(source), "--out", tmp, "--quiet"])
            self.assertEqual(code, 0)
            out = Path(tmp)
            self.assertTrue((out / "annotation.json").exists())
            self.assertTrue((out / "annotation.md").exists())
            overlay = out / "generic_ota.annotated.sp"
            self.assertTrue(overlay.exists())
            payload = json.loads((out / "annotation.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "0.2")
            self.assertEqual(payload["design"]["name"], "generic_ota")
            self.assertTrue(payload["devices"])
            self.assertTrue(payload["ports"])
            self.assertTrue(payload["nets"])
            self.assertTrue(payload["blocks"])
            self.assertIn("coverage", payload)
            self.assertIn("review_queue", payload)
            overlay_text = overlay.read_text(encoding="utf-8")
            self.assertIn("nll_role=input_pair", overlay_text)
            self.assertIn("match=DP_AMP", overlay_text)
        self.assertEqual(source.read_text(encoding="utf-8"), before)

    def test_json_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                main(["analyze", str(ROOT / "examples" / "generic_ota" / "generic_ota.sp"), "--out", tmp, "--quiet"]),
                0,
            )
            payload = json.loads((Path(tmp) / "annotation.json").read_text(encoding="utf-8"))
        for key in ("schema_version", "design", "devices", "blocks", "review_queue", "coverage", "warnings"):
            self.assertIn(key, payload)
        for device in payload["devices"]:
            for key in ("name", "kind", "type", "model", "role", "a2l_role", "group", "match", "confidence", "review", "structures", "evidence", "negative_evidence", "alternatives", "candidates", "semantic_id", "canonical_name", "top_score", "margin", "terminals", "line_no"):
                self.assertIn(key, device)
            self.assertTrue(device["evidence"])
            self.assertGreaterEqual(device["confidence"], 0.0)
            self.assertLessEqual(device["confidence"], 1.0)
            if device["kind"] == "mos":
                self.assertEqual(set(device["terminals"]), {"d", "g", "s", "b"})
        for key in ("original_name", "direction", "class", "interface", "quantity", "polarity", "confidence", "candidates", "anchors"):
            self.assertIn(key, payload["ports"][0])
        for key in ("original_name", "class", "structural_role", "is_port", "confidence", "candidates"):
            self.assertIn(key, payload["nets"][0])


if __name__ == "__main__":
    unittest.main()