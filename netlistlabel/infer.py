"""Device-level role inference and annotation assembly."""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

from .blocks import assign_blocks
from .facts import DesignFacts, MirrorCluster, build_facts, mos_net
from .model import Alternative, Annotation, Block, Candidate, DeviceAnnotation, NetAnnotation, PortAnnotation
from .nets import classify_nets
from .ports import classify_ports
from .spice import Device, Netlist

SCHEMA_VERSION = "0.2"


def annotate(netlist: Netlist) -> Annotation:
    facts = build_facts(netlist)
    ports = classify_ports(netlist, facts)
    feedback = _detect_feedback(facts)
    pass_gate_nets = {
        mos_net(device, "g")
        for device in facts.mos
        if device.name in facts.pass_devices and mos_net(device, "g")
    }

    annotations: list[DeviceAnnotation] = []
    for device in netlist.devices:
        if device.is_mos:
            annotation = _propose_mos(device, facts, feedback, pass_gate_nets)
        elif device.kind == "cap":
            annotation = _propose_cap(device, facts)
        elif device.kind == "res":
            annotation = _propose_res(device, facts, feedback)
        elif device.kind == "diode":
            annotation = _base(device, "bias", 0.65)
            annotation.structures.append("diode_connected")
            annotation.evidence.append(f"two-terminal diode {device.name}")
        elif device.kind == "bjt":
            annotation = _propose_bjt(device, facts)
        elif device.kind == "subckt":
            annotation = _propose_subckt(device, facts)
        elif device.kind == "inductor":
            annotation = _base(device, "passive", 0.4)
            annotation.evidence.append("inductor; function not resolved from topology")
        else:
            annotation = _base(device, "unknown", 0.0)
            annotation.evidence.append("unsupported device kind; no semantic proposal")
        if device.is_mos and _is_source_follower(device, facts):
            if "source_follower" not in annotation.structures:
                annotation.structures.append("source_follower")
            annotation.evidence.append(
                "drain is at a rail/AC ground; source drives a load or the next gate (common-drain/source follower)"
            )
        if device.is_mos and _is_common_source(device, facts):
            if "common_source" not in annotation.structures:
                annotation.structures.append("common_source")
            annotation.evidence.append(
                "source is at a rail; drain drives a load/current source (common-source stage)"
            )
        annotations.append(annotation)

    blocks = assign_blocks(facts, annotations, ports)
    nets = classify_nets(netlist, facts, ports, blocks)
    _assign_matches(facts, annotations, blocks, feedback)
    _finalize(annotations)
    return _assemble(facts, annotations, blocks, ports, nets)


def _is_source_follower(device: Device, facts: DesignFacts) -> bool:
    drain, gate, source = mos_net(device, "d"), mos_net(device, "g"), mos_net(device, "s")
    if not drain or not gate or not source:
        return False
    if drain not in facts.rails or source in facts.rails or gate in facts.rails:
        return False
    loads = [
        other
        for other in facts.mos
        if other.name != device.name
        and mos_net(other, "d") == source
        and (mos_net(other, "s") in facts.rails or other.name in facts.mirror_of)
    ]
    next_gates = facts.mos_on(source, "g")
    return bool(loads or next_gates)


def _is_common_source(device: Device, facts: DesignFacts) -> bool:
    drain, gate, source = mos_net(device, "d"), mos_net(device, "g"), mos_net(device, "s")
    if not drain or not gate or not source:
        return False
    if source not in facts.rails or drain in facts.rails or gate in facts.rails:
        return False
    if drain == gate:
        return False
    loads = [
        other
        for other in facts.mos
        if other.name != device.name
        and mos_net(other, "d") == drain
        and (mos_net(other, "s") in facts.rails or other.name in facts.cascodes)
    ]
    return bool(loads)


