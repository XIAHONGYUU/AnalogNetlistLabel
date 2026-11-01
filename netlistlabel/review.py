"""生成人工复核包（中文友好版）。

产物：
- review.md：中文阅读版，带编号、证据、行号、重点/抽查分组；
- review.csv：Excel 可直接编辑的标注表；
- gold.json：程序可读的 gold 模板。

只改 decision 和 label 字段；predicted 是审计记录，不要改。
"""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path
from typing import Any


def load_annotation(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sample(items: list[dict[str, Any]], count: int, seed: int, *, field: str = "role", key: set[str] | None = None, must: set[str] | None = None) -> list[dict[str, Any]]:
    if count <= 0 or count >= len(items):
        return list(items)
    must_items = [item for item in items if must and item.get(field) in must]
    review_items = [item for item in items if item.get("review") != "auto"]
    key_items = [item for item in items if key and item.get(field) in key and item not in must_items]
    rest = [item for item in items if item not in must_items and item not in review_items and item not in key_items]
    random.Random(seed).shuffle(rest)
    selected: list[dict[str, Any]] = []
    for group in (must_items, review_items, key_items, rest):
        for item in group:
            if len(selected) >= count:
                break
            if item not in selected:
                selected.append(item)
        if len(selected) >= count:
            break
    return selected


def _ev(items: list[str], limit: int = 2) -> str:
    return "; ".join(items[:limit]) if items else "—"


def _esc(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _source_lines(annotation: dict[str, Any]) -> list[str]:
    source = str(annotation.get("design", {}).get("source", ""))
    try:
        return Path(source).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def _line(device: dict[str, Any], lines: list[str]) -> str:
    number = int(device.get("line_no") or 0)
    return lines[number - 1].strip() if 0 < number <= len(lines) else "—"


def _pred_device(device: dict[str, Any]) -> str:
    parts = [str(device.get("role", "?"))]
    if device.get("match"):
        parts.append("match=" + str(device["match"]))
    if device.get("group"):
        parts.append("group=" + str(device["group"]))
    return " ".join(parts)


def _pred_net(net: dict[str, Any]) -> str:
    return f"{net.get('class', '?')}/{net.get('structural_role', '?')}"


def _pred_port(port: dict[str, Any]) -> str:
    return f"{port.get('direction', '?')}/{port.get('class', '?')}/{port.get('interface', '?')}"


def build_review_packet(annotation: dict[str, Any], out_dir: str | Path, *, device_count: int = 20, net_count: int = 12, port_count: int = 0, seed: int = 7) -> tuple[Path, Path, Path]:
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    devices = _sample(
        annotation.get("devices", []), device_count, seed,
        field="role",
        key={"input_pair", "tail_current", "pass_device", "current_mirror", "cascode", "output_stage", "feedback"},
        must={"pass_device", "input_pair", "tail_current", "output_stage", "feedback"},
    )
    nets = _sample(
        annotation.get("nets", []), net_count, seed + 1,
        field="structural_role",
        key={"tail", "mirror_gate", "pass_gate", "feedback", "gain_node", "reference", "startup"},
        must={"tail", "pass_gate", "feedback", "gain_node"},
    )
    ports = _sample(annotation.get("ports", []), port_count, seed + 2)
    source_lines = _source_lines(annotation)

    gold: dict[str, Any] = {
        "schema_version": "0.1",
        "design": annotation.get("design", {}).get("name", "design"),
        "source": Path(str(annotation.get("design", {}).get("source", ""))).name,
        "instructions": (
            "先读 review.md 或 review.csv。只改 decision 和 label 字段。"
            "decision=accept 表示预测正确；decision=correct 表示改了标签；"
            "decision=ambiguous 表示确实有歧义，不计入 accuracy；"
            "unreviewed 表示尚未复核。predicted 是审计记录，不要改。"
        ),
        "devices": {},
        "nets": {},
        "ports": {},
    }
    for index, device in enumerate(devices, start=1):
        gold["devices"][device["name"]] = {
            "id": f"D{index:02d}",
            "predicted": {
                "role": device.get("role"),
                "match": device.get("match"),
                "group": device.get("group"),
                "confidence": device.get("confidence"),
                "top_score": device.get("top_score"),
                "margin": device.get("margin"),
                "w_um": device.get("width_um"),
                "l_um": device.get("l_um"),
                "nf": device.get("nf"),
                "m": device.get("m"),
                "terminals": device.get("terminals", {}),
                "review": device.get("review"),
            },
            "decision": "unreviewed",
            "role": device.get("role") or "",
            "acceptable_roles": [],
            "match": device.get("match") or "",
            "group": device.get("group") or "",
            "comment": "",
        }
    for index, net in enumerate(nets, start=1):
        gold["nets"][net["original_name"]] = {
            "id": f"N{index:02d}",
            "predicted": {
                "class": net.get("class"),
                "structural_role": net.get("structural_role"),
                "block": net.get("block"),
                "confidence": net.get("confidence"),
                "review": net.get("review"),
            },
            "decision": "unreviewed",
            "class": net.get("class") or "",
            "acceptable_classes": [],
            "structural_role": net.get("structural_role") or "",
            "acceptable_structural_roles": [],
            "comment": "",
        }
    for index, port in enumerate(ports, start=1):
        gold["ports"][port["original_name"]] = {
            "id": f"P{index:02d}",
            "predicted": {
                "direction": port.get("direction"),
                "class": port.get("class"),
                "interface": port.get("interface"),
                "confidence": port.get("confidence"),
                "review": port.get("review"),
            },
            "decision": "unreviewed",
            "direction": port.get("direction") or "",
            "class": port.get("class") or "",
            "interface": port.get("interface") or "",
            "comment": "",
        }

    gold_path = target / "gold.json"
    gold_path.write_text(json.dumps(gold, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    csv_path = target / "review.csv"
    _write_csv(csv_path, devices, nets, ports)
    md_path = target / "review.md"
    md_path.write_text(_render_markdown(annotation, devices, nets, ports, source_lines), encoding="utf-8")
    return md_path, gold_path, csv_path


def _write_csv(path: Path, devices: list[dict[str, Any]], nets: list[dict[str, Any]], ports: list[dict[str, Any]]) -> None:
    columns = ["id", "kind", "name", "predicted", "decision", "role", "class", "structural_role", "direction", "interface", "match", "group", "w_um", "l_um", "nf", "m", "drain", "gate", "source", "bulk", "acceptable_roles", "acceptable_classes", "acceptable_structural_roles", "comment"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for index, device in enumerate(devices, start=1):
            terminals = device.get("terminals", {})
            writer.writerow({
                "id": f"D{index:02d}", "kind": "device", "name": device["name"],
                "predicted": _pred_device(device), "decision": "unreviewed",
                "role": device.get("role", ""), "match": device.get("match") or "",
                "group": device.get("group") or "",
                "w_um": device.get("width_um", ""), "l_um": device.get("l_um", ""),
                "nf": device.get("nf", ""), "m": device.get("m", ""),
                "drain": terminals.get("d", ""), "gate": terminals.get("g", ""),
                "source": terminals.get("s", ""), "bulk": terminals.get("b", ""),
            })
        for index, net in enumerate(nets, start=1):
            writer.writerow({"id": f"N{index:02d}", "kind": "net", "name": net["original_name"], "predicted": _pred_net(net), "decision": "unreviewed", "class": net.get("class", ""), "structural_role": net.get("structural_role", "")})
        for index, port in enumerate(ports, start=1):
            writer.writerow({"id": f"P{index:02d}", "kind": "port", "name": port["original_name"], "predicted": _pred_port(port), "decision": "unreviewed", "direction": port.get("direction", ""), "class": port.get("class", ""), "interface": port.get("interface", "")})


def _render_markdown(annotation: dict[str, Any], devices: list[dict[str, Any]], nets: list[dict[str, Any]], ports: list[dict[str, Any]], source_lines: list[str]) -> str:
    design = annotation.get("design", {})
    source = Path(str(design.get("source", ""))).name
    focus_devices = [d for d in devices if d.get("review") != "auto" or float(d.get("confidence", 0)) < 0.7]
    sample_devices = [d for d in devices if d not in focus_devices]
    focus_nets = [n for n in nets if n.get("review") != "auto" or float(n.get("confidence", 0)) < 0.7]
    sample_nets = [n for n in nets if n not in focus_nets]
    L: list[str] = []
    L.append(f"# 人工复核包 — {design.get('name', 'design')}")
    L.append("")
    L.append(f"- 源网表：{source}")
    L.append(f"- 抽查范围：{len(devices)} 个器件、{len(nets)} 个 net、{len(ports)} 个 port")
    L.append("")
    L.append("## 先看这里")
    L.append("")
    L.append("这份包用来判断 NetlistLabel 的标注是否正确。你不需要相信我；只需要逐项确认或纠正。")
    L.append("")
    L.append("1. accept：预测正确。")
    L.append("2. correct：预测错误，改成你认为正确的值。")
    L.append("3. ambiguous：确实有歧义；不计入 accuracy，单独统计。")
    L.append("4. 不确定时优先标 ambiguous，不要为了覆盖率硬选一个。")
    L.append("")
    L.append("编辑方式：")
    L.append("")
    L.append("- review.csv：用 Excel/表格软件打开，改 decision 和对应字段，最方便；")
    L.append("- gold.json：改 decision 和 role/class/structural_role 字段；")
    L.append("- 只改 decision 和标签字段，不要改 predicted。")
    L.append("")
    L.append("建议先看“重点确认”，再看“抽查”；端口通常最容易判断，可以先建立信心。")
    L.append("")
    L.append("## 端口")
    L.append("")
    L.append("| 编号 | 端口 | 方向 | 类别 | 接口 | 差分/总线 | 置信度 | 锚点 | 预测依据 |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for index, port in enumerate(ports, start=1):
        diff_bus = port.get("differential_group") or port.get("bus") or "—"
        L.append("| P{index:02d} | {name} | {direction} | {cls} | {interface} | {diff_bus} | {conf:.2f} | {anchors} | {evidence} |".format(index=index, name=port.get("original_name"), direction=port.get("direction"), cls=port.get("class"), interface=port.get("interface"), diff_bus=_esc(diff_bus), conf=float(port.get("confidence", 0.0)), anchors=_esc(", ".join(port.get("anchors", [])[:6]) or "—"), evidence=_esc(_ev(port.get("evidence", [])))))
    L.append("")
    L.append("## 关键尺寸与连接")
    L.append("")
    L.append("| 编号 | 器件 | 行 | W/L (µm) | nf/m | D | G | S | B |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for index, device in enumerate(devices, start=1):
        terminals = device.get("terminals", {})
        mos = device.get("kind") == "mos"
        wl = f"{device.get('width_um', 0):g}/{device.get('l_um', 0):g}" if mos else "—"
        nfm = f"{device.get('nf', 1)}/{device.get('m', 1)}" if mos else "—"
        L.append(
            "| D{index:02d} | {name} | {line} | {wl} | {nfm} | {d} | {g} | {s} | {b} |".format(
                index=index, name=device.get("name"), line=device.get("line_no") or "—",
                wl=wl, nfm=nfm,
                d=terminals.get("d", "—"), g=terminals.get("g", "—"),
                s=terminals.get("s", "—"), b=terminals.get("b", "—"),
            )
        )
    L.append("")
    L.append("## 重点确认（低置信度 / 有歧义 / 高影响）")
    L.append("")
    if focus_devices:
        _device_table(L, focus_devices)
    else:
        L.append("没有重点器件。")
    L.append("")
    L.append("## 抽查（高置信度，用来检验自动接受部分）")
    L.append("")
    if sample_devices:
        _device_table(L, sample_devices)
    else:
        L.append("没有抽查器件。")
    L.append("")
    L.append("## 重点 net")
    L.append("")
    if focus_nets:
        _net_table(L, focus_nets)
    else:
        L.append("没有重点 net。")
    L.append("")
    L.append("## 抽查 net")
    L.append("")
    if sample_nets:
        _net_table(L, sample_nets)
    else:
        L.append("没有抽查 net。")
    L.append("")
    L.append("## 网表上下文")
    L.append("")
    L.append("器件行号对应源文件；net 的锚点表示它连接到的器件端子。")
    L.append("")
    for device in devices:
        L.append(f"- {device.get('name')}（第 {device.get('line_no') or 0} 行）：{_line(device, source_lines)}")
    L.append("")
    for net in nets:
        L.append(f"- {net.get('original_name')}：{', '.join(net.get('anchors', [])[:10]) or '—'}")
    L.append("")
    L.append("## 怎么评分")
    L.append("")
    L.append("    python3 -m netlistlabel evaluate \\")
    L.append("      out/v02_ldo/annotation.json \\")
    L.append("      review/ldo_quick/review.csv \\")
    L.append("      --out out/eval/ldo_quick")
    L.append("")
    L.append("结果会给出 strict/lenient accuracy、confusion、review rate、auto precision。")
    L.append("这是抽样结果，不是全局准确率；但它能告诉你错在哪里、错多少。")
    L.append("")
    return "\n".join(L)


def _device_table(lines: list[str], devices: list[dict[str, Any]]) -> None:
    lines.append("| 编号 | 器件 | 行号 | 预测 | 匹配/分组 | top/margin | 置信度 | 复核 | 证据 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for index, device in enumerate(devices, start=1):
        lines.append("| D{index:02d} | {name} | {line_no} | {role} | {match}/{group} | {top:.2f}/{margin:.2f} | {conf:.2f} | {review} | {evidence} |".format(index=index, name=device.get("name"), line_no=device.get("line_no") or "—", role=device.get("role"), match=device.get("match") or "—", group=device.get("group") or "—", top=float(device.get("top_score", 0.0)), margin=float(device.get("margin", 0.0)), conf=float(device.get("confidence", 0.0)), review=device.get("review"), evidence=_esc(_ev(device.get("evidence", []), 3))))


def _net_table(lines: list[str], nets: list[dict[str, Any]]) -> None:
    lines.append("| 编号 | net | 类别/结构角色 | block | 置信度 | 复核 | 证据 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for index, net in enumerate(nets, start=1):
        lines.append("| N{index:02d} | {name} | {cls}/{role} | {block} | {conf:.2f} | {review} | {evidence} |".format(index=index, name=net.get("original_name"), cls=net.get("class"), role=net.get("structural_role"), block=net.get("block") or "—", conf=float(net.get("confidence", 0.0)), review=net.get("review"), evidence=_esc(_ev(net.get("evidence", [])))))
