"""Evaluate an annotation against a human review/gold packet.

The gold packet uses decision=accept/correct/ambiguous/unreviewed. Accepted items
use the prediction as the expected label; corrected items use the edited field.
Ambiguous items are counted separately and excluded from accuracy.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

DECISIONS = {"unreviewed", "accept", "correct", "ambiguous"}


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluate_files(pred_path: str | Path, gold_path: str | Path) -> dict[str, Any]:
    prediction = load_json(pred_path)
    gold_path = Path(gold_path)
    gold = _load_csv_gold(gold_path) if gold_path.suffix.lower() == ".csv" else load_json(gold_path)
    return evaluate(prediction, gold)


def _split_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in str(value).replace(",", ";").split(";") if part.strip()]


def _load_csv_gold(path: Path) -> dict[str, Any]:
    gold: dict[str, Any] = {
        "schema_version": "0.1",
        "design": "",
        "source": path.name,
        "devices": {},
        "nets": {},
        "ports": {},
    }
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            kind = (row.get("kind") or "").strip().lower()
            name = (row.get("name") or "").strip()
            if not kind or not name:
                continue
            decision = (row.get("decision") or "unreviewed").strip().lower()
            predicted = (row.get("predicted") or "").strip()
            if kind == "device":
                role = (row.get("role") or "").strip() or predicted.split(" ")[0]
                gold["devices"][name] = {
                    "decision": decision,
                    "role": role,
                    "acceptable_roles": _split_list(row.get("acceptable_roles")),
                    "match": (row.get("match") or "").strip(),
                    "group": (row.get("group") or "").strip(),
                    "comment": (row.get("comment") or "").strip(),
                }
            elif kind == "net":
                parts = predicted.split("/", 1)
                gold["nets"][name] = {
                    "decision": decision,
                    "class": (row.get("class") or "").strip() or (parts[0] if parts else ""),
                    "acceptable_classes": _split_list(row.get("acceptable_classes")),
                    "structural_role": (row.get("structural_role") or "").strip() or (parts[1] if len(parts) > 1 else ""),
                    "acceptable_structural_roles": _split_list(row.get("acceptable_structural_roles")),
                    "comment": (row.get("comment") or "").strip(),
                }
            elif kind == "port":
                parts = predicted.split("/", 2)
                gold["ports"][name] = {
                    "decision": decision,
                    "direction": (row.get("direction") or "").strip() or (parts[0] if parts else ""),
                    "class": (row.get("class") or "").strip() or (parts[1] if len(parts) > 1 else ""),
                    "interface": (row.get("interface") or "").strip() or (parts[2] if len(parts) > 2 else ""),
                    "comment": (row.get("comment") or "").strip(),
                }
    return gold


def evaluate(prediction: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any]:
    pred_devices = {item["name"]: item for item in prediction.get("devices", [])}
    pred_nets = {item["original_name"]: item for item in prediction.get("nets", [])}
    pred_ports = {item["original_name"]: item for item in prediction.get("ports", [])}

    result: dict[str, Any] = {
        "design": prediction.get("design", {}).get("name", gold.get("design", "design")),
        "schema_version": "0.1",
        "source": gold.get("source", ""),
        "decisions": Counter(),
        "devices": _evaluate_devices(gold.get("devices", {}), pred_devices),
        "nets": _evaluate_nets(gold.get("nets", {}), pred_nets),
        "ports": _evaluate_ports(gold.get("ports", {}), pred_ports),
        "notes": [
            "This is a sampled human-review result, not a claim of global accuracy.",
            "Accepted items use the prediction as the expected label.",
            "Ambiguous items are counted but excluded from accuracy.",
        ],
    }

    reviewed = 0
    for section in ("devices", "nets", "ports"):
        data = result[section]
        reviewed += data["reviewed"]
        for decision, count in data["decisions"].items():
            result["decisions"][decision] += count
    result["decisions"] = dict(result["decisions"])
    result["reviewed_total"] = reviewed
    result["review_rate"] = _rate(reviewed, result["devices"]["total"] + result["nets"]["total"] + result["ports"]["total"])
    result["device_strict_accuracy"] = result["devices"]["strict_accuracy"]
    result["device_lenient_accuracy"] = result["devices"]["lenient_accuracy"]
    result["net_class_accuracy"] = result["nets"]["class_accuracy"]
    result["net_role_accuracy"] = result["nets"]["role_accuracy"]
    result["port_direction_accuracy"] = result["ports"]["direction_accuracy"]
    result["port_class_accuracy"] = result["ports"]["class_accuracy"]
    result["port_interface_accuracy"] = result["ports"]["interface_accuracy"]
    return result


def _decision(item: dict[str, Any]) -> str:
    decision = str(item.get("decision", "unreviewed")).lower()
    return decision if decision in DECISIONS else "unreviewed"


def _rate(correct: int, total: int) -> float | None:
    return round(correct / total, 3) if total else None


def _evaluate_devices(gold: dict[str, Any], prediction: dict[str, Any]) -> dict[str, Any]:
    decisions: Counter[str] = Counter()
    strict_correct = 0
    lenient_correct = 0
    evaluated = 0
    auto_reviewed = 0
    auto_correct = 0
    match_total = 0
    match_correct = 0
    group_total = 0
    group_correct = 0
    confusion: Counter[str] = Counter()
    missing: list[str] = []

    for name, item in gold.items():
        decision = _decision(item)
        decisions[decision] += 1
        if decision == "unreviewed":
            continue
        pred = prediction.get(name)
        if pred is None:
            missing.append(name)
            continue
        if decision == "ambiguous":
            continue
        expected = pred.get("role") if decision == "accept" else (item.get("role") or pred.get("role"))
        acceptable = set(item.get("acceptable_roles") or [])
        strict = pred.get("role") == expected
        lenient = strict or pred.get("role") in acceptable
        strict_correct += int(strict)
        lenient_correct += int(lenient)
        evaluated += 1
        confusion[f"{pred.get('role')} -> {expected}"] += 1
        if pred.get("review") == "auto":
            auto_reviewed += 1
            auto_correct += int(strict)
        if item.get("match"):
            match_total += 1
            match_correct += int((pred.get("match") or "") == item.get("match"))
        if item.get("group"):
            group_total += 1
            group_correct += int((pred.get("group") or "") == item.get("group"))

    return {
        "total": len(gold),
        "reviewed": evaluated + sum(count for decision, count in decisions.items() if decision == "ambiguous"),
        "evaluated": evaluated,
        "decisions": dict(decisions),
        "strict_correct": strict_correct,
        "strict_accuracy": _rate(strict_correct, evaluated),
        "lenient_correct": lenient_correct,
        "lenient_accuracy": _rate(lenient_correct, evaluated),
        "auto_reviewed": auto_reviewed,
        "auto_precision": _rate(auto_correct, auto_reviewed),
        "match_total": match_total,
        "match_accuracy": _rate(match_correct, match_total),
        "group_total": group_total,
        "group_accuracy": _rate(group_correct, group_total),
        "confusion": dict(confusion),
        "missing_predictions": missing,
    }


def _evaluate_nets(gold: dict[str, Any], prediction: dict[str, Any]) -> dict[str, Any]:
    decisions: Counter[str] = Counter()
    class_correct = 0
    role_correct = 0
    evaluated = 0
    class_confusion: Counter[str] = Counter()
    role_confusion: Counter[str] = Counter()
    missing: list[str] = []

    for name, item in gold.items():
        decision = _decision(item)
        decisions[decision] += 1
        if decision == "unreviewed":
            continue
        pred = prediction.get(name)
        if pred is None:
            missing.append(name)
            continue
        if decision == "ambiguous":
            continue
        expected_class = pred.get("class") if decision == "accept" else (item.get("class") or pred.get("class"))
        expected_role = (
            pred.get("structural_role")
            if decision == "accept"
            else (item.get("structural_role") or pred.get("structural_role"))
        )
        class_ok = pred.get("class") == expected_class or pred.get("class") in set(item.get("acceptable_classes") or [])
        role_ok = pred.get("structural_role") == expected_role or pred.get("structural_role") in set(
            item.get("acceptable_structural_roles") or []
        )
        class_correct += int(class_ok)
        role_correct += int(role_ok)
        evaluated += 1
        class_confusion[f"{pred.get('class')} -> {expected_class}"] += 1
        role_confusion[f"{pred.get('structural_role')} -> {expected_role}"] += 1

    return {
        "total": len(gold),
        "reviewed": evaluated + sum(count for decision, count in decisions.items() if decision == "ambiguous"),
        "evaluated": evaluated,
        "decisions": dict(decisions),
        "class_correct": class_correct,
        "class_accuracy": _rate(class_correct, evaluated),
        "role_correct": role_correct,
        "role_accuracy": _rate(role_correct, evaluated),
        "class_confusion": dict(class_confusion),
        "role_confusion": dict(role_confusion),
        "missing_predictions": missing,
    }


def _evaluate_ports(gold: dict[str, Any], prediction: dict[str, Any]) -> dict[str, Any]:
    decisions: Counter[str] = Counter()
    direction_correct = 0
    class_correct = 0
    interface_correct = 0
    evaluated = 0
    missing: list[str] = []

    for name, item in gold.items():
        decision = _decision(item)
        decisions[decision] += 1
        if decision == "unreviewed":
            continue
        pred = prediction.get(name)
        if pred is None:
            missing.append(name)
            continue
        if decision == "ambiguous":
            continue
        expected_direction = pred.get("direction") if decision == "accept" else (item.get("direction") or pred.get("direction"))
        expected_class = pred.get("class") if decision == "accept" else (item.get("class") or pred.get("class"))
        expected_interface = pred.get("interface") if decision == "accept" else (item.get("interface") or pred.get("interface"))
        direction_correct += int(pred.get("direction") == expected_direction)
        class_correct += int(pred.get("class") == expected_class)
        interface_correct += int(pred.get("interface") == expected_interface)
        evaluated += 1

    return {
        "total": len(gold),
        "reviewed": evaluated + sum(count for decision, count in decisions.items() if decision == "ambiguous"),
        "evaluated": evaluated,
        "decisions": dict(decisions),
        "direction_correct": direction_correct,
        "direction_accuracy": _rate(direction_correct, evaluated),
        "class_correct": class_correct,
        "class_accuracy": _rate(class_correct, evaluated),
        "interface_correct": interface_correct,
        "interface_accuracy": _rate(interface_correct, evaluated),
        "missing_predictions": missing,
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Review evaluation — {result.get('design', 'design')}")
    lines.append("")
    lines.append("> Sampled human review, not a global accuracy claim.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("| --- | --- |")
    lines.append(f"| reviewed / packet | {result.get('reviewed_total', 0)} |")
    lines.append(f"| review rate | {_fmt(result.get('review_rate'))} |")
    lines.append(f"| device strict accuracy | {_fmt(result.get('device_strict_accuracy'))} |")
    lines.append(f"| device lenient accuracy | {_fmt(result.get('device_lenient_accuracy'))} |")
    lines.append(f"| net class accuracy | {_fmt(result.get('net_class_accuracy'))} |")
    lines.append(f"| net role accuracy | {_fmt(result.get('net_role_accuracy'))} |")
    lines.append(f"| port direction accuracy | {_fmt(result.get('port_direction_accuracy'))} |")
    lines.append(f"| port class accuracy | {_fmt(result.get('port_class_accuracy'))} |")
    lines.append(f"| port interface accuracy | {_fmt(result.get('port_interface_accuracy'))} |")
    lines.append("")
    for section in ("devices", "nets", "ports"):
        data = result.get(section, {})
        lines.append(f"## {section.title()}")
        lines.append("")
        lines.append(f"- total: {data.get('total', 0)}")
        lines.append(f"- evaluated: {data.get('evaluated', 0)}")
        lines.append(f"- decisions: {data.get('decisions', {})}")
        if section == "devices":
            lines.append(f"- auto precision (tool auto + reviewed): {_fmt(data.get('auto_precision'))}")
            lines.append(f"- match accuracy: {_fmt(data.get('match_accuracy'))}")
            lines.append(f"- group accuracy: {_fmt(data.get('group_accuracy'))}")
            if data.get("confusion"):
                lines.append(f"- confusion: {data['confusion']}")
        if section == "nets":
            if data.get("class_confusion"):
                lines.append(f"- class confusion: {data['class_confusion']}")
            if data.get("role_confusion"):
                lines.append(f"- role confusion: {data['role_confusion']}")
        lines.append("")
    missing = {
        section: result.get(section, {}).get("missing_predictions", [])
        for section in ("devices", "nets", "ports")
    }
    missing = {key: value for key, value in missing.items() if value}
    if missing:
        lines.append("## Missing predictions")
        lines.append("")
        for section, names in missing.items():
            lines.append(f"- {section}: {', '.join(names)}")
        lines.append("")
    lines.append("## Notes")
    lines.append("")
    for note in result.get("notes", []):
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def _fmt(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.1%}"
    return str(value)


def write_evaluation(result: dict[str, Any], out_dir: str | Path) -> tuple[Path, Path]:
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "eval.json"
    md_path = target / "eval.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return json_path, md_path