def _base(device: Device, role: str, confidence: float) -> DeviceAnnotation:
    value_known = True
    cap_pf = 0.0
    res_ohm = 0.0
    if device.kind == "cap":
        cap_pf = device.cap_pf
        value_known = cap_pf > 0
    elif device.kind == "res":
        res_ohm = device.res_ohm
        value_known = res_ohm > 0
    return DeviceAnnotation(
        name=device.name,
        kind=device.kind,
        dtype=device.type,
        model=device.model,
        terminals=dict(device.terminals),
        role=role,
        confidence=confidence,
        width_um=device.width_um,
        l_um=device.l_um,
        nf=device.nf,
        m=device.m,
        cap_pf=cap_pf,
        res_ohm=res_ohm,
        value_known=value_known,
        line_no=device.line_no,
    )


def _propose_mos(
    device: Device,
    facts: DesignFacts,
    feedback: dict[str, dict[str, object]],
    pass_gate_nets: set[str],
) -> DeviceAnnotation:
    name = device.name
    gate = mos_net(device, "g")
    source = mos_net(device, "s")
    drain = mos_net(device, "d")

    if name in facts.pass_devices:
        annotation = _base(device, "pass_device", facts.pass_devices[name])
        annotation.structures.append("pass")
        annotation.evidence = [
            f"total width {device.width_um:g} um vs median {facts.median_width:g} um",
        ]
        touched = {drain, source} & facts.output_ports
        if touched:
            annotation.evidence.append(f"terminal on output port {sorted(touched)[0]}")
        annotation.notes = "large pass device; confirm SOA/EM and finger count in layout"
        return annotation

    pair = facts.pair_of.get(name)
    if pair is not None:
        annotation = _base(device, "input_pair", pair.confidence)
        annotation.structures.append("diff_pair")
        annotation.evidence = list(pair.evidence)
        annotation.alternatives.append(
            Alternative("bias", 0.2, "a source-coupled pair can also be a bias/current branch")
        )
        return annotation

    if name in facts.tails:
        annotation = _base(device, "tail_current", 0.9)
        annotation.structures.append("tail")
        annotation.evidence = [
            f"drain {drain} is the common source of a differential pair",
            f"source {source} is a rail",
        ]
        return annotation

    if name in facts.cascodes:
        lower = facts.cascodes[name]
        annotation = _base(device, "cascode", 0.82)
        annotation.structures.extend(["cascode", "stack_member"])
        annotation.evidence = [
            f"source {source} is the drain of {lower}",
            f"gate {gate} is bias-like and not the source/drain of this stack",
        ]
        annotation.alternatives.append(
            Alternative("current_mirror", 0.25, "the stack may be a mirror branch rather than a cascode")
        )
        return annotation

    if gate and gate in facts.control:
        inverter = facts.inverter_of.get(name)
        mux = facts.mux_of.get(name)
        if inverter is not None:
            annotation = _base(device, "logic", inverter.confidence)
            annotation.structures.append("inverter")
            annotation.evidence = list(inverter.evidence)
            annotation.notes = "complementary pair used as an inverter/level driver"
            kind = facts.control.get(gate, "")
            if kind == "enable":
                annotation.a2l_role_override = "enable_switch"
            elif kind == "select":
                annotation.a2l_role_override = "adj_switch"
            return annotation
        if mux is not None:
            annotation = _base(device, "adj_switch", mux.confidence)
            annotation.structures.extend(["mux", "control_switch"])
            annotation.evidence = list(mux.evidence)
            return annotation
        kind = facts.control[gate]
        role = "enable_switch" if kind == "enable" else "adj_switch" if kind == "select" else "switch"
        annotation = _base(device, role, 0.8 if role != "switch" else 0.6)
        annotation.structures.append("control_switch")
        annotation.evidence = [
            f"gate {gate} is a {kind or 'control'} net",
        ] + facts.control_evidence.get(gate, [])
        return annotation

    cluster = facts.mirror_of.get(name)
    if cluster is not None:
        annotation = _base(device, "current_mirror", cluster.confidence)
        if cluster.reference == name:
            annotation.structures.extend(["mirror_reference", "diode_connected"])
            annotation.evidence = [
                f"diode-connected reference of {cluster.id}",
            ] + cluster.evidence
        else:
            annotation.structures.append("mirror_member")
            annotation.evidence = list(cluster.evidence)
        if cluster.reference is None or cluster.confidence < 0.6:
            annotation.alternatives.append(
                Alternative("bias", 0.4, "large gate/source fan-out may be bias distribution, not a matched mirror")
            )
            annotation.notes = "confirm whether this device belongs to a matched mirror or only to the bias fan-out"
        return annotation

    if name in facts.diode:
        annotation = _base(device, "bias", 0.72)
        annotation.structures.append("diode_connected")
        annotation.evidence = [facts.diode[name]]
        annotation.alternatives.append(
            Alternative("current_mirror", 0.45, "diode-connected devices often set a mirror reference")
        )
        return annotation

    # A gain device whose drain/source is an output port is an output stage.
    # Current mirrors are handled above so a mirror load does not become one.
    if (
        {drain, source} & facts.output_ports
        and device.width_um >= 2 * facts.median_width
    ):
        annotation = _base(device, "output_stage", 0.72)
        annotation.structures.append("output_stage")
        annotation.evidence = [
            f"terminal on output port {sorted({drain, source} & facts.output_ports)[0]}",
            f"total width {device.width_um:g} um vs median {facts.median_width:g} um",
        ]
        return annotation

    # A source on the pass-device gate net is the pass driver.
    if source and source in pass_gate_nets:
        annotation = _base(device, "output_stage", 0.72)
        annotation.structures.append("pass_driver")
        annotation.evidence = [
            f"source {source} is the gate net of a pass device",
            f"gate {gate} is the high-impedance driver input",
        ]
        return annotation

    # A mirror with source degeneration: same mirror gate as a reference, but
    # the source is not the reference source.
    if gate and gate not in facts.rails and gate not in facts.control:
        same_gate = [
            other
            for other in facts.mos
            if other.name != name
            and mos_net(other, "g") == gate
            and other.type == device.type
            and mos_net(other, "s") in facts.rails
        ]
        mirror_ref = any(
            other.name in facts.diode or other.name in facts.mirror_of for other in same_gate
        )
        if mirror_ref and facts.bias_like(gate):
            annotation = _base(device, "current_mirror", 0.62)
            annotation.structures.append("mirror_candidate")
            annotation.evidence = [
                f"shares mirror gate {gate} with {', '.join(other.name for other in same_gate[:4])}",
                f"source {source} differs from the rail-tied mirror source; possible degeneration",
            ]
            annotation.notes = "mirror with source degeneration or a separate branch; confirm ratio"
            return annotation

    if gate and facts.bias_like(gate):
        annotation = _base(device, "bias", 0.55)
        annotation.evidence = [
            f"gate {gate} is a bias-like net (multiple gates and/or a diode reference)"
        ]
        annotation.alternatives.append(
            Alternative("current_mirror", 0.35, "may be a mirror branch whose source differs")
        )
        return annotation

    if source and source in facts.rails and gate and gate not in facts.control:
        annotation = _base(device, "bias", 0.42)
        annotation.structures.append("supply")
        annotation.evidence = [f"source {source} is a rail; no pair/mirror/control signature"]
        annotation.notes = "low-confidence bias/current-source candidate"
        return annotation

    annotation = _base(device, "unknown", 0.0)
    annotation.evidence = ["no pair, mirror, cascode, control, pass or bias signature matched"]
    return annotation


