"""Port classification and anchoring.

The port is the cell's interface contract. It is not "a net with a name": it has
direction, electrical class, interface semantics, differential/bus grouping, and
evidence. These annotations anchor the internal net/device inference.
"""

from __future__ import annotations

import re
from collections import defaultdict

from .facts import DesignFacts
from .model import Candidate, PortAnnotation
from .spice import Netlist

_BUS_RE = re.compile(r"^(.*?)[<\[](\d+)(?::(\d+))?[>\]]$")
_DIFF_RE = re.compile(r"^(.*?)(?:_?)(P|N)$", re.I)

_POWER_WORDS = ("VDD", "VCC", "VPP", "VPWR", "AVDD", "DVDD", "VDDIO", "VDDA", "VDDD")
_GROUND_WORDS = ("VSS", "GND", "VEE", "VGND", "AVSS", "DVSS", "VSSA", "VSSD", "VSSIO", "0")
_REFERENCE_WORDS = ("VREF", "VBG", "VBGR", "VREF_EXT", "VREF_INT", "VREFP", "VREFN")
_BIAS_WORDS = ("BIAS", "VBIAS", "IBIAS", "NBIAS", "PBIAS", "VBN", "VBP", "IBN", "IBP")
_CLOCK_WORDS = ("CLK", "CK", "CLOCK", "OSC", "CLKOUT")
_RESET_WORDS = ("RST", "RESET", "NRST", "POR", "PWRON")
_ENABLE_WORDS = ("EN", "ENA", "ENB", "ENN", "ENP", "PD", "PWREN", "SLEEP", "STANDBY")
_SELECT_WORDS = ("SEL", "SELECT", "TRIM", "ADJ", "MODE", "TEST", "BYPASS", "VSEL")
_INTERFACE_WORDS = ("ATD", "DTA")

_PIN_DIRECTION = {
    "I": "input",
    "IN": "input",
    "O": "output",
    "OUT": "output",
    "B": "bidirectional",
    "IO": "bidirectional",
    "INOUT": "bidirectional",
}


def classify_ports(netlist: Netlist, facts: DesignFacts) -> list[PortAnnotation]:
    ports: list[PortAnnotation] = []
    for name in netlist.ports:
        ports.append(_classify_one(name, netlist, facts))

    _assign_differential_groups(ports)
    for port in ports:
        if port.conflicts:
            port.review = "confirm"
        elif port.electrical_class == "unknown":
            port.review = "unknown"
        elif port.confidence < 0.7:
            port.review = "confirm"
        else:
            port.review = "auto"
    return ports


