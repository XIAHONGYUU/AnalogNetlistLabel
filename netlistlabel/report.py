"""JSON and Markdown serialization."""

from __future__ import annotations

import json
from pathlib import Path

from .model import Annotation


def write_json(annotation: Annotation, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(annotation.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def _escape(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _review_name(item: dict[str, object]) -> str:
    return str(item.get("name") or item.get("device") or "—")


def render_markdown(annotation: Annotation) -> str:
    design = annotation.design
    coverage = annotation.coverage
    lines: list[str] = []
    lines.append(f"# NetlistLabel 标注 — {design.get('name', 'design')}")
    lines.append("")
    lines.append(
        "> 这是**语义 overlay 提案**，不是模拟 owner 已确认的事实。"
        "原始名字保留；规范名只是可选建议；review 列与文末 review queue 需要人工确认。"
    )
    lines.append("")
    lines.append("## 设计概览")
    lines.append("")
    lines.append(f"- 源文件: {design.get('source', '')}")
    lines.append(f"- 子电路: {design.get('subckt', '')}")
    lines.append(f"- 端口: {', '.join(design.get('ports', [])) or '—'}")
    lines.append(f"- 电源/地轨: {', '.join(design.get('rails', [])) or '—'}")
    stats = design.get("stats", {})
    lines.append(
        "- 器件: {devices} ({mos} MOS, {caps} C, {resistors} R, {subckts} X); "
        "端口: {ports}; net: {nets}; 功能块: {blocks}".format(
            devices=stats.get("devices", 0),
            mos=stats.get("mos", 0),
            caps=stats.get("caps", 0),
            resistors=stats.get("resistors", 0),
            subckts=stats.get("subckts", 0),
            ports=stats.get("ports", 0),
            nets=stats.get("nets", 0),
            blocks=stats.get("blocks", 0),
        )
    )
    lines.append("")
    lines.append("## 覆盖率")
    lines.append("")
    lines.append("| 指标 | 值 |")
    lines.append("| --- | --- |")
    lines.append(f"| 端口类别覆盖率 | {coverage.get('ports_classified', 0)}/{coverage.get('ports_total', 0)} = {coverage.get('port_class_coverage', 0):.1%} |")
    lines.append(f"| 器件 role 覆盖率 | {coverage.get('roles_known', 0)}/{coverage.get('devices_total', 0)} = {coverage.get('role_coverage', 0):.1%} |")
    lines.append(f"| MOS role 覆盖率 | {coverage.get('mos_roles_known', 0)}/{coverage.get('mos_total', 0)} = {coverage.get('mos_role_coverage', 0):.1%} |")
    lines.append(f"| net 类别覆盖率 | {coverage.get('nets_class_known', 0)}/{coverage.get('nets_total', 0)} = {coverage.get('net_class_coverage', 0):.1%} |")
    lines.append(f"| net 结构角色覆盖率 | {coverage.get('nets_role_known', 0)}/{coverage.get('nets_total', 0)} = {coverage.get('net_role_coverage', 0):.1%} |")
    lines.append(f"| 匹配组器件 | {coverage.get('matched_devices', 0)} = {coverage.get('match_coverage', 0):.1%} |")
    lines.append(f"| 待确认项 | {coverage.get('review_items', 0)} (端口 {coverage.get('port_review_items', 0)}, net {coverage.get('net_review_items', 0)}) |")
    lines.append(f"| 平均置信度 | 器件 {coverage.get('mean_confidence', 0):.2f}, 端口 {coverage.get('mean_port_confidence', 0):.2f}, net {coverage.get('mean_net_confidence', 0):.2f} |")
    structures = coverage.get("structure_counts", {})
    if structures:
        lines.append(f"| 结构统计 | {', '.join(f'{key}: {value}' for key, value in structures.items())} |")
    lines.append("")

    lines.append("## 端口")
    lines.append("")
    lines.append("| 端口 | 方向 | 类别 | 接口 | 数量 | 极性 | 差分/总线 | 置信度 | 复核 | 证据 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for port in annotation.ports:
        diff_bus = port.differential_group or port.bus or "—"
        lines.append(
            "| {name} | {direction} | {cls} | {interface} | {quantity} | {polarity} | {diff_bus} | {conf:.2f} | {review} | {evidence} |".format(
                name=port.original_name,
                direction=port.direction,
                cls=port.electrical_class,
                interface=port.interface,
                quantity=port.quantity,
                polarity=port.polarity,
                diff_bus=_escape(diff_bus),
                conf=port.confidence,
                review=port.review,
                evidence=_escape("; ".join(port.evidence[:3])),
            )
        )
    lines.append("")

    lines.append("## Net")
    lines.append("")
    lines.append("| net | 端口 | 类别 | 结构角色 | 差分/总线 | block | 置信度 | 复核 | 证据 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for net in annotation.nets:
        diff_bus = net.differential_group or net.bus or "—"
        lines.append(
            "| {name} | {port} | {cls} | {role} | {diff_bus} | {block} | {conf:.2f} | {review} | {evidence} |".format(
                name=net.original_name,
                port="yes" if net.is_port else "—",
                cls=net.electrical_class,
                role=net.structural_role,
                diff_bus=_escape(diff_bus),
                block=net.block or "—",
                conf=net.confidence,
                review=net.review,
                evidence=_escape("; ".join(net.evidence[:2])),
            )
        )
    lines.append("")

    lines.append("## 功能块")
    lines.append("")
    lines.append("| block | 标签 | 器件 | 置信度 | 证据 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for block in annotation.blocks:
        lines.append(
            "| {id} | {label} | {devices} | {conf:.2f} | {evidence} |".format(
                id=block.id,
                label=_escape(block.label),
                devices=", ".join(block.devices),
                conf=block.confidence,
                evidence=_escape("; ".join(block.evidence[:3])),
            )
        )
    lines.append("")

    lines.append("## 器件")
    lines.append("")
    lines.append("| 器件 | 类型 | W/L (µm) | nf/m | D | G | S | B | role | group | match | 置信度 | 复核 | 证据 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for device in annotation.devices:
        evidence = "; ".join(device.evidence[:3])
        terminals = device.terminals
        mos = device.kind == "mos"
        wl = f"{device.width_um:g}/{device.l_um:g}" if mos else "—"
        nfm = f"{device.nf}/{device.m}" if mos else "—"
        lines.append(
            "| {name} | {dtype} | {wl} | {nfm} | {d} | {g} | {s} | {b} | {role} | {group} | {match} | {conf:.2f} | {review} | {evidence} |".format(
                name=device.name,
                dtype=device.dtype,
                wl=wl,
                nfm=nfm,
                d=terminals.get("d", "—"),
                g=terminals.get("g", "—"),
                s=terminals.get("s", "—"),
                b=terminals.get("b", "—"),
                role=device.role,
                group=device.group or "—",
                match=device.match or "—",
                conf=device.confidence,
                review=device.review,
                evidence=_escape(evidence),
            )
        )
    lines.append("")

    lines.append("## 待确认队列")
    lines.append("")
    if not annotation.review_queue:
        lines.append("没有待确认项。")
    else:
        lines.append("| 类型 | 名称 | role | group | 原因 | 备选 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for item in annotation.review_queue:
            alternatives = "; ".join(
                f"{alt.get('role') or alt.get('label')} ({alt.get('confidence', 0):.2f})"
                for alt in item.get("alternatives", [])
            ) or "—"
            lines.append(
                "| {kind} | {name} | {role} | {group} | {reasons} | {alts} |".format(
                    kind=item.get("kind", "—"),
                    name=_review_name(item),
                    role=item.get("role") or "—",
                    group=item.get("group") or "—",
                    reasons=_escape("; ".join(item.get("reasons", []))),
                    alts=_escape(alternatives),
                )
            )
    lines.append("")

    if annotation.warnings:
        lines.append("## 警告")
        lines.append("")
        for warning in annotation.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    lines.append("## 限制")
    lines.append("")
    lines.append("- 只读拓扑，不读仿真波形、不计算小信号参数。")
    lines.append("- 不展开层次子电路；未展开的 subckt 应标为黑盒，当前版本尚未完全实现。")
    lines.append("- 不把 model/W/L 换算成电容或电阻值；缺省值会标为 value_known: false。")
    lines.append("- 功能块边界是提案；边界器件（如第二级偏置二极管）可能落在相邻块。")
    lines.append("- 规范名是可选建议；原始名字永远是下游身份。")
    lines.append("- a2l_role 是显式映射；pass_device→output_stage，feedback/logic 无 a2l 对应。")
    lines.append("")
    return "\n".join(lines)


def write_markdown(annotation: Annotation, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_markdown(annotation), encoding="utf-8")
    return target