def _propose_cap(device: Device, facts: DesignFacts) -> DeviceAnnotation:
    nodes = device.nodes[:2]
    rails = [net for net in nodes if net in facts.rails]
    if rails:
        annotation = _base(device, "decap", 0.55 if annotation_value(device) else 0.5)
        annotation.structures.append("cap_to_rail")
        annotation.evidence = [
            f"one terminal on rail {rails[0]}",
            "topology alone cannot distinguish decoupling from compensation/filtering",
        ]
        annotation.alternatives.append(
            Alternative("compensation", 0.35, "a rail-referenced cap can be a compensation or filter cap")
        )
        annotation.notes = _cap_value_note(device)
        return annotation
    annotation = _base(device, "compensation", 0.68)
    annotation.evidence = ["capacitor between two non-rail nets; likely signal-path compensation"]
    annotation.notes = _cap_value_note(device)
    return annotation


def annotation_value(device: Device) -> bool:
    return device.cap_pf > 0


def _cap_value_note(device: Device) -> str:
    if device.cap_pf > 0:
        return f"stated value {device.cap_pf:g} pF"
    return "no capacitance value stated; model/W/L only, not converted into a value"


def _propose_res(
    device: Device,
    facts: DesignFacts,
    feedback: dict[str, dict[str, object]],
) -> DeviceAnnotation:
    if device.name in feedback:
        info = feedback[device.name]
        annotation = _base(device, "feedback", 0.86)
        annotation.structures.append("series_divider")
        annotation.evidence = [
            f"divider node {info['midpoint']} drives gate of {info['gate_device']}",
            f"feedback resistors: {', '.join(info['resistors'])}",  # type: ignore[arg-type]
        ]
        annotation.notes = _res_value_note(device)
        return annotation

    nodes = device.nodes[:2]
    rail_nodes = [net for net in nodes if net in facts.rails]
    if rail_nodes:
        other = nodes[1] if nodes[0] in facts.rails else nodes[0]
        source_devices = facts.mos_on(other, "s")
        if source_devices:
            annotation = _base(device, "bias", 0.7)
            annotation.structures.append("degeneration")
            annotation.evidence = [
                f"one terminal on rail {rail_nodes[0]}",
                f"other terminal {other} is the source of {source_devices[0].name}",
            ]
            annotation.notes = _res_value_note(device)
            return annotation
        annotation = _base(device, "passive", 0.45)
        annotation.evidence = [f"resistor from rail {rail_nodes[0]} to {other}"]
        annotation.notes = _res_value_note(device)
        return annotation

    annotation = _base(device, "passive", 0.4)
    annotation.evidence = ["resistor between non-rail nets; function not resolved"]
    annotation.notes = _res_value_note(device)
    return annotation


