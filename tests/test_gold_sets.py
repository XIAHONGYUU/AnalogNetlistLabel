from __future__ import annotations

import json
import unittest
from pathlib import Path

from netlistlabel.evaluate import evaluate
from netlistlabel.infer import annotate
from netlistlabel.spice import parse_file

ROOT = Path(__file__).resolve().parents[1]


class GoldSmokeTest(unittest.TestCase):
    def test_generic_ota_gold(self) -> None:
        annotation = annotate(parse_file(ROOT / "examples" / "generic_ota" / "generic_ota.sp"))
        gold = json.loads((ROOT / "benchmarks" / "gold" / "generic_ota.gold.json").read_text(encoding="utf-8"))
        result = evaluate(annotation.to_dict(), gold)
        self.assertEqual(result["reviewed_total"], 26)
        self.assertEqual(result["device_strict_accuracy"], 1.0)
        self.assertEqual(result["net_class_accuracy"], 1.0)
        self.assertEqual(result["port_direction_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
