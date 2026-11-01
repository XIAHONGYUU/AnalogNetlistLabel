"""Compare an inferred annotation with a reference annotation file.

The reference is usually a human- or agent-authored annotated netlist. It is a
comparison target, not ground truth: disagreements are listed for review.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

from .infer import annotate
from .model import Annotation
from .spice import Netlist, parse_file


def compare_files(raw_path: str | Path, reference_path: str | Path) -> tuple[Annotation, dict[str, Any]]:
    raw = parse_file(raw_path)
    reference = parse_file(reference_path)
    annotation = annotate(raw)
    result = compare_annotation(annotation, raw, reference)
    return annotation, result


def compare_annotation(annotation: Annotation, raw: Netlist, reference: Netlist) -> dict[str, Any]:
    inferred = annotation.device_map()
    ref_devices = reference.device_by_name()
    rows: list[dict[str, Any]] = []

    for device in raw.devices:
        ref_device = ref_devices.get(device.name)
        if ref_device is None:
            continue
        ref_role = ref_device.params.get("role")
        if not ref_role:
            continue
        ann = inferred.get(device.name)
        if ann is None:
            continue
        ref_match = ref_device.params.get("match")
        inferred_match = ann.match
        rows.append(
            {
                "name": device.name,
                "type": device.type,
                "inferred_role": ann.role,
                "inferred_a2l_role": ann.a2l_role,
                "reference_role": ref_role,
                "exact_match": ann.role == ref_role,
                "a2l_match": ann.a2l_role == ref_role,
                "confidence": round(ann.confidence, 3),
                "group": ann.group,
                "reference_group": ref_device.params.get("group"),
                "inferred_match": inferred_match,
                "reference_match": ref_match,
                "evidence": ann.evidence,
            }
        )

    compared = len(rows)
    exact = sum(1 for row in rows if row["exact_match"])
    a2l = sum(1 for row in rows if row["a2l_match"])
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        confusion[row["inferred_role"]][row["reference_role"]] += 1

    # Match-group agreement: compare actual device sets, not group ids.
    ref_groups: dict[str, set[str]] = defaultdict(set)
    inf_groups: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row["reference_match"]:
            ref_groups[row["reference_match"]].add(row["name"])
        if row["inferred_match"]:
            inf_groups[row["inferred_match"]].add(row["name"])
    match_sets_ref = {frozenset(names) for names in ref_groups.values() if len(names) >= 2}
    match_sets_inf = {frozenset(names) for names in inf_groups.values() if len(names) >= 2}
    match_exact = match_sets_ref & match_sets_inf
    ref_matched_devices = {name for names in match_sets_ref for name in names}
    inf_matched_devices = {name for names in match_sets_inf for name in names}
    match_precision = (
        len(match_exact) / len(match_sets_inf) if match_sets_inf else 0.0
    )
    match_recall = (
        len(match_exact) / len(match_sets_ref) if match_sets_ref else 0.0
    )

    # Partition agreement: for every device pair, did both partitions put them
    # in the same group? This is label-independent.
    pair_total = 0
    pair_agree = 0
    for left, right in combinations(rows, 2):
        pair_total += 1
        ref_same = left["reference_group"] and left["reference_group"] == right["reference_group"]
        inf_same = left["group"] and left["group"] == right["group"]
        if bool(ref_same) == bool(inf_same):
            pair_agree += 1
    partition_agreement = pair_agree / pair_total if pair_total else 0.0

    disagreements = [row for row in rows if not row["a2l_match"]]
    summary = {
        "raw": str(raw.source),
        "reference": str(reference.source),
        "compared_devices": compared,
        "exact_role_agree": exact,
        "exact_role_rate": round(exact / compared, 3) if compared else 0.0,
        "a2l_role_agree": a2l,
        "a2l_role_rate": round(a2l / compared, 3) if compared else 0.0,
        "reference_match_groups": len(match_sets_ref),
        "inferred_match_groups": len(match_sets_inf),
        "exact_match_groups": len(match_exact),
        "match_group_precision": round(match_precision, 3),
        "match_group_recall": round(match_recall, 3),
        "ref_matched_devices": len(ref_matched_devices),
        "inferred_matched_devices": len(inf_matched_devices),
        "partition_pair_agreement": round(partition_agreement, 3),
    }
    return {
        "summary": summary,
        "rows": rows,
        "disagreements": disagreements,
        "confusion": {role: dict(counter) for role, counter in sorted(confusion.items())},
        "match_groups": {
            "reference": [sorted(names) for names in sorted(match_sets_ref)],
            "inferred": [sorted(names) for names in sorted(match_sets_inf)],
            "exact": [sorted(names) for names in sorted(match_exact)],
        },
        "caveat": (
            "The reference is a prior annotation, not ground truth. "
            "Every disagreement needs manual review before it is treated as an error."
        ),
    }


def render_compare_markdown(result: dict[str, Any]) -> str:
    summary = result["summary"]
    lines: list[str] = []
    lines.append("# NetlistLabel comparison")
    lines.append("")
    lines.append(f"- raw: {summary['raw']}")
    lines.append(f"- reference: {summary['reference']}")
    lines.append("")
    lines.append("> " + result["caveat"])
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("| --- | --- |")
    for key in (
        "compared_devices",
        "exact_role_agree",
        "exact_role_rate",
        "a2l_role_agree",
        "a2l_role_rate",
        "partition_pair_agreement",
        "reference_match_groups",
        "inferred_match_groups",
        "exact_match_groups",
        "match_group_precision",
        "match_group_recall",
    ):
        value = summary[key]
        if isinstance(value, float):
            value = f"{value:.1%}" if key.endswith("rate") or key.endswith("agreement") or key.startswith("match_group") else f"{value:.3f}"
        lines.append(f"| {key} | {value} |")
    lines.append("")

    lines.append("## Disagreements (a2l-level)")
    lines.append("")
    if not result["disagreements"]:
        lines.append("None.")
    else:
        lines.append("| device | inferred | reference | conf | group | evidence |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for row in result["disagreements"]:
            evidence = "; ".join(row["evidence"][:2]).replace("|", "\\|")
            lines.append(
                "| {name} | {inf} | {ref} | {conf:.2f} | {group} | {evidence} |".format(
                    name=row["name"],
                    inf=row["inferred_role"],
                    ref=row["reference_role"],
                    conf=row["confidence"],
                    group=row["group"],
                    evidence=evidence,
                )
            )
    lines.append("")

    lines.append("## Confusion (inferred → reference)")
    lines.append("")
    lines.append("| inferred | reference counts |")
    lines.append("| --- | --- |")
    for role, counts in result["confusion"].items():
        lines.append(f"| {role} | {', '.join(f'{key}: {value}' for key, value in counts.items())} |")
    lines.append("")

    lines.append("## Match groups")
    lines.append("")
    exact = result["match_groups"]["exact"]
    lines.append(f"- exact device-set matches: {exact or 'none'}")
    lines.append(f"- reference groups: {result['match_groups']['reference'] or 'none'}")
    lines.append(f"- inferred groups: {result['match_groups']['inferred'] or 'none'}")
    lines.append("")
    return "\n".join(lines)


def write_compare(result: dict[str, Any], out_dir: str | Path) -> tuple[Path, Path]:
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "compare.json"
    md_path = target / "compare.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_compare_markdown(result), encoding="utf-8")
    return json_path, md_path
