"""Write a proposal overlay: a copy of the source netlist with annotations.

The source file is never modified. The overlay is intended for review and for
downstream tools (Analog2Layout accepts role=/match=/group= parameters).
"""

from __future__ import annotations

import re
from pathlib import Path

from .model import Annotation
from .spice import Netlist


def overlay_filename(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or "design"
    return f"{safe}.annotated.sp"


def write_annotated_sp(netlist: Netlist, annotation: Annotation, path: str | Path) -> Path:
    source = Path(netlist.source)
    if not source.exists():
        raise FileNotFoundError(f"cannot write overlay: source netlist not found: {source}")
    lines = source.read_text(encoding="utf-8").splitlines()
    devices = annotation.device_map()

    for device in netlist.devices:
        index = device.line_no - 1
        if index < 0 or index >= len(lines):
            continue
        line = lines[index]
        if line.lstrip().startswith("*"):
            continue
        if "nll_role=" in line:
            continue
        annotation_device = devices.get(device.name)
        if annotation_device is None:
            continue
        tokens: list[str] = []
        if annotation_device.a2l_role:
            tokens.append(f"role={annotation_device.a2l_role}")
        tokens.append(f"nll_role={annotation_device.role}")
        if annotation_device.group:
            tokens.append(f"group={annotation_device.group}")
        if annotation_device.match:
            tokens.append(f"match={annotation_device.match}")
        if not tokens:
            continue
        if line.rstrip().endswith("\\"):
            lines[index] = line.rstrip()[:-1].rstrip() + " " + " ".join(tokens) + " \\"
        else:
            lines[index] = line.rstrip() + " " + " ".join(tokens)

    header = [
        "* NetlistLabel annotation overlay (PROPOSAL, NOT APPROVED)",
        f"* source: {netlist.source}",
        f"* design: {netlist.name}",
        "* role= is the Analog2Layout-compatible mapping; nll_role= is the extended",
        "* NetlistLabel role. Review annotation.md before using this in a flow.",
    ]
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(header + lines) + "\n", encoding="utf-8")
    return target