def _norm(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper() or "PORT"


def _contains(name: str, words: tuple[str, ...]) -> str | None:
    upper = name.upper()
    for word in words:
        if upper == word or upper.startswith(word + "_") or upper.endswith("_" + word):
            return word
    return None


def _bus(name: str) -> tuple[str, str | None]:
    match = _BUS_RE.match(name)
    if not match:
        return name, None
    base = match.group(1)
    if match.group(3):
        return base, f"{match.group(2)}:{match.group(3)}"
    return base, match.group(2)


def _direction(name: str, netlist: Netlist, facts: DesignFacts) -> tuple[str, list[str]]:
    evidence: list[str] = []
    raw = netlist.pin_directions.get(name, "")
    if raw:
        direction = _PIN_DIRECTION.get(raw.upper(), "unknown")
        evidence.append(f"PININFO direction {raw}")
        if direction != "unknown":
            return direction, evidence
    net = name
    if net in facts.output_ports:
        evidence.append(f"net {net} is an output port")
        return "output", evidence
    if facts.mos_on(net, "g"):
        evidence.append(f"net {net} drives {len(facts.mos_on(net, 'g'))} gate(s)")
        return "input", evidence
    for device in facts.mos:
        if net in (device.nodes[0], device.nodes[2]) and device.width_um >= 5 * facts.median_width:
            evidence.append(f"net {net} connects to a large pass/output device {device.name}")
            return "output", evidence
    return "unknown", evidence


def _rail_is_ground(net: str, facts: DesignFacts) -> bool:
    upper = net.upper()
    if upper == "0" or "VSS" in upper or "GND" in upper:
        return True
    nmos = 0
    pmos = 0
    for device in facts.mos:
        if len(device.nodes) >= 4 and device.nodes[3] == net:
            if device.type == "nmos":
                nmos += 1
            elif device.type == "pmos":
                pmos += 1
    return nmos > pmos


def _classify_one(name: str, netlist: Netlist, facts: DesignFacts) -> PortAnnotation:
    base, bus = _bus(name)
    direction, dir_evidence = _direction(name, netlist, facts)
    evidence: list[str] = list(dir_evidence)
    negative: list[str] = []
    conflicts: list[str] = []
    anchors = [f"{device_name}.{terminal}" for device_name, terminal in facts.nets.get(name, [])][:16]

    electrical_class = "unknown"
    interface = "unknown"
    quantity = "unknown"
    polarity = "unknown"
    score = 0.4

    upper = base.upper()
    if name in facts.rails or upper in _POWER_WORDS or upper in _GROUND_WORDS:
        if _rail_is_ground(name, facts):
            electrical_class = "ground"
            interface = "ground"
            quantity = "voltage"
            direction = "ground"
            score = 0.95
            evidence.append(f"net {name} is a ground/body-tied rail")
        else:
            electrical_class = "power"
            interface = "power"
            quantity = "voltage"
            direction = "power"
            score = 0.95
            evidence.append(f"net {name} is a power rail")
    elif _contains(upper, _INTERFACE_WORDS):
        electrical_class = "interface"
        interface = "atd" if upper.startswith("ATD") else "dta"
        quantity = "digital_bus" if bus else "digital"
        score = 0.9
        evidence.append(f"interface token {interface.upper()} in port name")
    elif _contains(upper, _REFERENCE_WORDS):
        electrical_class = "reference"
        interface = "analog_reference"
        quantity = "voltage"
        score = 0.9
        evidence.append(f"reference token in port name {name}")
    elif _contains(upper, _BIAS_WORDS):
        electrical_class = "bias"
        interface = "bias"
        quantity = "current" if upper.startswith("I") else "voltage"
        score = 0.85
        evidence.append(f"bias token in port name {name}")
    elif _contains(upper, _CLOCK_WORDS):
        electrical_class = "clock"
        interface = "digital_input"
        quantity = "digital"
        score = 0.9
        evidence.append(f"clock token in port name {name}")
    elif _contains(upper, _RESET_WORDS):
        electrical_class = "reset"
        interface = "digital_input"
        quantity = "digital"
        score = 0.9
        evidence.append(f"reset token in port name {name}")
    elif _contains(upper, _ENABLE_WORDS):
        electrical_class = "enable"
        interface = "digital_input"
        quantity = "digital"
        score = 0.9
        evidence.append(f"enable token in port name {name}")
        if upper.endswith("N") or upper.endswith("B"):
            polarity = "active_low"
            evidence.append("name suffix suggests active-low enable")
    elif _contains(upper, _SELECT_WORDS):
        electrical_class = "select"
        interface = "digital_input"
        quantity = "digital"
        score = 0.88
        evidence.append(f"select/trim token in port name {name}")
    elif direction == "input" and _structural_bias(name, facts):
        electrical_class = "bias"
        interface = "bias"
        quantity = "current" if upper.startswith("I") else "voltage"
        score = 0.65
        evidence.append(_structural_bias(name, facts) or "structural bias evidence")
    elif direction in ("input", "output", "bidirectional"):
        electrical_class = "signal"
        interface = {
            "input": "analog_input",
            "output": "analog_output",
            "bidirectional": "analog_bidirectional",
        }[direction]
        quantity = "voltage"
        score = 0.7
        evidence.append(f"direction {direction} and no control/power token")
    else:
        evidence.append("no class token and no structural direction evidence")
        negative.append("port class is unresolved")

    if direction in ("power", "ground") and electrical_class not in ("power", "ground"):
        conflicts.append(f"direction {direction} conflicts with class {electrical_class}")

    # A power/ground name that is not a rail is a conflict, not a silent relabel.
    if electrical_class in ("power", "ground") and name not in facts.rails:
        conflicts.append(f"name suggests {electrical_class} but net is not in inferred rails")

    # Differential suffix detection is only applied to signal/clock ports.
    if electrical_class in ("signal", "clock", "interface"):
        match = _DIFF_RE.match(base)
        if match and len(match.group(1)) >= 2:
            polarity = "positive" if match.group(2).upper() == "P" else "negative"
            evidence.append(f"differential suffix {match.group(2).upper()}")

    if bus:
        evidence.append(f"bus syntax <{bus}>")

    semantic_id = f"port:{_norm(name)}"
    candidates = [
        Candidate(
            label=electrical_class,
            score=score,
            kind="class",
            evidence=list(evidence),
            negative_evidence=list(negative),
        )
    ]
    if electrical_class != "unknown":
        candidates.append(
            Candidate(
                label="unknown",
                score=max(0.05, 0.5 - score / 2),
                kind="class",
                evidence=["conservative fallback when port semantics are incomplete"],
            )
        )

    return PortAnnotation(
        original_name=name,
        direction=direction,
        electrical_class=electrical_class,
        interface=interface,
        quantity=quantity,
        polarity=polarity,
        confidence=score,
        differential_group=None,
        bus=bus,
        semantic_id=semantic_id,
        canonical_name=name,
        evidence=evidence,
        negative_evidence=negative,
        candidates=candidates,
        conflicts=conflicts,
        anchors=anchors,
        review="auto",
    )


def _structural_bias(name: str, facts: DesignFacts) -> str | None:
    gates = facts.mos_on(name, "g")
    for device in gates:
        if device.name in facts.mirror_of:
            return f"port net {name} drives mirror device {device.name}"
        if device.name in facts.tails:
            return f"port net {name} drives tail device {device.name}"
    if len(gates) >= 2 and name not in facts.control:
        return f"port net {name} is a shared gate net"
    return None


def _assign_differential_groups(ports: list[PortAnnotation]) -> None:
    by_base: dict[str, list[PortAnnotation]] = defaultdict(list)
    for port in ports:
        if port.electrical_class not in ("signal", "clock", "interface"):
            continue
        match = _DIFF_RE.match(port.original_name)
        if not match or len(match.group(1)) < 2:
            continue
        by_base[match.group(1).upper()].append(port)
    for base, group in by_base.items():
        if len(group) != 2:
            continue
        classes = {port.electrical_class for port in group}
        if len(classes) != 1:
            continue
        for port in group:
            port.differential_group = base
            port.evidence.append(f"differential group {base} from P/N-suffixed port pair")