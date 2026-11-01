from __future__ import annotations

import unittest
from pathlib import Path

from netlistlabel.spice import parse_file, parse_text

ROOT = Path(__file__).resolve().parents[1]


class SpiceParserTest(unittest.TestCase):
    def test_generic_ota_example(self) -> None:
        netlist = parse_file(ROOT / "examples" / "generic_ota" / "generic_ota.sp")
        self.assertEqual(len(netlist.devices), 9)
        self.assertEqual(sum(1 for device in netlist.devices if device.is_mos), 8)
        self.assertEqual(netlist.ports, ["inp", "inn", "out", "vdd", "vss", "nbias", "pbias"])
        self.assertEqual(netlist.pin_directions["out"], "O")
        mos = netlist.device_by_name()["XM1"]
        self.assertEqual(mos.type, "nmos")
        self.assertEqual(mos.nodes, ["n1", "inp", "tail", "vss"])
        self.assertAlmostEqual(mos.w_um, 2.0)
        self.assertAlmostEqual(mos.l_um, 0.5)
        self.assertAlmostEqual(mos.width_um, 2.0)

    def test_spectre_node_list_and_value_style_passive(self) -> None:
        text = """
.subckt s a b c
M1 (d g s b) nmos w=1 l=0.5 nf=2 m=3
C1 d s 1.5p
R1 d s 10k
.ends
"""
        netlist = parse_text(text, source="memory.sp")
        by_name = netlist.device_by_name()
        self.assertEqual(by_name["M1"].nodes, ["d", "g", "s", "b"])
        self.assertAlmostEqual(by_name["M1"].width_um, 6.0)
        self.assertAlmostEqual(by_name["C1"].cap_pf, 1.5)
        self.assertAlmostEqual(by_name["R1"].res_ohm, 10000.0)

    def test_xq_mosfet_is_not_forced_to_bjt(self) -> None:
        text = """
.subckt s d g s b
XQ7 d g s b sky130_fd_pr__nfet_01v8 L=1 W=2 nf=1 m=1
.ends
"""
        netlist = parse_text(text, source="memory.sp")
        device = netlist.device_by_name()["XQ7"]
        self.assertEqual(device.kind, "mos")
        self.assertEqual(device.type, "nmos")
        self.assertEqual(device.nodes, ["d", "g", "s", "b"])

    def test_subckt_selection(self) -> None:
        text = """
.subckt leaf a b
M1 a a b b nmos w=1 l=1
.ends
.subckt top x y
X1 x y leaf
.ends
"""
        netlist = parse_text(text, source="memory.sp")
        self.assertEqual(netlist.subckt, "top")
        self.assertEqual([device.name for device in netlist.devices], ["X1"])
        self.assertEqual(netlist.devices[0].kind, "subckt")


if __name__ == "__main__":
    unittest.main()