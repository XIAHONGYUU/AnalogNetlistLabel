"""A deliberately small, read-only SPICE reader.

Supported subset:

* MOS: `M1 d g s b model w=... l=... nf=... m=...`
* Spectre-style node list: `M1 (d g s b) model ...`
* capacitor: `C1 n1 n2 1.5p` or `C1 n1 n2 model c=1.5p`
* resistor: `R1 n1 n2 10k` or `R1 n1 n2 model r=10k`
* diode and BJT device lines
* subcircuit instances: `X1 n1 n2 subckt_name`
* `.subckt` / `.ends` / `.pininfo` / `.global`
* continuation lines and `*`, `;`, `//`, `$` comments

This is not a full SPICE parser. It does not evaluate `.param` expressions,
expand device models, flatten hierarchical subcircuits, or compute capacitance
from W/L. Those limitations are deliberate: the annotation layer must not invent
values that the netlist does not state.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .units import parse_cap_pf, parse_int, parse_length_um, parse_res_ohm


@dataclass
class SubcktDef:
    name: str
    ports: list[str]
    line_no: int


@dataclass
class Device:
    name: str
    kind: str
    nodes: list[str]
    model: str
    params: dict[str, str] = field(default_factory=dict)
    line_no: int = 0
    subckt: str = ""
    raw: str = ""

    @property
    def type(self) -> str:
        model = self.model.lower()
        if self.kind == "mos":
            if any(token in model for token in ("pfet", "pmos", "pch", "pmoscap")):
                return "pmos"
            if any(token in model for token in ("nfet", "nmos", "nch", "nmoscap")):
                return "nmos"
            if model.startswith("p"):
                return "pmos"
            if model.startswith("n"):
                return "nmos"
            return "unknown"
        if self.kind == "bjt":
            if "pnp" in model:
                return "pnp"
            return "npn"
        return self.kind

    @property
    def is_mos(self) -> bool:
        return self.kind == "mos"

    @property
    def is_passive(self) -> bool:
        return self.kind in ("cap", "res", "inductor")

    @property
    def is_digital_subckt(self) -> bool:
        if self.kind != "subckt":
            return False
        model = self.model.lower()
        return any(
            token in model
            for token in ("stdcell", "_sc_", "sc_hvl", "buf", "inv", "level", "lsb", "logic")
        )

    @property
    def terminals(self) -> list[tuple[str, str]]:
        if self.kind == "mos":
            names = ("d", "g", "s", "b")
            return list(zip(names, self.nodes[:4]))
        if self.kind == "bjt":
            names = ("c", "b", "e")
            return list(zip(names, self.nodes[:3]))
        if self.kind in ("cap", "res", "diode", "inductor"):
            names = ("p", "n")
            return list(zip(names, self.nodes[:2]))
        return [(f"p{i}", node) for i, node in enumerate(self.nodes)]

    @property
    def w_um(self) -> float:
        return _length(self.params.get("w"), f"{self.name} w")

    @property
    def l_um(self) -> float:
        return _length(self.params.get("l"), f"{self.name} l")

    @property
    def nf(self) -> int:
        return _count(self.params.get("nf") or self.params.get("fingers"), f"{self.name} nf")

    @property
    def m(self) -> int:
        return _count(self.params.get("m") or self.params.get("mult"), f"{self.name} m")

    @property
    def width_um(self) -> float:
        if not self.is_mos:
            return 0.0
        try:
            return self.w_um * self.nf * self.m
        except ValueError:
            return 0.0

    @property
    def cap_pf(self) -> float:
        raw = self.params.get("c") or self.params.get("value")
        if raw is None:
            return 0.0
        try:
            return parse_cap_pf(raw, what=f"{self.name} c")
        except ValueError:
            return 0.0

    @property
    def res_ohm(self) -> float:
        raw = self.params.get("r") or self.params.get("value")
        if raw is None:
            return 0.0
        try:
            return parse_res_ohm(raw, what=f"{self.name} r")
        except ValueError:
            return 0.0


def _length(raw: str | None, what: str) -> float:
    if raw is None or str(raw).strip() == "":
        return 0.0
    try:
        return parse_length_um(raw, what=what)
    except ValueError:
        return 0.0


def _count(raw: str | None, what: str) -> int:
    if raw is None or str(raw).strip() == "":
        return 1
    try:
        return parse_int(raw, what=what)
    except ValueError:
        return 1


@dataclass
class Netlist:
    source: str
    name: str
    subckt: str
    ports: list[str]
    pin_directions: dict[str, str]
    devices: list[Device]
    subckts: list[SubcktDef]
    globals: list[str]
    warnings: list[str] = field(default_factory=list)

    def device_by_name(self) -> dict[str, Device]:
        return {device.name: device for device in self.devices}

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "name": self.name,
            "subckt": self.subckt,
            "ports": self.ports,
            "pin_directions": self.pin_directions,
            "warnings": self.warnings,
            "devices": [
                {
                    "name": device.name,
                    "kind": device.kind,
                    "type": device.type,
                    "nodes": device.nodes,
                    "model": device.model,
                    "params": device.params,
                    "subckt": device.subckt,
                    "line_no": device.line_no,
                }
                for device in self.devices
            ],
        }


_NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?[a-zA-Z]*$")


def _strip_comment(line: str) -> str:
    text = line.rstrip("\n\r")
    stripped = text.lstrip()
    if stripped.startswith("*"):
        # xschem commonly writes active directives as "*.PININFO" / "*.GLOBAL".
        # Treat those as active; every other "*" line is a comment.
        candidate = stripped[1:].strip()
        if candidate.lower().startswith((".pininfo", ".global")):
            text = candidate
        else:
            return ""
    for marker in ("//", ";", "$"):
        index = text.find(marker)
        if index >= 0:
            text = text[:index]
    return text.rstrip()


def _logical_lines(text: str) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = _strip_comment(raw)
        if not line.strip():
            continue
        if line.lstrip().startswith("+"):
            continuation = line.lstrip()[1:].strip()
            if result:
                first, previous = result[-1]
                result[-1] = (first, f"{previous} {continuation}")
            else:
                result.append((number, continuation))
        else:
            result.append((number, line.strip()))
    return result


def _parse_params(tokens: list[str]) -> dict[str, str]:
    params: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        key = key.strip().lower()
        value = value.strip().strip("'\"")
        if key:
            params[key] = value
    return params


def _split_model_and_params(tokens: list[str]) -> tuple[str, list[str]]:
    """Return (model, param_tokens) from the tail of a device line."""

    for index, token in enumerate(tokens):
        if "=" in token:
            return (tokens[index - 1] if index > 0 else ""), tokens[index:]
    return (tokens[-1] if tokens else ""), []


def _parse_mos(name: str, tokens: list[str], line_no: int, warnings: list[str]) -> tuple[list[str], str, list[str]]:
    rest = tokens[1:]
    if not rest:
        warnings.append(f"line {line_no}: {name} has no terminals")
        return [], "", []
    if rest[0].startswith("("):
        joined = " ".join(rest)
        close = joined.find(")")
        if close < 0:
            warnings.append(f"line {line_no}: {name} has an unterminated node list")
            return [], "", []
        node_text = joined[1:close]
        nodes = [part for part in re.split(r"[\s,]+", node_text) if part]
        tail = shlex.split(joined[close + 1 :].strip())
        model, param_tokens = _split_model_and_params(tail)
        return nodes, model, param_tokens
    if len(rest) < 5:
        warnings.append(f"line {line_no}: {name} needs four terminals and a model")
        return rest[:-1], rest[-1] if rest else "", []
    return _split_terminals_and_model(rest, kind="mos")


def _split_terminals_and_model(
    rest: list[str], *, kind: str
) -> tuple[list[str], str, list[str]]:
    """Split a device tail into (nodes, model/value, param tokens).

    The last non-parameter token is the model. For a value-style passive line
    (`R1 a b 10k`) the numeric token becomes a value parameter instead.
    """

    eq_index = next((index for index, token in enumerate(rest) if "=" in token), None)
    if eq_index is None:
        head, params = rest, []
    else:
        head, params = rest[:eq_index], rest[eq_index:]

    if not head:
        return [], "", params

    last = head[-1]
    if kind in ("cap", "res", "inductor", "diode") and _NUMBER_RE.match(last) and len(head) >= 3:
        return head[:-1], kind, [f"value={last}"] + params

    return head[:-1], last, params


def _parse_two_terminal(
    name: str,
    tokens: list[str],
    line_no: int,
    warnings: list[str],
    *,
    kind: str,
) -> tuple[list[str], str, list[str]]:
    rest = tokens[1:]
    if len(rest) < 3:
        warnings.append(f"line {line_no}: {name} needs two nodes and a value/model")
        return rest[:2], "", []
    nodes, model, param_tokens = _split_terminals_and_model(rest, kind=kind)
    if not model:
        warnings.append(f"line {line_no}: {name} has no model/value")
    return nodes, model, param_tokens


def _parse_subckt_instance(name: str, tokens: list[str], line_no: int, warnings: list[str]) -> tuple[list[str], str, list[str]]:
    rest = tokens[1:]
    if len(rest) < 2:
        warnings.append(f"line {line_no}: {name} needs at least one node and a subcircuit name")
        return rest, "", []
    nodes, model, param_tokens = _split_terminals_and_model(rest, kind="subckt")
    if not model:
        warnings.append(f"line {line_no}: {name} has no subcircuit name")
    return nodes, model, param_tokens


def _model_token(tokens: list[str]) -> str:
    for index, token in enumerate(tokens):
        if "=" in token:
            return tokens[index - 1] if index > 0 else ""
    return tokens[-1] if tokens else ""


def _looks_like_mos_model(model: str) -> bool:
    text = model.lower()
    return any(token in text for token in ("nmos", "pmos", "nfet", "pfet", "nch", "pch"))


def _pininfo_directions(tokens: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for token in tokens:
        if ":" not in token:
            continue
        name, direction = token.split(":", 1)
        direction = direction.strip().upper()
        if direction in ("I", "O", "B", "IO", "IN", "OUT", "INOUT"):
            result[name] = direction
    return result


def parse_text(text: str, *, source: str = "<memory>", name: str | None = None) -> Netlist:
    warnings: list[str] = []
    logical = _logical_lines(text)

    subckts: list[SubcktDef] = []
    current_subckt = ""
    pin_directions: dict[str, str] = {}
    globals_: list[str] = []
    all_devices: list[Device] = []
    seen: set[str] = set()

    for line_no, line in logical:
        tokens = shlex.split(line)
        if not tokens:
            continue
        head = tokens[0].lower()

        if head == ".subckt":
            if len(tokens) < 2:
                warnings.append(f"line {line_no}: .subckt without a name")
                continue
            current_subckt = tokens[1]
            ports = [token for token in tokens[2:] if "=" not in token]
            subckts.append(SubcktDef(current_subckt, ports, line_no))
            continue

        if head in (".ends", ".end"):
            current_subckt = ""
            continue

        if head == ".pininfo":
            pin_directions.update(_pininfo_directions(tokens[1:]))
            continue

        if head == ".global":
            globals_.extend(tokens[1:])
            continue

        if head.startswith("."):
            # .model, .param, .include, .lib, .temp, ...
            continue

        instance = tokens[0]
        low = instance.lower()
        prefix = low[0]
        if low.startswith("x") and len(low) > 1 and low[1] in "mrcdqlj":
            prefix = low[1]
        elif low.startswith("x"):
            prefix = "x"

        # A Q-prefixed line with a MOSFET model is an XQ*/Q* MOSFET, not a BJT.
        # Do not let the prefix alone decide when the model token is explicit.
        if prefix == "q" and _looks_like_mos_model(_model_token(tokens)) and len(tokens) >= 6:
            prefix = "m"

        if prefix == "m":
            nodes, model, param_tokens = _parse_mos(instance, tokens, line_no, warnings)
            kind = "mos"
        elif prefix == "c":
            nodes, model, param_tokens = _parse_two_terminal(instance, tokens, line_no, warnings, kind="cap")
            kind = "cap"
        elif prefix == "r":
            nodes, model, param_tokens = _parse_two_terminal(instance, tokens, line_no, warnings, kind="res")
            kind = "res"
        elif prefix == "d":
            nodes, model, param_tokens = _parse_two_terminal(instance, tokens, line_no, warnings, kind="diode")
            kind = "diode"
        elif prefix == "l":
            nodes, model, param_tokens = _parse_two_terminal(instance, tokens, line_no, warnings, kind="inductor")
            kind = "inductor"
        elif prefix == "q":
            rest = tokens[1:]
            if len(rest) < 4:
                warnings.append(f"line {line_no}: {instance} needs at least three terminals and a model")
                nodes, model, param_tokens = rest[:3], "", []
            else:
                nodes, model = rest[:3], rest[3]
                param_tokens = rest[4:]
            kind = "bjt"
        elif prefix == "x":
            nodes, model, param_tokens = _parse_subckt_instance(instance, tokens, line_no, warnings)
            kind = "subckt"
        else:
            warnings.append(f"line {line_no}: unsupported device prefix in {instance!r}; kept as other")
            nodes, model, param_tokens = tokens[1:], "", []
            kind = "other"

        params = _parse_params(param_tokens)
        if kind in ("cap", "res") and model and _NUMBER_RE.match(model) and "value" not in params:
            params["value"] = model
        if kind in ("mos", "cap", "res") and not model:
            warnings.append(f"line {line_no}: {instance} has no model/value")

        if instance in seen:
            warnings.append(f"line {line_no}: duplicate device name {instance!r}")
        seen.add(instance)

        all_devices.append(
            Device(
                name=instance,
                kind=kind,
                nodes=nodes,
                model=model,
                params=params,
                line_no=line_no,
                subckt=current_subckt,
                raw=line,
            )
        )

    if not all_devices:
        warnings.append("no devices found")

    # Choose the top-level subcircuit: one that is not instantiated. If there is
    # no subcircuit, all devices belong to the top level.
    instantiated = {device.model for device in all_devices if device.kind == "subckt"}
    candidates = [definition for definition in subckts if definition.name not in instantiated]
    if not candidates:
        candidates = subckts
    top: SubcktDef | None = None
    if candidates:
        counts = {definition.name: 0 for definition in candidates}
        for device in all_devices:
            if device.subckt in counts:
                counts[device.subckt] += 1
        top_name = max(candidates, key=lambda definition: counts[definition.name]).name
        top = next(definition for definition in candidates if definition.name == top_name)
        devices = [device for device in all_devices if device.subckt == top_name]
        subckt_name = top_name
        ports = list(top.ports)
        skipped = sorted({device.subckt for device in all_devices if device.subckt and device.subckt != top_name})
        if skipped:
            warnings.append("annotation focused on top subckt; skipped: " + ", ".join(skipped))
    else:
        devices = all_devices
        subckt_name = name or Path(source).stem
        ports = []

    # Keep only pin directions that belong to the selected top subckt.
    if top is not None:
        port_set = set(ports)
        pin_directions = {key: value for key, value in pin_directions.items() if key in port_set}

    design_name = name or (top.name if top else Path(source).stem)
    return Netlist(
        source=source,
        name=design_name,
        subckt=subckt_name,
        ports=ports,
        pin_directions=pin_directions,
        devices=devices,
        subckts=subckts,
        globals=globals_,
        warnings=warnings,
    )


def parse_file(path: str | Path, *, name: str | None = None) -> Netlist:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    return parse_text(text, source=str(file_path), name=name or file_path.stem)