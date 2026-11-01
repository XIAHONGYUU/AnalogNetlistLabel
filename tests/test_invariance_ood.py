from __future__ import annotations

import random
import re
import unittest
from pathlib import Path

from netlistlabel.infer import annotate
from netlistlabel.spice import parse_file, parse_text

ROOT = Path(__file__).resolve().parents[1]
BASE = (ROOT / "examples" / "generic_ota" / "generic_ota.sp").read_text(encoding="utf-8")

DEVICE_MAP = {
    "XM1": "M901",
    "XM2": "M902",
    "XM3": "M903",
    "XM4": "M904",
    "XM5": "M905",
    "XM6": "M906",
    "XM7": "M907",
    "XM8": "M908",
    "XC1": "C909",
}
NET_MAP = {
    "n1": "a1",
    "n2": "b2",
    "tail": "t0",
    "out": "o0",
    "vdd": "p0",
    "vss": "g0",
    "inp": "i0",
    "inn": "i1",
    "nbias": "nb0",
    "pbias": "pb0",
}


def _rename(text: str, mapping: dict[str, str]) -> str:
    for old in sorted(mapping, key=len, reverse=True):
        text = re.sub(
            r"(?<![A-Za-z0-9_])" + re.escape(old) + r"(?![A-Za-z0-9_])",
            mapping[old],
            text,
        )
    return text


def _shuffle(text: str) -> str:
    lines = text.splitlines()
    body = [line for line in lines if line.startswith(("XM", "XC"))]
    head = [line for line in lines if line not in body and line.strip() != ".ends"]
    random.Random(7).shuffle(body)
    return "\n".join(head + body + [".ends", ""])


def _scale_wl(text: str) -> str:
    def scale(match: re.Match[str]) -> str:
        return f"{match.group(1)}={float(match.group(2)) * 0.4:g}"

    return re.sub(r"\b([WL])=(\d+(?:\.\d+)?)", scale, text)


def _annotate(text: str):
    return annotate(parse_text(text, source="memory.sp"))


def _device_signatures(annotation, name_map: dict[str, str] | None = None):
    result = {}
    for device in annotation.devices:
        name = (name_map or {}).get(device.name, device.name)
        result[name.lower()] = (device.role, device.group, device.match)
    return result


class MetamorphicInvarianceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = _annotate(BASE)
        cls.base_devices = _device_signatures(cls.base)

    def test_device_rename_invariance(self) -> None:
        annotated = _annotate(_rename(BASE, DEVICE_MAP))
        inverse = {new: old for old, new in DEVICE_MAP.items()}
        self.assertEqual(_device_signatures(annotated, inverse), self.base_devices)

    def test_net_rename_preserves_device_groups(self) -> None:
        annotated = _annotate(_rename(BASE, NET_MAP))
        self.assertEqual(_device_signatures(annotated), self.base_devices)

    def test_net_rename_preserves_net_semantics(self) -> None:
        annotated = _annotate(_rename(BASE, NET_MAP))
        base_nets = self.base.net_map()
        nets = annotated.net_map()
        for old, new in NET_MAP.items():
            if old not in base_nets or new not in nets:
                continue
            self.assertEqual(
                (base_nets[old].electrical_class, base_nets[old].structural_role),
                (nets[new].electrical_class, nets[new].structural_role),
                f"{old} -> {new}",
            )

    def test_line_shuffle_invariance(self) -> None:
        annotated = _annotate(_shuffle(BASE))
        self.assertEqual(_device_signatures(annotated), self.base_devices)

    def test_case_invariance(self) -> None:
        annotated = _annotate(BASE.lower())
        self.assertEqual(_device_signatures(annotated), self.base_devices)

    def test_wl_scale_invariance(self) -> None:
        annotated = _annotate(_scale_wl(BASE))
        self.assertEqual(_device_signatures(annotated), self.base_devices)

    def test_subckt_rename_invariance(self) -> None:
        annotated = _annotate(BASE.replace("ota_generic", "cell_x"))
        self.assertEqual(_device_signatures(annotated), self.base_devices)


class OodTest(unittest.TestCase):
    def _roles(self, text: str) -> set[str]:
        return {device.role for device in annotate(parse_text(text, source="ood.sp")).devices}

    def test_rc_filter_does_not_invent_analog_roles(self) -> None:
        text = """
.subckt rc in out vss
R1 in out 10k
C1 out vss 1n
.ends
"""
        roles = self._roles(text)
        for forbidden in ("input_pair", "current_mirror", "cascode", "tail_current", "pass_device"):
            self.assertNotIn(forbidden, roles)

    def test_resistor_divider_does_not_invent_analog_roles(self) -> None:
        text = """
.subckt div in out vss
R1 in out 10k
R2 out vss 10k
.ends
"""
        roles = self._roles(text)
        for forbidden in ("input_pair", "current_mirror", "cascode", "tail_current", "pass_device"):
            self.assertNotIn(forbidden, roles)

    def test_digital_inverter_does_not_invent_analog_roles(self) -> None:
        text = """
.subckt inv a y vdd vss
XM1 y a vss vss sky130_fd_pr__nfet_01v8 L=0.5 W=1 nf=1 m=1
XM2 y a vdd vdd sky130_fd_pr__pfet_01v8 L=0.5 W=2 nf=1 m=1
.ends
"""
        roles = self._roles(text)
        for forbidden in ("input_pair", "current_mirror", "cascode", "tail_current", "pass_device"):
            self.assertNotIn(forbidden, roles)


if __name__ == "__main__":
    unittest.main()