from __future__ import annotations

import unittest
from pathlib import Path

from netlistlabel.infer import annotate
from netlistlabel.spice import parse_file, parse_text

ROOT = Path(__file__).resolve().parents[1]


class PortAndNetInferenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.netlist = parse_file(ROOT / "examples" / "generic_ota" / "generic_ota.sp")
        cls.annotation = annotate(cls.netlist)
        cls.ports = cls.annotation.port_map()
        cls.nets = cls.annotation.net_map()

    def test_ports_are_first_class(self) -> None:
        self.assertEqual(self.ports["inp"].direction, "input")
        self.assertEqual(self.ports["inp"].electrical_class, "signal")
        self.assertEqual(self.ports["inp"].interface, "analog_input")
        self.assertEqual(self.ports["vdd"].electrical_class, "power")
        self.assertEqual(self.ports["vss"].electrical_class, "ground")
        self.assertEqual(self.ports["nbias"].electrical_class, "bias")
        self.assertEqual(self.ports["out"].direction, "output")
        self.assertEqual(self.ports["inp"].differential_group, "IN")

    def test_nets_have_classes_and_roles(self) -> None:
        self.assertEqual(self.nets["tail"].structural_role, "tail")
        self.assertEqual(self.nets["n1"].structural_role, "mirror_gate")
        self.assertEqual(self.nets["vdd"].structural_role, "supply")
        self.assertEqual(self.nets["vss"].structural_role, "ground")
        self.assertEqual(self.nets["out"].structural_role, "output")
        self.assertTrue(self.nets["out"].is_port)

    def test_review_queue_is_typed(self) -> None:
        kinds = {item["kind"] for item in self.annotation.review_queue}
        self.assertIn("device", kinds)
        self.assertIn("net", kinds)
        for item in self.annotation.review_queue:
            self.assertIn("name", item)
            self.assertIn("reasons", item)
            self.assertTrue(item["reasons"])


class MixedSignalPortTest(unittest.TestCase):
    def test_interface_bus_enable_clock_ports(self) -> None:
        text = """
.subckt ms VINP VINN VOUT ATD<3:0> DTA<3:0> ENN CLK VDD VSS
*.PININFO VINP:I VINN:I VOUT:O ATD<3:0>:I DTA<3:0>:O ENN:I CLK:I VDD:I VSS:I
XM1 VOUT VINP VSS VSS sky130_fd_pr__nfet_01v8 L=0.5 W=2 nf=1 m=1
XM2 VOUT VINN VSS VSS sky130_fd_pr__nfet_01v8 L=0.5 W=2 nf=1 m=1
.ends
"""
        annotation = annotate(parse_text(text, source="mixed.sp"))
        ports = annotation.port_map()
        self.assertEqual(ports["ATD<3:0>"].electrical_class, "interface")
        self.assertEqual(ports["ATD<3:0>"].interface, "atd")
        self.assertEqual(ports["ATD<3:0>"].bus, "3:0")
        self.assertEqual(ports["DTA<3:0>"].interface, "dta")
        self.assertEqual(ports["ENN"].electrical_class, "enable")
        self.assertEqual(ports["ENN"].polarity, "active_low")
        self.assertEqual(ports["CLK"].electrical_class, "clock")
        self.assertEqual(ports["VINP"].differential_group, "VIN")
        self.assertEqual(ports["VINN"].differential_group, "VIN")


class LdoPortAndNetTest(unittest.TestCase):
    def test_ldo_ports_and_nets(self) -> None:
        path = ROOT.parent / "project_analog2layout" / "examples" / "sky130_ldo_01v8" / "ldo.sp"
        if not path.exists():
            self.skipTest("external SKY130 LDO benchmark not available")
        annotation = annotate(parse_file(path))
        ports = annotation.port_map()
        nets = annotation.net_map()
        self.assertEqual(ports["AVDD"].electrical_class, "power")
        self.assertEqual(ports["AVSS"].electrical_class, "ground")
        self.assertEqual(ports["ENA"].electrical_class, "enable")
        self.assertEqual(ports["VREF_EXT"].electrical_class, "reference")
        self.assertEqual(ports["SEL_EXT"].electrical_class, "select")
        self.assertEqual(ports["VOUT"].direction, "output")
        self.assertEqual(nets["VPASS"].structural_role, "pass_gate")
        self.assertEqual(nets["VM"].structural_role, "feedback")
        self.assertEqual(nets["VBIAS_P"].structural_role, "mirror_gate")
        self.assertEqual(nets["VERR"].structural_role, "gain_node")
        self.assertEqual(nets["net2"].electrical_class, "signal")
        self.assertEqual(nets["net2"].structural_role, "mirror_gate")
        self.assertEqual(nets["net2"].function, "interstage_signal")
        self.assertEqual(nets["VSTART"].structural_role, "startup")
        self.assertEqual(nets["VREF_INT"].structural_role, "reference")
        self.assertIsNone(nets["AVDD"].block)


if __name__ == "__main__":
    unittest.main()