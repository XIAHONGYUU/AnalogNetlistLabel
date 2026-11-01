"""Connectivity facts and structural recognizers.

This module answers questions that are verifiable from the netlist alone:
which nets are rails, which MOS devices are diode-connected, which devices share
a mirror gate/source, which pairs share a source, which devices are stacked, and
which gates are controlled by an enable/select net.

It deliberately does not assign functional roles; that is `infer.py`'s job.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations

from .spice import Device, Netlist

POWER_RE = re.compile(
    r"^(?:(?:a|d|io|ana|dig|p)?(?:vdd|vss|vcc|vee|vddio|vssio|vddh|vssh|vpwr|vgnd|gnd))$",
    re.I,
)
CONTROL_RE = re.compile(
    r"(^|_)(en|ena|enable|pd|pwr|power|sel|select|trim|adj|mode|test|bypass|sleep|standby|reset|rst|nres|vsel)(_|$)",
    re.I,
)
OUTPUT_RE = re.compile(r"(^|_)(out|vout|vo|output)(_|$)", re.I)
ENABLE_RE = re.compile(r"(^|_)(en|ena|enable|pd|pwr|power|sleep|standby|reset|rst|nres)(_|$)", re.I)


def _net(device: Device, terminal: str) -> str:
    if device.kind == "mos":
        index = {"d": 0, "g": 1, "s": 2, "b": 3}[terminal]
    elif device.kind == "bjt":
        index = {"c": 0, "b": 1, "e": 2}[terminal]
    elif device.kind in ("cap", "res", "diode", "inductor"):
        index = {"p": 0, "n": 1}[terminal]
    else:
        return ""
    return device.nodes[index] if len(device.nodes) > index else ""


def mos_net(device: Device, terminal: str) -> str:
    return _net(device, terminal)


def _sanitize(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", text).strip("_") or "net"


def _similar_width(a: Device, b: Device) -> bool:
    wa, wb = a.width_um, b.width_um
    if wa <= 0 or wb <= 0:
        return a.model == b.model
    return max(wa, wb) / min(wa, wb) <= 1.25


@dataclass
class MirrorCluster:
    id: str
    mtype: str
    gate: str
    source: str
    devices: list[str]
    reference: str | None
    confidence: float
    evidence: list[str]


@dataclass
class Pair:
    a: str
    b: str
    source: str
    gates: tuple[str, str]
    drains: tuple[str, str]
    tail: str | None
    confidence: float
    evidence: list[str]


@dataclass
class Inverter:
    nmos: str
    pmos: str
    input_net: str
    output_net: str
    confidence: float
    evidence: list[str]


@dataclass
class Mux:
    devices: list[str]
    output_net: str
    source_nets: list[str]
    control_nets: list[str]
    confidence: float
    evidence: list[str]


@dataclass
class DesignFacts:
    netlist: Netlist
    nets: dict[str, list[tuple[str, str]]]
    rails: set[str]
    ports: list[str]
    port_dirs: dict[str, str]
    output_ports: set[str]
    control: dict[str, str]
    control_evidence: dict[str, list[str]]
    diode: dict[str, str]
    mirror_clusters: list[MirrorCluster]
    mirror_of: dict[str, MirrorCluster]
    pairs: list[Pair]
    pair_of: dict[str, Pair]
    tails: dict[str, str]
    cascodes: dict[str, str]
    inverters: list[Inverter]
    inverter_of: dict[str, Inverter]
    muxes: list[Mux]
    mux_of: dict[str, Mux]
    pass_devices: dict[str, float]
    median_width: float
    warnings: list[str] = field(default_factory=list)

    @property
    def devices(self) -> list[Device]:
        return self.netlist.devices

    @property
    def mos(self) -> list[Device]:
        return [device for device in self.netlist.devices if device.is_mos]

    def by_name(self, name: str) -> Device | None:
        for device in self.netlist.devices:
            if device.name == name:
                return device
        return None

    def is_rail(self, net: str) -> bool:
        return net in self.rails

    def devices_on(self, net: str) -> list[tuple[str, str]]:
        return self.nets.get(net, [])

    def mos_on(self, net: str, terminal: str | None = None) -> list[Device]:
        result: list[Device] = []
        for name, term in self.nets.get(net, []):
            if terminal is not None and term != terminal:
                continue
            device = self.by_name(name)
            if device is not None and device.is_mos:
                result.append(device)
        return result

    def net_degree(self, net: str) -> int:
        return len(self.nets.get(net, []))

    def bias_like(self, net: str) -> bool:
        if self.is_rail(net) or net in self.control:
            return False
        gate_count = sum(1 for name, term in self.nets.get(net, []) if term == "g")
        return gate_count >= 2 or any(term == "d" and name in self.diode for name, term in self.nets.get(net, []))


def build_facts(netlist: Netlist) -> DesignFacts:
    warnings: list[str] = list(netlist.warnings)
    nets: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for device in netlist.devices:
        for terminal, net in device.terminals:
            if net:
                nets[net].append((device.name, terminal))
    nets = dict(nets)

    mos = [device for device in netlist.devices if device.is_mos]
    ports = list(netlist.ports)
    port_dirs = dict(netlist.pin_directions)

    # Rails: power-like port names plus bulk-tied nets. Internal names such as
    # VDD_START are deliberately not matched by POWER_RE.
    bulk_counts = Counter(
        mos_net(device, "b") for device in mos if mos_net(device, "b")
    )
    rails: set[str] = set()
    for net in nets:
        if POWER_RE.match(net) and (net in ports or bulk_counts.get(net, 0) >= 1):
            rails.add(net)
    for net in ports:
        if POWER_RE.match(net):
            rails.add(net)
    if mos:
        for net, count in bulk_counts.items():
            if count >= max(3, int(0.2 * len(mos))) and count >= 3:
                rails.add(net)
    # A net explicitly marked as a global supply is also a rail candidate.
    for net in netlist.globals:
        if POWER_RE.match(net):
            rails.add(net)

    output_ports = {
        port
        for port in ports
        if port_dirs.get(port, "").upper().startswith("O") or OUTPUT_RE.search(port)
    }
    for net in rails:
        output_ports.discard(net)

    # Diode-connected MOS.
    diode: dict[str, str] = {}
    for device in mos:
        d, g = mos_net(device, "d"), mos_net(device, "g")
        if d and d == g:
            diode[device.name] = f"gate net {g} equals drain net {d} (diode-connected)"

    # Inverter pairs: complementary devices, same gate and drain, opposite rails.
    inverters: list[Inverter] = []
    inverter_of: dict[str, Inverter] = {}
    for nmos in (device for device in mos if device.type == "nmos"):
        for pmos in (device for device in mos if device.type == "pmos"):
            if mos_net(nmos, "g") != mos_net(pmos, "g"):
                continue
            if mos_net(nmos, "d") != mos_net(pmos, "d"):
                continue
            ns, ps = mos_net(nmos, "s"), mos_net(pmos, "s")
            if ns not in rails or ps not in rails or ns == ps:
                continue
            out = mos_net(nmos, "d")
            inp = mos_net(nmos, "g")
            if not out or not inp or out in rails:
                continue
            inverter = Inverter(
                nmos=nmos.name,
                pmos=pmos.name,
                input_net=inp,
                output_net=out,
                confidence=0.88,
                evidence=[
                    f"{nmos.name}/{pmos.name} share gate {inp} and drain {out}",
                    f"{nmos.name} source {ns} and {pmos.name} source {ps} are opposite rails",
                ],
            )
            inverters.append(inverter)
            inverter_of[nmos.name] = inverter
            inverter_of[pmos.name] = inverter

    # Control nets: control-like ports, then propagate through inverter pairs and
    # digital subcircuit instances.
    control: dict[str, str] = {}
    control_evidence: dict[str, list[str]] = {}
    for port in ports:
        if CONTROL_RE.search(port):
            kind = "enable" if ENABLE_RE.search(port) else "select"
            control[port] = kind
            control_evidence[port] = [f"control-like port name {port}"]

    for _ in range(8):
        changed = False
        for inverter in inverters:
            if inverter.input_net in control and inverter.output_net not in control:
                control[inverter.output_net] = control[inverter.input_net]
                control_evidence[inverter.output_net] = [
                    f"{inverter.output_net} is the inverted output of {inverter.input_net} "
                    f"({inverter.nmos}/{inverter.pmos} pair)"
                ] + control_evidence.get(inverter.input_net, [])
                changed = True
        for device in netlist.devices:
            if not device.is_digital_subckt or not device.nodes:
                continue
            out_net = device.nodes[-1]
            input_nets = device.nodes[:-1]
            sources = [net for net in input_nets if net in control]
            if sources and out_net not in control:
                control[out_net] = control[sources[0]]
                control_evidence[out_net] = [
                    f"{device.name} ({device.model}) drives {out_net} from {sources[0]}"
                ] + control_evidence.get(sources[0], [])
                changed = True
        if not changed:
            break

    # Pass / output candidates by total width.
    widths = sorted(device.width_um for device in mos if device.width_um > 0)
    median_width = widths[len(widths) // 2] if widths else 1.0
    pass_devices: dict[str, float] = {}
    for device in mos:
        width = device.width_um
        if width <= 0:
            continue
        nets_set = {mos_net(device, "d"), mos_net(device, "s")}
        touches_output = bool(nets_set & output_ports)
        touches_rail = bool(nets_set & rails)
        if width >= 10 * median_width and touches_output:
            pass_devices[device.name] = 0.95
        elif width >= 20 * median_width and touches_rail:
            pass_devices[device.name] = 0.75
        elif width >= 5 * median_width and touches_output:
            pass_devices[device.name] = 0.7

    # Mirror clusters: same type, gate and source. Control-driven devices are
    # switches, not mirrors.
    groups: dict[tuple[str, str, str], list[Device]] = defaultdict(list)
    for device in mos:
        gate, source = mos_net(device, "g"), mos_net(device, "s")
        if not gate or not source or gate in rails or source not in rails and source not in nets:
            continue
        if gate in control:
            continue
        if device.name in pass_devices:
            continue
        groups[(device.type, gate, source)].append(device)

    mirror_clusters: list[MirrorCluster] = []
    mirror_of: dict[str, MirrorCluster] = {}
    for (mtype, gate, source), members in groups.items():
        if len(members) < 2:
            continue
        names = [device.name for device in members]
        reference = next((device.name for device in members if device.name in diode), None)
        if reference is None:
            # A device whose drain is the gate net is effectively the reference
            # even if the parser did not call it diode-connected (e.g. BJT).
            reference = next(
                (device.name for device in members if mos_net(device, "d") == gate), None
            )
        confidence = 0.82 if reference else 0.5
        evidence = [
            f"{len(names)} {mtype} devices share gate {gate} and source {source}",
        ]
        if reference:
            evidence.append(f"{reference} is the diode-connected reference")
        if len(names) > 4:
            evidence.append("large fan-out cluster: likely bias distribution rather than one matched mirror")
            confidence = min(confidence, 0.55)
        cluster = MirrorCluster(
            id=f"MIR_{mtype.upper()}_{_sanitize(gate)}_{_sanitize(source)}",
            mtype=mtype,
            gate=gate,
            source=source,
            devices=names,
            reference=reference,
            confidence=confidence,
            evidence=evidence,
        )
        mirror_clusters.append(cluster)
        for name in names:
            mirror_of[name] = cluster

    # Differential pairs: same source, same type, distinct gates/drains.
    pairs: list[Pair] = []
    pair_of: dict[str, Pair] = {}
    by_source: dict[str, list[Device]] = defaultdict(list)
    for device in mos:
        source = mos_net(device, "s")
        if source and source not in rails:
            by_source[source].append(device)

    candidates: list[tuple[float, Device, Device, list[str]]] = []
    for source, members in by_source.items():
        if len(members) < 2:
            continue
        for a, b in combinations(members, 2):
            if a.type != b.type or a.name in pass_devices or b.name in pass_devices:
                continue
            if a.name in diode or b.name in diode:
                continue
            ga, gb = mos_net(a, "g"), mos_net(b, "g")
            da, db = mos_net(a, "d"), mos_net(b, "d")
            if not ga or not gb or ga == gb or not da or not db or da == db:
                continue
            if ga in control or gb in control or ga in rails or gb in rails:
                continue
            if mos_net(a, "b") != mos_net(b, "b") and not (
                mos_net(a, "b") in rails and mos_net(b, "b") in rails
            ):
                continue
            score = 0.30
            evidence = [f"{a.name}/{b.name} share source {source}", f"gates {ga}/{gb} are distinct"]
            if _similar_width(a, b):
                score += 0.10
                evidence.append("similar total width")
            if a.model == b.model:
                score += 0.10
            # Symmetric loads: one same-type load on each drain, sharing a gate
            # or model.
            left = [d for d in mos if da in (mos_net(d, "d"), mos_net(d, "s")) and d.name not in (a.name, b.name)]
            right = [d for d in mos if db in (mos_net(d, "d"), mos_net(d, "s")) and d.name not in (a.name, b.name)]
            sym = False
            for la in left:
                for lb in right:
                    if la.type == lb.type and (la.model == lb.model or mos_net(la, "g") == mos_net(lb, "g")):
                        sym = True
                        evidence.append(
                            f"symmetric {la.type} loads {la.name}/{lb.name} on {da}/{db}"
                        )
                        break
                if sym:
                    break
            if sym:
                score += 0.22
            tail = [d for d in mos if mos_net(d, "d") == source and mos_net(d, "s") in rails]
            if tail:
                score += 0.10
                evidence.append(f"tail device {tail[0].name} feeds {source}")
            if ga in ports or gb in ports:
                score += 0.05
            confidence = min(0.96, score)
            if confidence >= 0.62:
                candidates.append((confidence, a, b, evidence))

    candidates.sort(key=lambda item: item[0], reverse=True)
    for confidence, a, b, evidence in candidates:
        if a.name in pair_of or b.name in pair_of:
            continue
        pair = Pair(
            a=a.name,
            b=b.name,
            source=source_of_pair(a, b),
            gates=(mos_net(a, "g"), mos_net(b, "g")),
            drains=(mos_net(a, "d"), mos_net(b, "d")),
            tail=None,
            confidence=confidence,
            evidence=evidence,
        )
        pairs.append(pair)
        pair_of[a.name] = pair
        pair_of[b.name] = pair

    # Tails: a MOS feeding the pair source from a rail.
    tails: dict[str, str] = {}
    for pair in pairs:
        candidates_tail = [
            device
            for device in mos
            if mos_net(device, "d") == pair.source
            and mos_net(device, "s") in rails
            and mos_net(device, "g") != pair.source
            and mos_net(device, "g") not in control
        ]
        if candidates_tail:
            tail = max(candidates_tail, key=lambda device: device.width_um)
            tails[tail.name] = pair.source
            pair.tail = tail.name
            pair.evidence.append(f"tail {tail.name} source {mos_net(tail, 's')} feeds {pair.source}")
            pair.confidence = min(0.98, pair.confidence + 0.03)

    # Cascodes: upper device whose source is the drain of a lower same-type device.
    cascodes: dict[str, str] = {}
    for upper in mos:
        if upper.name in pass_devices or upper.name in diode:
            continue
        us = mos_net(upper, "s")
        ug = mos_net(upper, "g")
        if not us or us in rails or not ug or ug in control or ug in rails:
            continue
        # A real cascode source is a local series node, not a bias bus.
        if len(nets.get(us, [])) > 4:
            continue
        lowers = [
            lower
            for lower in mos
            if lower.name != upper.name
            and lower.type == upper.type
            and mos_net(lower, "d") == us
            and mos_net(lower, "s") != us
        ]
        if not lowers:
            continue
        lower = max(lowers, key=lambda device: device.width_um)
        score = 0.35
        if _similar_width(upper, lower):
            score += 0.10
        if upper.model == lower.model:
            score += 0.10
        if bias_like_net(ug, nets, diode, control, rails):
            score += 0.20
        if len(nets.get(us, [])) <= 4:
            score += 0.10
        # A cascode gate must be a bias/port net. A signal-driven series device
        # is more likely a pass driver or a stacked output device.
        if score >= 0.62 and (bias_like_net(ug, nets, diode, control, rails) or ug in ports):
            cascodes[upper.name] = lower.name

    # Muxes: two same-type devices share a drain but select different sources,
    # with both gates on control nets.
    muxes: list[Mux] = []
    mux_of: dict[str, Mux] = {}
    by_drain: dict[str, list[Device]] = defaultdict(list)
    for device in mos:
        drain = mos_net(device, "d")
        if drain and drain not in rails:
            by_drain[drain].append(device)
    for drain, members in by_drain.items():
        if len(members) < 2:
            continue
        for a, b in combinations(members, 2):
            if a.type != b.type:
                continue
            ga, gb = mos_net(a, "g"), mos_net(b, "g")
            sa, sb = mos_net(a, "s"), mos_net(b, "s")
            if ga == gb or sa == sb:
                continue
            if ga not in control or gb not in control:
                continue
            mux = Mux(
                devices=[a.name, b.name],
                output_net=drain,
                source_nets=[sa, sb],
                control_nets=[ga, gb],
                confidence=0.78,
                evidence=[
                    f"{a.name}/{b.name} share drain {drain} but select different sources {sa}/{sb}",
                    f"gates {ga}/{gb} are control nets",
                ],
            )
            muxes.append(mux)
            mux_of[a.name] = mux
            mux_of[b.name] = mux

    return DesignFacts(
        netlist=netlist,
        nets=nets,
        rails=rails,
        ports=ports,
        port_dirs=port_dirs,
        output_ports=output_ports,
        control=control,
        control_evidence=control_evidence,
        diode=diode,
        mirror_clusters=mirror_clusters,
        mirror_of=mirror_of,
        pairs=pairs,
        pair_of=pair_of,
        tails=tails,
        cascodes=cascodes,
        inverters=inverters,
        inverter_of=inverter_of,
        muxes=muxes,
        mux_of=mux_of,
        pass_devices=pass_devices,
        median_width=median_width,
        warnings=warnings,
    )


def source_of_pair(a: Device, b: Device) -> str:
    return mos_net(a, "s")


def bias_like_net(
    net: str,
    nets: dict[str, list[tuple[str, str]]],
    diode: dict[str, str],
    control: dict[str, str],
    rails: set[str],
) -> bool:
    if net in rails or net in control:
        return False
    gate_count = sum(1 for name, term in nets.get(net, []) if term == "g")
    if gate_count >= 2:
        return True
    return any(term == "d" and name in diode for name, term in nets.get(net, []))