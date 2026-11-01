"""Functional-block aggregation.

The block layer is intentionally coarse and explainable. It does not try to
recover a full hierarchy; it answers: which devices participate in the signal
path, the output stage, bias/reference/startup, control, and feedback?

Every block is a *proposal*. Devices can remain in `UNKNOWN`/`PASSIVE`.
"""

from __future__ import annotations

import re
from collections import deque

from .facts import DesignFacts, mos_net

BIAS_PORT_RE = re.compile(r"(^|_)(bias|nbias|pbias|vbias|ibias|iref)(_|$)", re.I)
from .model import Block, DeviceAnnotation, PortAnnotation

CONTROL_ROLES = {"logic", "enable_switch", "adj_switch", "switch"}
BIAS_ROLES = {"current_mirror", "cascode", "bias", "reference"}


def assign_blocks(
    facts: DesignFacts,
    annotations: list[DeviceAnnotation],
    ports: list[PortAnnotation] | None = None,
) -> list[Block]:
    by_name = {annotation.name: annotation for annotation in annotations}
    blocks: list[Block] = []

    signal = _signal_path(facts, ports)
    output = _output_region(facts, signal)
    amplifier = signal - output

    if amplifier:
        blocks.append(
            _make_block(
                "AMP",
                "信号路径放大级",
                "amplifier",
                amplifier,
                facts,
                by_name,
                [
                    "reachable from non-rail, non-control input ports through gate/source/drain edges",
                    "excludes the pass device and its immediate gate-drive network",
                ],
            )
        )
    if output:
        blocks.append(
            _make_block(
                "OUT",
                "输出/功率级",
                "output",
                output,
                facts,
                by_name,
                [
                    "contains the pass device or a device on its gate-drive net",
                ],
            )
        )

    assigned = set(amplifier) | set(output)

    bias_candidates = {
        annotation.name
        for annotation in annotations
        if annotation.role in BIAS_ROLES and annotation.name not in assigned
    }
    startup = _grow_by_nets(
        facts,
        {name for name in bias_candidates if _has_hint(facts, name, ("start", "kick", "por"))},
        bias_candidates,
        level=2,
    )
    reference = _grow_by_nets(
        facts,
        {
            name
            for name in bias_candidates - startup
            if _has_hint(facts, name, ("ref", "vref", "bandgap", "bg"))
        },
        bias_candidates - startup,
        level=2,
    )
    bias = bias_candidates - startup - reference

    if bias:
        blocks.append(
            _make_block(
                "BIAS",
                "偏置网络",
                "bias",
                bias,
                facts,
                by_name,
                ["mirror/cascode/bias devices outside the signal path"],
            )
        )
    if reference:
        blocks.append(
            _make_block(
                "REF",
                "基准/参考网络",
                "reference",
                reference,
                facts,
                by_name,
                ["devices touching a ref/vref-like net, grown through source/drain sharing"],
            )
        )
    if startup:
        blocks.append(
            _make_block(
                "START",
                "启动/踢偏网络",
                "startup",
                startup,
                facts,
                by_name,
                ["devices touching a start/kick/por-like net, grown through source/drain sharing"],
            )
        )
    assigned |= bias_candidates

    control_names = {
        annotation.name
        for annotation in annotations
        if annotation.role in CONTROL_ROLES and annotation.name not in assigned
    }
    enable = {
        name
        for name in control_names
        if _control_kind(facts, by_name[name]) == "enable"
    }
    select = {
        name
        for name in control_names
        if _control_kind(facts, by_name[name]) == "select"
    }
    other_control = control_names - enable - select

    if enable:
        blocks.append(
            _make_block(
                "CTRL_EN",
                "使能/掉电控制",
                "control",
                enable,
                facts,
                by_name,
                ["gate net propagates from an enable-like port or inverter"],
            )
        )
    if select:
        blocks.append(
            _make_block(
                "CTRL_SEL",
                "选择/Trim 控制",
                "control",
                select,
                facts,
                by_name,
                ["gate net propagates from a select/trim-like port or inverter"],
            )
        )
    if other_control:
        blocks.append(
            _make_block(
                "CTRL",
                "控制开关",
                "control",
                other_control,
                facts,
                by_name,
                ["switching devices whose control function is unresolved"],
            )
        )
    assigned |= control_names

    feedback = {
        annotation.name
        for annotation in annotations
        if annotation.role == "feedback" and annotation.name not in assigned
    }
    if feedback:
        blocks.append(
            _make_block(
                "FB",
                "反馈分压/补偿网络",
                "feedback",
                feedback,
                facts,
                by_name,
                ["passive devices on a divider that drives an amplifier input"],
            )
        )
        assigned |= feedback

    passive = {
        annotation.name
        for annotation in annotations
        if annotation.kind in ("cap", "res", "diode", "bjt", "inductor")
        and annotation.name not in assigned
        and annotation.role not in CONTROL_ROLES
    }
    if passive:
        blocks.append(
            _make_block(
                "PASSIVE",
                "未归类无源网络",
                "passive",
                passive,
                facts,
                by_name,
                ["passive devices not assigned to a functional block"],
            )
        )
        assigned |= passive

    unknown = {
        annotation.name
        for annotation in annotations
        if annotation.name not in assigned and annotation.role == "unknown"
    }
    if unknown:
        blocks.append(
            _make_block(
                "UNKNOWN",
                "未解析器件",
                "unknown",
                unknown,
                facts,
                by_name,
                ["no structural signature matched"],
            )
        )

    # Any remaining devices (rare) go to a catch-all so the partition is total.
    remaining = {annotation.name for annotation in annotations} - {
        name for block in blocks for name in block.devices
    }
    if remaining:
        blocks.append(
            _make_block(
                "OTHER",
                "其他器件",
                "unknown",
                remaining,
                facts,
                by_name,
                ["not covered by the other block rules"],
            )
        )

    for block in blocks:
        for name in block.devices:
            by_name[name].group = block.id
    return blocks


