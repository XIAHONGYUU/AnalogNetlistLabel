from __future__ import annotations

import unittest

from netlistlabel.infer import annotate
from netlistlabel.spice import parse_text


class DeviceAbstentionTest(unittest.TestCase):
    def test_unrecognized_device_hard_abstains(self) -> None:
        text = """
.subckt weird a b c d
XM1 a b c d sky130_fd_pr__nfet_01v8 L=1 W=1 nf=1 m=1
.ends
"""
        annotation = annotate(parse_text(text, source="weird.sp"))
        device = annotation.device_map()["XM1"]
        self.assertEqual(device.role, "unknown")
        self.assertEqual(device.review, "unknown")
        self.assertLessEqual(device.top_score, 0.45)
        self.assertTrue(device.candidates)
        self.assertIn("unknown", {candidate.label for candidate in device.candidates})
        self.assertTrue(device.evidence)
        self.assertTrue(any(item["name"] == "XM1" for item in annotation.review_queue))

    def test_confident_device_has_margin(self) -> None:
        text = """
.subckt pair inp inn out vdd vss tail
XM1 out inp tail vss sky130_fd_pr__nfet_01v8 L=1 W=2 nf=1 m=1
XM2 out2 inn tail vss sky130_fd_pr__nfet_01v8 L=1 W=2 nf=1 m=1
XM3 tail vss vss vss sky130_fd_pr__nfet_01v8 L=1 W=1 nf=1 m=1
XM4 out out vdd vdd sky130_fd_pr__pfet_01v8 L=1 W=2 nf=1 m=1
XM5 out2 out vdd vdd sky130_fd_pr__pfet_01v8 L=1 W=2 nf=1 m=1
.ends
"""
        annotation = annotate(parse_text(text, source="pair.sp"))
        device = annotation.device_map()["XM1"]
        self.assertGreater(device.top_score, 0.0)
        self.assertGreaterEqual(device.margin, 0.0)
        self.assertEqual(device.role, "input_pair")
        self.assertEqual(device.review, "auto")


if __name__ == "__main__":
    unittest.main()