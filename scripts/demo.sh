#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT=""
if [ "$#" -gt 0 ]; then OUT="$1"; fi
if [ -z "$OUT" ]; then OUT=out/demo; fi

echo "== Generic OTA =="
python3 -m netlistlabel analyze examples/generic_ota/generic_ota.sp --out "$OUT/generic_ota"
python3 -m netlistlabel evaluate \
  "$OUT/generic_ota/annotation.json" \
  benchmarks/gold/generic_ota.gold.json \
  --out "$OUT/generic_ota/eval"

LDO_DIR="$(printenv NETLISTLABEL_LDO_DIR || true)"
if [ -n "$LDO_DIR" ] && [ -f "$LDO_DIR/ldo.sp" ]; then
  echo "== SKY130 LDO =="
  python3 -m netlistlabel analyze "$LDO_DIR/ldo.sp" --out "$OUT/ldo"
  python3 -m netlistlabel evaluate \
    "$OUT/ldo/annotation.json" \
    benchmarks/gold/ldo_reviewed.gold.json \
    --out "$OUT/ldo/eval"
else
  echo "Set NETLISTLABEL_LDO_DIR to a directory containing ldo.sp to run the LDO demo."
fi

echo "Artifacts: $OUT"