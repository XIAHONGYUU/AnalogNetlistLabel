"""Net classification and structural-role annotation.

Nets are where names carry the most human intent (VINP, EN, ATD, VBIAS_P), but they
are also the most incomplete. This module emits a layered answer: electrical class,
structural role, differential/bus grouping, optional canonical name, evidence and
review state. It does not overwrite the original net name.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from .facts import DesignFacts, mos_net
from .model import Block, Candidate, NetAnnotation, PortAnnotation
from .spice import Netlist

_BUS_RE = re.compile(r"^(.*?)[<\[](\d+)(?::(\d+))?[>\]]$")
_CLOCK_RE = re.compile(r"(^|_)(CLK|CK|CLOCK|OSC)(_|$)", re.I)
_RESET_RE = re.compile(r"(^|_)(RST|RESET|NRST|POR)(_|$)", re.I)
_REFERENCE_RE = re.compile(r"(VREF|VBG|VBGR|VREF_INT|VREF_EXT)", re.I)
_GROUND_WORDS = ("VSS", "GND", "AGND", "DGND", "0")

_ROLE_CONFIDENCE = {
    "supply": 0.95,
    "ground": 0.95,
    "input": 0.85,
    "output": 0.85,
    "tail": 0.85,
    "mirror_gate": 0.8,
    "cascode_mid": 0.75,
    "pass_gate": 0.8,
    "feedback": 0.8,
    "reference": 0.8,
    "startup": 0.75,
    "gain_node": 0.65,
    "degeneration": 0.7,
    "bias_bus": 0.7,
    "control": 0.8,
    "internal": 0.45,
    "unknown": 0.0,
}


def classify_nets(
    netlist: Netlist,
    facts: DesignFacts,
    ports: list[PortAnnotation],
    blocks: list[Block],
) -> list[NetAnnotation]:
    port_by_name = {port.original_name: port for port in ports}
    block_of = {device: block.id for block in blocks for device in block.devices}

    tail_nets = {pair.source: pair for pair in facts.pairs}
    mirror_gates = {cluster.gate for cluster in facts.mirror_clusters}
    cascode_mids = {
        mos_net(device, "s")
        for device in facts.mos
        if device.name in facts.cascodes and mos_net(device, "s")
    }
    cascode_outputs = {
        mos_net(device, "d")
        for device in facts.mos
        if device.name in facts.cascodes and mos_net(device, "d")
    }
    pass_gates = {
        mos_net(device, "g")
        for device in facts.mos
        if device.name in facts.pass_devices and mos_net(device, "g")
    }
    output_nets = set(facts.output_ports)
    for device in facts.mos:
        if device.name in facts.pass_devices:
            output_nets.add(mos_net(device, "s"))
            output_nets.add(mos_net(device, "d"))
    feedback_nets = _feedback_nets(facts)
    degeneration_nets: set[str] = set()
    for resistor in (device for device in facts.devices if device.kind == "res"):
        for net in resistor.nodes[:2]:
            other = resistor.nodes[1] if resistor.nodes[0] == net else resistor.nodes[0]
            if other in facts.rails and facts.mos_on(net, "s"):
                degeneration_nets.add(net)
    gain_nodes = {
        name
        for name, terminals in facts.nets.items()
        if sum(1 for _n, terminal in terminals if terminal == "d") >= 2
        and any(terminal == "g" for _n, terminal in terminals)
    }
    diode_gates = {
        mos_net(device, "g")
        for device in facts.mos
        if device.name in facts.diode and mos_net(device, "g")
    }

    nets: list[NetAnnotation] = []
    for name, terminals in facts.nets.items():
        bus = _bus(name)
        is_port = name in port_by_name
        port = port_by_name.get(name)
        block = _majority_block(terminals, block_of)

        if is_port and port and port.direction == "output":
            terminal_devices = {device_name for device_name, _terminal in terminals}
            pass_blocks = [
                block_of[device.name]
                for device in facts.mos
                if device.name in facts.pass_devices
                and device.name in terminal_devices
                and block_of.get(device.name)
            ]
            if pass_blocks:
                block = pass_blocks[0]

        electrical_class = "signal"
        structural_role = "internal"
        function: str | None = None
        evidence: list[str] = []
        negative: list[str] = []
        conflicts: list[str] = []
        confidence = _ROLE_CONFIDENCE["internal"]
        differential_group = None

        if name in facts.rails or (port and port.electrical_class in ("power", "ground")):
            if (port and port.electrical_class == "ground") or _is_ground(name, facts):
                electrical_class = "ground"
                structural_role = "ground"
            else:
                electrical_class = "power"
                structural_role = "supply"
            evidence.append(f"net {name} is an inferred rail")
            confidence = _ROLE_CONFIDENCE[structural_role]
        elif is_port:
            electrical_class = port.electrical_class
            structural_role = _port_role(port)
            evidence.extend(f"port: {item}" for item in port.evidence[:3])
            confidence = port.confidence
        elif name in facts.control:
            electrical_class = "control"
            structural_role = "control"
            evidence.append(f"net {name} is a propagated {facts.control[name]} control net")
            confidence = _ROLE_CONFIDENCE["control"]
        elif _CLOCK_RE.search(name):
            electrical_class = "clock"
            structural_role = "control"
            evidence.append(f"net name {name} contains a clock token")
            confidence = 0.8
        elif _RESET_RE.search(name):
            electrical_class = "reset"
            structural_role = "control"
            evidence.append(f"net name {name} contains a reset token")
            confidence = 0.8
        elif name in tail_nets:
            pair = tail_nets[name]
            electrical_class = "signal"
            structural_role = "tail"
            differential_group = _pair_group(pair, block)
            evidence.append(f"net {name} is the common source of pair {pair.a}/{pair.b}")
            confidence = _ROLE_CONFIDENCE["tail"]
        elif name in pass_gates:
            electrical_class = "control"
            structural_role = "pass_gate"
            evidence.append(f"net {name} is the gate of a pass device")
            confidence = _ROLE_CONFIDENCE["pass_gate"]
        elif name in feedback_nets:
            electrical_class = "signal"
            structural_role = "feedback"
            evidence.append(f"net {name} is a divider midpoint that drives a pair gate")
            confidence = _ROLE_CONFIDENCE["feedback"]
        elif name in output_nets:
            electrical_class = "signal"
            structural_role = "output"
            evidence.append(f"net {name} is an output/pass-device net")
            confidence = _ROLE_CONFIDENCE["output"]
        elif _REFERENCE_RE.search(name) or (block == "REF" and structural_role == "internal"):
            electrical_class = "reference"
            structural_role = "reference"
            evidence.append(f"net {name} is a reference name or belongs to the REF block")
            confidence = _ROLE_CONFIDENCE["reference"]
        elif "START" in name.upper() or block == "START":
            electrical_class = "signal"
            structural_role = "startup"
            evidence.append(f"net {name} belongs to the startup network")
            confidence = _ROLE_CONFIDENCE["startup"]
        elif name in cascode_outputs and any(
            mos_net(driver, "s") in facts.rails and mos_net(driver, "d") not in facts.rails
            for driver in facts.mos_on(name, "g")
        ):
            electrical_class = "signal"
            structural_role = "mirror_gate"
            function = "interstage_signal"
            evidence.append(f"net {name} is a cascode output and drives a common-source gate")
            confidence = 0.8
        elif name in mirror_gates or name in diode_gates:
            electrical_class = "bias"
            structural_role = "mirror_gate"
            evidence.append(f"net {name} is shared by mirror/diode gates")
            confidence = _ROLE_CONFIDENCE["mirror_gate"]
        elif name in cascode_mids:
            electrical_class = "signal"
            structural_role = "cascode_mid"
            evidence.append(f"net {name} is the source of a cascode device")
            confidence = _ROLE_CONFIDENCE["cascode_mid"]
        elif name in gain_nodes:
            electrical_class = "signal"
            structural_role = "gain_node"
            evidence.append(f"net {name} is a multi-drain high-impedance gain node")
            confidence = _ROLE_CONFIDENCE["gain_node"]
        elif name in degeneration_nets:
            electrical_class = "bias"
            structural_role = "degeneration"
            evidence.append(f"net {name} is a source-degeneration node")
            confidence = _ROLE_CONFIDENCE["degeneration"]
        elif facts.bias_like(name) or _gate_fanout(terminals) >= 3:
            electrical_class = "bias"
            structural_role = "bias_bus"
            evidence.append(f"net {name} is a high-fanout bias-like net")
            confidence = _ROLE_CONFIDENCE["bias_bus"]
        else:
            electrical_class = "signal"
            structural_role = "internal"
            evidence.append("no rail/control/port/structural role matched")
            negative.append("internal net role is not resolved")
            confidence = _ROLE_CONFIDENCE["internal"]

        if electrical_class in ("power", "ground"):
            # A rail is a global net; assigning it to the first block that touches
            # it (e.g. CTRL_EN because a level shifter uses AVDD) is misleading.
            block = None

        if port:
            electrical_class = port.electrical_class
            structural_role = _port_role(port)
            differential_group = port.differential_group
            evidence.append(f"port class {port.electrical_class} and interface {port.interface}")
            confidence = max(confidence, port.confidence)
        elif name in facts.control:
            electrical_class = "control"

        if electrical_class == "signal" and structural_role == "internal" and differential_group is None:
            negative.append("no structural role evidence for this internal net")

        if port and port.conflicts:
            conflicts.extend(port.conflicts)

        candidates = [
            Candidate(
                label=electrical_class,
                score=confidence,
                kind="class",
                evidence=list(evidence),
                negative_evidence=list(negative),
            )
        ]
        if structural_role != "internal":
            candidates.append(
                Candidate(
                    label=structural_role,
                    score=confidence,
                    kind="structural_role",
                    evidence=list(evidence),
                )
            )

        semantic_id = f"net:{_norm(name)}"
        norm = _norm(name)
        canonical = None
        if is_port:
            canonical = name
        elif structural_role == "tail":
            canonical = _suffix("TAIL", block)
        elif structural_role == "cascode_mid":
            canonical = _suffix("CAS_MID", block)
        elif structural_role == "pass_gate":
            canonical = "PASS_GATE"
        elif structural_role == "feedback":
            canonical = _suffix("FB", block)
        # Mirror gates and bias buses are intentionally left unnamed: many nets
        # share the role, and a name would imply a uniqueness that does not exist.

        nets.append(
            NetAnnotation(
                original_name=name,
                is_port=is_port,
                electrical_class=electrical_class,
                structural_role=structural_role,
                confidence=confidence,
                function=function,
                differential_group=differential_group,
                bus=bus,
                semantic_id=semantic_id,
                canonical_name=canonical,
                block=block,
                evidence=evidence,
                negative_evidence=negative,
                candidates=candidates,
                conflicts=conflicts,
                anchors=[f"{device_name}.{terminal}" for device_name, terminal in terminals][:16],
                review="auto",
            )
        )

    _assign_pair_groups(nets, facts, block_of)
    for net in nets:
        if net.conflicts:
            net.review = "confirm"
        elif net.electrical_class == "unknown" or net.structural_role == "unknown":
            net.review = "unknown"
        elif net.confidence < 0.7:
            net.review = "confirm"
        else:
            net.review = "auto"
    return nets


def _norm(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper() or "NET"


def _bus(name: str) -> str | None:
    match = _BUS_RE.match(name)
    if not match:
        return None
    return f"{match.group(2)}:{match.group(3)}" if match.group(3) else match.group(2)


def _suffix(base: str, block: str | None) -> str:
    return f"{base}_{block}" if block else base


def _gate_fanout(terminals: list[tuple[str, str]]) -> int:
    return sum(1 for _name, terminal in terminals if terminal == "g")


def _is_ground(name: str, facts: DesignFacts) -> bool:
    upper = name.upper()
    if upper == "0" or "VSS" in upper or "GND" in upper:
        return True
    nmos = 0
    pmos = 0
    for device in facts.mos:
        if len(device.nodes) >= 4 and device.nodes[3] == name:
            if device.type == "nmos":
                nmos += 1
            elif device.type == "pmos":
                pmos += 1
    return nmos > pmos


def _port_role(port: PortAnnotation) -> str:
    if port.electrical_class in ("power", "ground"):
        return "supply" if port.electrical_class == "power" else "ground"
    if port.electrical_class == "bias":
        return "bias_bus"
    if port.electrical_class == "reference":
        return "reference"
    if port.electrical_class in ("control", "enable", "select", "clock", "reset", "interface"):
        return "control"
    if port.direction == "input":
        return "input"
    if port.direction == "output":
        return "output"
    return "internal"


def _feedback_nets(facts: DesignFacts) -> set[str]:
    resistors = [device for device in facts.devices if device.kind == "res"]
    by_net: dict[str, list[str]] = defaultdict(list)
    for device in resistors:
        for net in device.nodes[:2]:
            if net and net not in facts.rails:
                by_net[net].append(device.name)
    result: set[str] = set()
    for net, names in by_net.items():
        if len(names) >= 2 and facts.mos_on(net, "g"):
            result.add(net)
    return result


def _majority_block(
    terminals: list[tuple[str, str]],
    block_of: dict[str, str],
) -> str | None:
    counts = Counter(
        block_of[name] for name, _terminal in terminals if block_of.get(name)
    )
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def _pair_group(pair: object, block: str | None) -> str:
    block_name = block or "PAIR"
    return f"DP_{block_name}"


def _assign_pair_groups(
    nets: list[NetAnnotation],
    facts: DesignFacts,
    block_of: dict[str, str],
) -> None:
    by_name = {net.original_name: net for net in nets}
    for pair in facts.pairs:
        block = block_of.get(pair.a) or block_of.get(pair.b) or "PAIR"
        group = f"DP_{block}"
        for net_name in pair.drains:
            net = by_name.get(net_name)
            if net is not None:
                net.differential_group = group
                net.evidence.append(f"differential group {group} from pair {pair.a}/{pair.b}")
                if net.structural_role == "internal":
                    net.structural_role = "output"
                    net.confidence = max(net.confidence, 0.75)