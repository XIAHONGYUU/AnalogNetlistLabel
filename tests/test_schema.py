from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

try:
    import jsonschema
except ImportError:  # optional test dependency; the package itself is stdlib-only
    jsonschema = None

from netlistlabel.cli import main

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "annotation.schema.json"


class SchemaContractTest(unittest.TestCase):
    def test_schema_parses(self) -> None:
        data = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(data["properties"]["schema_version"]["type"], "string")
        for key in ("ports", "devices", "nets", "blocks", "review_queue", "coverage"):
            self.assertIn(key, data["properties"])

    @unittest.skipIf(jsonschema is None, "jsonschema not installed")
    def test_generated_annotation_matches_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code = main(
                [
                    "analyze",
                    str(ROOT / "examples" / "generic_ota" / "generic_ota.sp"),
                    "--out",
                    tmp,
                    "--quiet",
                ]
            )
            self.assertEqual(code, 0)
            payload = json.loads((Path(tmp) / "annotation.json").read_text(encoding="utf-8"))
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        jsonschema.validate(payload, schema)


if __name__ == "__main__":
    unittest.main()