def _res_value_note(device: Device) -> str:
    if device.res_ohm > 0:
        return f"stated value {device.res_ohm:g} ohm"
    return "no resistance value stated; model/W/L only, not converted into a value"


def _propose_bjt(device: Device, facts: DesignFacts) -> DeviceAnnotation:
    if device.nodes and len(device.nodes) >= 3 and device.nodes[0] == device.nodes[1]:
        annotation = _base(device, "bias", 0.55)
        annotation.structures.append("diode_connected")
        annotation.evidence = ["collector and base share a net (diode-connected BJT)"]
        return annotation
    annotation = _base(device, "unknown", 0.0)
    annotation.evidence = ["BJT function not resolved from topology"]
    return annotation


def _propose_subckt(device: Device, facts: DesignFacts) -> DeviceAnnotation:
    if device.is_digital_subckt:
        annotation = _base(device, "logic", 0.82)
        annotation.structures.append("level_shift")
        inputs = device.nodes[:-1] if device.nodes else []
        output = device.nodes[-1] if device.nodes else ""
        controlled = [net for net in inputs if net in facts.control]
        annotation.evidence = [
            f"digital/level-shift subcircuit {device.model}",
            f"output {output} driven from {', '.join(controlled) if controlled else 'its inputs'}",
        ]
        if output in facts.control:
            annotation.evidence.append(f"output {output} is a propagated {facts.control[output]} control net")
        return annotation
    annotation = _base(device, "unknown", 0.0)
    annotation.evidence = [
        f"subcircuit instance {device.name} ({device.model}) is not expanded; internal function unresolved"
    ]
    annotation.notes = "hierarchical block; flatten or inspect the subcircuit definition for a role"
    return annotation


def _detect_feedback(facts: DesignFacts) -> dict[str, dict[str, object]]:
    resistors = [device for device in facts.devices if device.kind == "res"]
    by_net: dict[str, list[Device]] = {}
    for device in resistors:
        for net in device.nodes[:2]:
            if net and net not in facts.rails:
                by_net.setdefault(net, []).append(device)

    result: dict[str, dict[str, object]] = {}
    for midpoint, members in by_net.items():
        if len(members) < 2:
            continue
        gate_devices = facts.mos_on(midpoint, "g")
        if not gate_devices:
            continue
        resistors_names = [device.name for device in members]
        for device in members:
            result[device.name] = {
                "midpoint": midpoint,
                "gate_device": gate_devices[0].name,
                "resistors": resistors_names,
            }
    return result