def _signal_path(facts: DesignFacts, ports: list[PortAnnotation] | None = None) -> set[str]:
    port_by_name = {
        getattr(port, "original_name", ""): port for port in (ports or [])
    }
    seeds: set[str] = set()
    for port in facts.ports:
        if port in facts.rails:
            continue
        annotation = port_by_name.get(port)
        if annotation is not None:
            electrical_class = getattr(annotation, "electrical_class", "unknown")
            direction = getattr(annotation, "direction", "unknown")
            if electrical_class in ("power", "ground", "reference", "bias", "control", "clock", "reset", "enable", "select", "interface"):
                continue
            if direction in ("output", "power", "ground"):
                continue
        elif port in facts.control or BIAS_PORT_RE.search(port):
            continue
        for device in facts.mos_on(port, "g"):
            if device.name not in facts.pass_devices:
                seeds.add(device.name)
    if not seeds:
        for pair in facts.pairs:
            seeds.update((pair.a, pair.b))

    seen = set(seeds)
    queue: deque[str] = deque(seeds)
    while queue:
        name = queue.popleft()
        device = facts.by_name(name)
        if device is None:
            continue
        pair = facts.pair_of.get(name)
        if pair is not None:
            for partner in (pair.a, pair.b, pair.tail):
                if partner and partner not in seen:
                    seen.add(partner)
                    queue.append(partner)
        for net in {mos_net(device, "d"), mos_net(device, "s")}:
            if not net or net in facts.rails:
                continue
            for nxt in facts.mos_on(net, "g"):
                if nxt.name in seen or mos_net(nxt, "g") in facts.control:
                    continue
                seen.add(nxt.name)
                queue.append(nxt.name)
            for nxt in facts.mos_on(net, "s"):
                if nxt.name in seen:
                    continue
                if nxt.name in facts.cascodes or nxt.name in facts.pass_devices:
                    seen.add(nxt.name)
                    queue.append(nxt.name)
            for nxt in facts.mos_on(net, "d"):
                if nxt.name in seen:
                    continue
                if mos_net(nxt, "g") in facts.control:
                    continue
                if nxt.name in facts.diode and mos_net(nxt, "s") in facts.rails:
                    # A diode-connected bias reference to a rail is support, not
                    # a stage load. Keep it out of the signal path.
                    continue
                seen.add(nxt.name)
                queue.append(nxt.name)
    return seen


