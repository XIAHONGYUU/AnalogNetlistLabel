from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from netlistlabel.evaluate import evaluate, evaluate_files
from netlistlabel.infer import annotate
from netlistlabel.review import build_review_packet
from netlistlabel.spice import parse_file

ROOT = Path(__file__).resolve().parents[1]


class ReviewEvaluateTest(unittest.TestCase):
    def test_packet_and_accept_all(self) -> None:
        annotation = annotate(parse_file(ROOT / "examples" / "generic_ota" / "generic_ota.sp"))
        payload = annotation.to_dict()
        with tempfile.TemporaryDirectory() as tmp:
            md_path, gold_path, csv_path = build_review_packet(
                payload, tmp, device_count=0, net_count=0, port_count=0
            )
            self.assertTrue(md_path.exists())
            self.assertTrue(csv_path.exists())
            review_text = md_path.read_text(encoding="utf-8")
            self.assertIn("关键尺寸与连接", review_text)
            self.assertIn("| D | G | S | B |", review_text)
            gold = json.loads(gold_path.read_text(encoding="utf-8"))
        self.assertTrue(gold["devices"])
        self.assertTrue(gold["nets"])
        self.assertTrue(gold["ports"])
        for section in ("devices", "nets", "ports"):
            for item in gold[section].values():
                self.assertEqual(item["decision"], "unreviewed")
                self.assertIn("predicted", item)

        for section in ("devices", "nets", "ports"):
            for item in gold[section].values():
                item["decision"] = "accept"
        result = evaluate(payload, gold)
        self.assertEqual(result["reviewed_total"], len(gold["devices"]) + len(gold["nets"]) + len(gold["ports"]))
        self.assertEqual(result["device_strict_accuracy"], 1.0)
        self.assertEqual(result["net_class_accuracy"], 1.0)
        self.assertEqual(result["port_direction_accuracy"], 1.0)

    def test_csv_accept_all(self) -> None:
        annotation = annotate(parse_file(ROOT / "examples" / "generic_ota" / "generic_ota.sp"))
        payload = annotation.to_dict()
        with tempfile.TemporaryDirectory() as tmp:
            _, _, csv_path = build_review_packet(
                payload, tmp, device_count=0, net_count=0, port_count=0
            )
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
                fields = list(rows[0].keys())
            for row in rows:
                row["decision"] = "accept"
            with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            pred_path = Path(tmp) / "annotation.json"
            pred_path.write_text(json.dumps(payload), encoding="utf-8")
            result = evaluate_files(pred_path, csv_path)
        self.assertEqual(result["device_strict_accuracy"], 1.0)
        self.assertEqual(result["net_class_accuracy"], 1.0)
        self.assertEqual(result["port_direction_accuracy"], 1.0)

    def test_correction_and_ambiguous_are_counted(self) -> None:
        annotation = annotate(parse_file(ROOT / "examples" / "generic_ota" / "generic_ota.sp"))
        payload = annotation.to_dict()
        with tempfile.TemporaryDirectory() as tmp:
            _, gold_path, _ = build_review_packet(
                payload, tmp, device_count=0, net_count=0, port_count=0
            )
            gold = json.loads(gold_path.read_text(encoding="utf-8"))
        for item in gold["devices"].values():
            item["decision"] = "accept"
        gold["devices"]["XM1"]["decision"] = "correct"
        gold["devices"]["XM1"]["role"] = "tail_current"
        gold["devices"]["XM2"]["decision"] = "ambiguous"
        result = evaluate(payload, gold)
        self.assertEqual(result["devices"]["decisions"].get("ambiguous"), 1)
        self.assertLess(result["device_strict_accuracy"], 1.0)
        self.assertEqual(result["devices"]["evaluated"], len(gold["devices"]) - 1)


if __name__ == "__main__":
    unittest.main()