def _assign_matches(
    facts: DesignFacts,
    annotations: list[DeviceAnnotation],
    blocks: list[Block],
    feedback: dict[str, dict[str, object]],
) -> None:
    by_name = {annotation.name: annotation for annotation in annotations}
    block_of = {name: block.id for block in blocks for name in block.devices}

    def add(names: Iterable[str], match_id: str, evidence: str, confidence: float = 0.8) -> None:
        names = [name for name in names if name in by_name]
        if len(names) < 2:
            return
        existing = {by_name[name].match for name in names if by_name[name].match}
        if existing and existing != {match_id}:
            return
        # Never extend a partial group transitively; a match group must be added
        # as one decision, not grown one device at a time.
        if any(by_name[name].match == match_id for name in names) and not all(
            by_name[name].match == match_id for name in names
        ):
            return
        for name in names:
            annotation = by_name[name]
            annotation.match = match_id
            annotation.evidence.append(f"match group {match_id}: {evidence}")
            annotation.confidence = max(annotation.confidence, min(confidence, 0.9))

    for pair in facts.pairs:
        block = block_of.get(pair.a)
        if not block or block_of.get(pair.b) != block:
            continue
        add((pair.a, pair.b), f"DP_{block}", "differential pair with symmetric surroundings", pair.confidence)

        # Symmetric loads on the two drains.
        loads_left = [
            device.name
            for device in facts.mos_on(pair.drains[0], "d")
            if device.name not in (pair.a, pair.b)
        ]
        loads_right = [
            device.name
            for device in facts.mos_on(pair.drains[1], "d")
            if device.name not in (pair.a, pair.b)
        ]
        for left in loads_left:
            for right in loads_right:
                a, b = facts.by_name(left), facts.by_name(right)
                if a is None or b is None:
                    continue
                if a.type != b.type or a.model != b.model:
                    continue
                if mos_net(a, "g") != mos_net(b, "g"):
                    continue
                if block_of.get(left) != block or block_of.get(right) != block:
                    continue
                add((left, right), f"LOAD_{block}", "same type/model/gate on the two pair drains", 0.85)

    # Cascode pairs in the same block and on the same bias gate.
    groups: dict[tuple[str, str], list[str]] = {}
    for upper in facts.cascodes:
        device = facts.by_name(upper)
        if device is None:
            continue
        key = (block_of.get(upper, ""), mos_net(device, "g"))
        groups.setdefault(key, []).append(upper)
    for (block, _gate), names in groups.items():
        if not block or len(names) != 2:
            continue
        a, b = (facts.by_name(name) for name in names)
        if a is None or b is None or a.type != b.type:
            continue
        if not _similar_width(a.width_um, b.width_um):
            continue
        add(names, f"CAS_{block}", "two cascodes share a bias gate in the same block", 0.8)

    # A degenerated mirror: same gate, rail-referenced partner, source through a resistor.
    for a, b in _same_gate_pairs(facts):
        block = block_of.get(a.name)
        if not block or block_of.get(b.name) != block:
            continue
        if block in ("REF", "START"):
            continue
        ann_a, ann_b = by_name.get(a.name), by_name.get(b.name)
        if ann_a is None or ann_b is None:
            continue
        if {ann_a.role, ann_b.role} - {"current_mirror", "bias"}:
            continue
        if a.type != b.type:
            continue
        ratio = max(a.width_um, b.width_um) / min(a.width_um, b.width_um) if min(a.width_um, b.width_um) > 0 else 1.0
        if ratio > 1.25 and abs(ratio - round(ratio)) > 0.05:
            continue
        if a.name in facts.mirror_of and b.name in facts.mirror_of:
            continue
        one_rail = mos_net(a, "s") in facts.rails or mos_net(b, "s") in facts.rails
        if not one_rail:
            continue
        add((a.name, b.name), f"MIR_{block_of[a.name]}_DEG", "same mirror gate, one source rail-tied and one degenerated", 0.7)

    # Mirror pairs within a block. A large bias fan-out can contain two
    # same-block members; those are the only ones that form a local match.
    for cluster in facts.mirror_clusters:
        per_block: dict[str, list[str]] = {}
        for name in cluster.devices:
            block = block_of.get(name)
            if block:
                per_block.setdefault(block, []).append(name)
        for block, names in per_block.items():
            if len(names) != 2:
                continue
            a, b = facts.by_name(names[0]), facts.by_name(names[1])
            if a is None or b is None or not _similar_width(a.width_um, b.width_um):
                continue
            suffix = re.sub(r"[^A-Za-z0-9]+", "_", cluster.gate).strip("_") or "MIR"
            add(names, f"MIR_{block}_{suffix}", "same mirror gate and source in one block", 0.75)

    for names in _feedback_groups(facts, feedback).values():
        add(names, "FB_DIV", "resistors share a feedback midpoint that drives a pair gate", 0.85)