def _output_region(facts: DesignFacts, signal: set[str]) -> set[str]:
    output = {name for name in facts.pass_devices if name in signal}
    if not output:
        output = set(facts.pass_devices)
    pass_gate_nets = {
        mos_net(device, "g")
        for device in facts.mos
        if device.name in facts.pass_devices and mos_net(device, "g")
    }
    for name in signal:
        device = facts.by_name(name)
        if device is None:
            continue
        if {mos_net(device, "d"), mos_net(device, "s")} & pass_gate_nets:
            output.add(name)
        elif (
            {mos_net(device, "d"), mos_net(device, "s")} & facts.output_ports
            and device.width_um >= 2 * facts.median_width
        ):
            output.add(name)
    return output


def _has_hint(facts: DesignFacts, name: str, tokens: tuple[str, ...]) -> bool:
    device = facts.by_name(name)
    if device is None:
        return False
    for net in device.nodes:
        low = net.lower()
        if any(token in low for token in tokens):
            return True
    return False


def _grow_by_nets(
    facts: DesignFacts,
    seeds: set[str],
    universe: set[str],
    *,
    level: int,
) -> set[str]:
    if not seeds:
        return set()
    seen = set(seeds)
    frontier = set(seeds)
    for _ in range(level):
        next_frontier: set[str] = set()
        for name in frontier:
            device = facts.by_name(name)
            if device is None:
                continue
            for net in {mos_net(device, "d"), mos_net(device, "s")}:
                if not net or net in facts.rails:
                    continue
                # Do not let a local start/reference chain leak through a
                # global bias bus into the rest of the bias network.
                gate_fanout = sum(1 for _name, term in facts.nets.get(net, []) if term == "g")
                if gate_fanout >= 4:
                    continue
                for other in facts.mos_on(net):
                    if other.name in universe and other.name not in seen:
                        seen.add(other.name)
                        next_frontier.add(other.name)
        frontier = next_frontier
        if not frontier:
            break
    return seen


def _control_kind(facts: DesignFacts, annotation: DeviceAnnotation) -> str:
    device = facts.by_name(annotation.name)
    if device is None:
        return ""
    if annotation.role == "enable_switch":
        return "enable"
    if annotation.role == "adj_switch":
        return "select"
    gate = mos_net(device, "g") if device.is_mos else ""
    if gate in facts.control:
        return facts.control[gate]
    # Logic/level-shift instances: classify by the control net they drive.
    if device.kind == "subckt" and device.nodes:
        out = device.nodes[-1]
        if out in facts.control:
            return facts.control[out]
    if annotation.role == "logic":
        for net in device.nodes:
            if net in facts.control:
                return facts.control[net]
    return ""


def _make_block(
    block_id: str,
    label: str,
    kind: str,
    names: set[str],
    facts: DesignFacts,
    by_name: dict[str, DeviceAnnotation],
    evidence: list[str],
) -> Block:
    ordered = sorted(names, key=_natural_key)
    nets: set[str] = set()
    ports: set[str] = set()
    for name in ordered:
        device = facts.by_name(name)
        if device is None:
            continue
        for net in device.nodes:
            if net and net not in facts.rails:
                nets.add(net)
                if net in facts.ports:
                    ports.add(net)
    confidences = [by_name[name].confidence for name in ordered if name in by_name]
    confidence = sum(confidences) / len(confidences) if confidences else 0.0
    roles = {by_name[name].role for name in ordered if name in by_name}
    detail = [f"roles: {', '.join(sorted(roles))}"]
    return Block(
        id=block_id,
        label=label,
        kind=kind,
        devices=ordered,
        nets=sorted(nets, key=_natural_key),
        ports=sorted(ports, key=_natural_key),
        confidence=confidence,
        evidence=evidence + detail,
    )


def _natural_key(value: str) -> list[object]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]