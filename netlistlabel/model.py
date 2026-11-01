"""Data model for the annotation proposal."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .taxonomy import a2l_role as map_a2l_role


@dataclass
class Alternative:
    role: str
    confidence: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role, "confidence": round(self.confidence, 3), "reason": self.reason}


@dataclass
class Candidate:
    """A competing semantic candidate with evidence on both sides."""

    label: str
    score: float
    kind: str = "role"
    evidence: list[str] = field(default_factory=list)
    negative_evidence: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "score": round(self.score, 3),
            "kind": self.kind,
            "evidence": self.evidence,
            "negative_evidence": self.negative_evidence,
            "reason": self.reason,
        }


@dataclass
class DeviceAnnotation:
    name: str
    kind: str
    dtype: str
    model: str
    role: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    negative_evidence: list[str] = field(default_factory=list)
    structures: list[str] = field(default_factory=list)
    alternatives: list[Alternative] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    group: str = ""
    match: str | None = None
    review: str = "auto"
    notes: str = ""
    width_um: float = 0.0
    l_um: float = 0.0
    nf: int = 1
    m: int = 1
    cap_pf: float = 0.0
    res_ohm: float = 0.0
    value_known: bool = True
    a2l_role_override: str | None = None
    semantic_id: str | None = None
    canonical_name: str | None = None
    top_score: float = 0.0
    margin: float = 0.0
    line_no: int = 0
    terminals: dict[str, str] = field(default_factory=dict)

    @property
    def a2l_role(self) -> str | None:
        return self.a2l_role_override or map_a2l_role(self.role)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "kind": self.kind,
            "type": self.dtype,
            "model": self.model,
            "terminals": self.terminals,
            "role": self.role,
            "a2l_role": self.a2l_role,
            "group": self.group or None,
            "match": self.match,
            "confidence": round(self.confidence, 3),
            "review": self.review,
            "structures": self.structures,
            "evidence": self.evidence,
            "negative_evidence": self.negative_evidence,
            "alternatives": [alt.to_dict() for alt in self.alternatives],
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "semantic_id": self.semantic_id,
            "canonical_name": self.canonical_name,
            "top_score": round(self.top_score, 3),
            "margin": round(self.margin, 3),
            "line_no": self.line_no,
        }
        if self.kind == "mos":
            data.update(
                {
                    "width_um": round(self.width_um, 3),
                    "l_um": round(self.l_um, 3),
                    "nf": self.nf,
                    "m": self.m,
                    "value_known": True,
                }
            )
        elif self.kind == "cap":
            data.update({"cap_pf": round(self.cap_pf, 4), "value_known": self.value_known})
        elif self.kind == "res":
            data.update({"res_ohm": round(self.res_ohm, 3), "value_known": self.value_known})
        if self.notes:
            data["notes"] = self.notes
        return data


@dataclass
class PortAnnotation:
    original_name: str
    direction: str
    electrical_class: str
    interface: str
    quantity: str
    polarity: str
    confidence: float
    differential_group: str | None = None
    bus: str | None = None
    semantic_id: str = ""
    canonical_name: str | None = None
    evidence: list[str] = field(default_factory=list)
    negative_evidence: list[str] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    anchors: list[str] = field(default_factory=list)
    review: str = "auto"

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_name": self.original_name,
            "direction": self.direction,
            "class": self.electrical_class,
            "interface": self.interface,
            "quantity": self.quantity,
            "polarity": self.polarity,
            "differential_group": self.differential_group,
            "bus": self.bus,
            "semantic_id": self.semantic_id,
            "canonical_name": self.canonical_name,
            "confidence": round(self.confidence, 3),
            "review": self.review,
            "evidence": self.evidence,
            "negative_evidence": self.negative_evidence,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "conflicts": self.conflicts,
            "anchors": self.anchors,
        }


@dataclass
class NetAnnotation:
    original_name: str
    electrical_class: str
    structural_role: str
    confidence: float
    is_port: bool = False
    function: str | None = None
    differential_group: str | None = None
    bus: str | None = None
    semantic_id: str = ""
    canonical_name: str | None = None
    block: str | None = None
    evidence: list[str] = field(default_factory=list)
    negative_evidence: list[str] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    anchors: list[str] = field(default_factory=list)
    review: str = "auto"

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_name": self.original_name,
            "is_port": self.is_port,
            "class": self.electrical_class,
            "structural_role": self.structural_role,
            "function": self.function,
            "differential_group": self.differential_group,
            "bus": self.bus,
            "semantic_id": self.semantic_id,
            "canonical_name": self.canonical_name,
            "block": self.block,
            "confidence": round(self.confidence, 3),
            "review": self.review,
            "evidence": self.evidence,
            "negative_evidence": self.negative_evidence,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "conflicts": self.conflicts,
            "anchors": self.anchors,
        }


@dataclass
class Block:
    id: str
    label: str
    kind: str
    devices: list[str]
    nets: list[str]
    ports: list[str]
    confidence: float
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "devices": self.devices,
            "nets": self.nets,
            "ports": self.ports,
            "confidence": round(self.confidence, 3),
            "evidence": self.evidence,
        }


@dataclass
class Annotation:
    schema_version: str
    design: dict[str, Any]
    devices: list[DeviceAnnotation]
    blocks: list[Block]
    review_queue: list[dict[str, Any]]
    coverage: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    ports: list[PortAnnotation] = field(default_factory=list)
    nets: list[NetAnnotation] = field(default_factory=list)

    def device_map(self) -> dict[str, DeviceAnnotation]:
        return {device.name: device for device in self.devices}

    def port_map(self) -> dict[str, PortAnnotation]:
        return {port.original_name: port for port in self.ports}

    def net_map(self) -> dict[str, NetAnnotation]:
        return {net.original_name: net for net in self.nets}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "design": self.design,
            "ports": [port.to_dict() for port in self.ports],
            "devices": [device.to_dict() for device in self.devices],
            "nets": [net.to_dict() for net in self.nets],
            "blocks": [block.to_dict() for block in self.blocks],
            "review_queue": self.review_queue,
            "coverage": self.coverage,
            "warnings": self.warnings,
        }