def _same_gate_pairs(facts: DesignFacts) -> list[tuple[Device, Device]]:
    by_gate: dict[tuple[str, str], list[Device]] = {}
    for device in facts.mos:
        gate = mos_net(device, "g")
        if not gate or gate in facts.rails or gate in facts.control:
            continue
        by_gate.setdefault((device.type, gate), []).append(device)
    result: list[tuple[Device, Device]] = []
    for members in by_gate.values():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                result.append((members[i], members[j]))
    return result


def _feedback_groups(
    facts: DesignFacts, feedback: dict[str, dict[str, object]]
) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for name, info in feedback.items():
        key = str(info["midpoint"])
        groups.setdefault(key, []).append(name)
    return {key: names for key, names in groups.items() if len(names) >= 2}


def _similar_width(a: float, b: float) -> bool:
    if a <= 0 or b <= 0:
        return a == b
    return max(a, b) / min(a, b) <= 1.25


UNKNOWN_BASELINE = 0.35
HARD_ABSTAIN = 0.45
SOFT_CONFIRM = 0.70
AMBIGUOUS_MARGIN = 0.10


def _finalize(annotations: list[DeviceAnnotation]) -> None:
    for annotation in annotations:
        if not annotation.evidence:
            annotation.evidence.append("no evidence recorded (annotation bug)")

        by_label = {
            candidate.label: candidate
            for candidate in annotation.candidates
            if candidate.kind == "role"
        }
        if annotation.role not in by_label:
            by_label[annotation.role] = Candidate(
                label=annotation.role,
                score=annotation.confidence,
                kind="role",
                evidence=list(annotation.evidence),
                negative_evidence=list(annotation.negative_evidence),
            )
        for alternative in annotation.alternatives:
            if alternative.role not in by_label:
                by_label[alternative.role] = Candidate(
                    label=alternative.role,
                    score=alternative.confidence,
                    kind="role",
                    reason=alternative.reason,
                )
        if "unknown" not in by_label:
            by_label["unknown"] = Candidate(
                label="unknown",
                score=UNKNOWN_BASELINE,
                kind="role",
                evidence=["conservative abstention baseline"],
                reason="use when the top structural role is not clearly supported",
            )

        candidates = sorted(by_label.values(), key=lambda candidate: candidate.score, reverse=True)
        annotation.candidates = candidates
        top = candidates[0]
        second = candidates[1] if len(candidates) > 1 else Candidate("unknown", 0.0, kind="role")
        annotation.top_score = top.score
        annotation.margin = max(0.0, top.score - second.score)

        notes: list[str] = []
        if top.label != annotation.role and top.score >= HARD_ABSTAIN:
            annotation.review = "confirm"
            notes.append(f"top candidate {top.label} outscores declared role {annotation.role}")
        elif annotation.role != "unknown" and annotation.top_score < HARD_ABSTAIN:
            annotation.role = "unknown"
            annotation.review = "unknown"
            notes.append("hard abstention: top role support below 0.45")
        elif annotation.role == "unknown":
            annotation.review = "unknown"
        elif annotation.margin < AMBIGUOUS_MARGIN and annotation.top_score < 0.80:
            annotation.review = "confirm"
            notes.append(f"ambiguous: margin {annotation.margin:.2f} below 0.10")
        elif annotation.top_score < SOFT_CONFIRM:
            annotation.review = "confirm"
            notes.append(f"soft confirmation: top score {annotation.top_score:.2f} below 0.70")
        else:
            annotation.review = "auto"

        annotation.negative_evidence = list(annotation.negative_evidence)
        if notes:
            annotation.notes = "; ".join(filter(None, [annotation.notes, *notes]))

        if not annotation.semantic_id:
            annotation.semantic_id = "device:" + re.sub(r"[^A-Za-z0-9]+", "_", annotation.name).strip("_").upper()



def _assemble(
    facts: DesignFacts,
    annotations: list[DeviceAnnotation],
    blocks: list[Block],
    ports: list[PortAnnotation],
    nets: list[NetAnnotation],
) -> Annotation:
    review_queue: list[dict[str, object]] = []

    for annotation in annotations:
        reasons: list[str] = []
        if annotation.role == "unknown":
            reasons.append("role unresolved")
        if annotation.top_score < HARD_ABSTAIN:
            reasons.append(f"hard abstention: top score {annotation.top_score:.2f} below 0.45")
        if annotation.margin < AMBIGUOUS_MARGIN:
            reasons.append(f"ambiguous: margin {annotation.margin:.2f} below 0.10")
        if annotation.confidence < 0.7:
            reasons.append(f"confidence {annotation.confidence:.2f} below 0.70")
        if annotation.role == "current_mirror" and not annotation.match and any(
            "bias distribution" in alt.reason for alt in annotation.alternatives
        ):
            reasons.append("mirror vs bias-fan-out ambiguity")
        if annotation.kind == "cap" and not annotation.value_known:
            reasons.append("capacitance value not stated; model W/L was not converted")
        if annotation.role == "input_pair" and not annotation.match:
            reasons.append("input pair has no match group")
        if reasons:
            review_queue.append(
                {
                    "kind": "device",
                    "name": annotation.name,
                    "device": annotation.name,
                    "role": annotation.role,
                    "group": annotation.group or None,
                    "review": annotation.review,
                    "top_score": round(annotation.top_score, 3),
                    "margin": round(annotation.margin, 3),
                    "reasons": reasons,
                    "alternatives": [alt.to_dict() for alt in annotation.alternatives],
                }
            )

    for port in ports:
        reasons: list[str] = list(port.conflicts)
        if port.electrical_class == "unknown":
            reasons.append("port class unresolved")
        if port.confidence < 0.7:
            reasons.append(f"confidence {port.confidence:.2f} below 0.70")
        if port.review != "auto" and not reasons:
            reasons.append("review requested by port classifier")
        if reasons:
            review_queue.append(
                {
                    "kind": "port",
                    "name": port.original_name,
                    "role": port.electrical_class,
                    "interface": port.interface,
                    "direction": port.direction,
                    "group": None,
                    "review": port.review,
                    "reasons": reasons,
                    "alternatives": [
                        {"role": candidate.label, "confidence": candidate.score, "reason": candidate.reason}
                        for candidate in port.candidates[1:]
                    ],
                }
            )

    for net in nets:
        reasons: list[str] = list(net.conflicts)
        if net.electrical_class == "unknown":
            reasons.append("net class unresolved")
        if net.structural_role == "internal" and net.confidence < 0.7:
            reasons.append("internal net has no structural role")
        if net.confidence < 0.7:
            reasons.append(f"confidence {net.confidence:.2f} below 0.70")
        if net.review != "auto" and not reasons:
            reasons.append("review requested by net classifier")
        if reasons:
            review_queue.append(
                {
                    "kind": "net",
                    "name": net.original_name,
                    "role": net.electrical_class,
                    "structural_role": net.structural_role,
                    "group": net.block,
                    "review": net.review,
                    "reasons": reasons,
                    "alternatives": [
                        {"role": candidate.label, "confidence": candidate.score, "reason": candidate.reason}
                        for candidate in net.candidates[1:]
                    ],
                }
            )

    known = [annotation for annotation in annotations if annotation.role != "unknown"]
    mos = [annotation for annotation in annotations if annotation.kind == "mos"]
    mos_known = [annotation for annotation in mos if annotation.role != "unknown"]
    matched = [annotation for annotation in annotations if annotation.match]
    mean_confidence = (
        sum(annotation.confidence for annotation in annotations) / len(annotations)
        if annotations
        else 0.0
    )
    structure_counts = Counter(
        structure for annotation in annotations for structure in annotation.structures
    )

    ports_known = [port for port in ports if port.electrical_class != "unknown"]
    nets_class_known = [net for net in nets if net.electrical_class != "unknown"]
    nets_role_known = [
        net for net in nets if net.structural_role not in ("unknown", "internal")
    ]
    device_auto = sum(1 for annotation in annotations if annotation.review == "auto")
    device_confirm = sum(1 for annotation in annotations if annotation.review == "confirm")
    device_unknown = sum(1 for annotation in annotations if annotation.review == "unknown")
    mean_margin = (
        sum(annotation.margin for annotation in annotations) / len(annotations)
        if annotations
        else 0.0
    )
    mean_port_confidence = (
        sum(port.confidence for port in ports) / len(ports) if ports else 0.0
    )
    mean_net_confidence = (
        sum(net.confidence for net in nets) / len(nets) if nets else 0.0
    )

    coverage = {
        "devices_total": len(annotations),
        "roles_known": len(known),
        "role_coverage": round(len(known) / len(annotations), 3) if annotations else 0.0,
        "mos_total": len(mos),
        "mos_roles_known": len(mos_known),
        "mos_role_coverage": round(len(mos_known) / len(mos), 3) if mos else 0.0,
        "matched_devices": len(matched),
        "match_coverage": round(len(matched) / len(annotations), 3) if annotations else 0.0,
        "device_auto": device_auto,
        "device_confirm": device_confirm,
        "device_unknown": device_unknown,
        "mean_margin": round(mean_margin, 3),
        "ports_total": len(ports),
        "ports_classified": len(ports_known),
        "port_class_coverage": round(len(ports_known) / len(ports), 3) if ports else 0.0,
        "nets_total": len(nets),
        "nets_class_known": len(nets_class_known),
        "net_class_coverage": round(len(nets_class_known) / len(nets), 3) if nets else 0.0,
        "nets_role_known": len(nets_role_known),
        "net_role_coverage": round(len(nets_role_known) / len(nets), 3) if nets else 0.0,
        "port_review_items": sum(1 for port in ports if port.review != "auto"),
        "net_review_items": sum(1 for net in nets if net.review != "auto"),
        "review_items": len(review_queue),
        "mean_confidence": round(mean_confidence, 3),
        "mean_port_confidence": round(mean_port_confidence, 3),
        "mean_net_confidence": round(mean_net_confidence, 3),
        "structure_counts": dict(sorted(structure_counts.items())),
        "block_count": len(blocks),
    }

    design = {
        "name": facts.netlist.name,
        "source": facts.netlist.source,
        "subckt": facts.netlist.subckt,
        "ports": facts.ports,
        "port_directions": facts.port_dirs,
        "rails": sorted(facts.rails),
        "output_ports": sorted(facts.output_ports),
        "stats": {
            "devices": len(annotations),
            "mos": len(mos),
            "caps": sum(1 for annotation in annotations if annotation.kind == "cap"),
            "resistors": sum(1 for annotation in annotations if annotation.kind == "res"),
            "subckts": sum(1 for annotation in annotations if annotation.kind == "subckt"),
            "ports": len(ports),
            "nets": len(nets),
            "blocks": len(blocks),
            "median_width_um": round(facts.median_width, 3),
        },
    }

    warnings = list(dict.fromkeys(facts.warnings))
    if not facts.ports:
        warnings.append("no top-level ports found; rail/control inference is weaker")
    if not facts.pairs:
        warnings.append("no differential pair detected; amplifier block may be incomplete")
    if any(port.conflicts for port in ports):
        warnings.append("one or more ports have a name/structure conflict; see review queue")

    return Annotation(
        schema_version=SCHEMA_VERSION,
        design=design,
        devices=annotations,
        blocks=blocks,
        review_queue=review_queue,
        coverage=coverage,
        warnings=warnings,
        ports=ports,
        nets=nets,
    )