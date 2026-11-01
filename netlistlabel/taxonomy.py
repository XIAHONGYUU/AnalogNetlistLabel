"""Role, structure, and block-label taxonomy.

Two layers are kept deliberately separate:

* `role` is the semantic answer to "what is this device doing?".
* `a2l_role` is the layout-facing mapping used by Analog2Layout. The a2l
  taxonomy is owned by Analog2Layout; this project does not silently add ids to
  it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoleInfo:
    id: str
    zh: str
    en: str
    a2l_role: str | None
    description: str


ROLES: dict[str, RoleInfo] = {
    "input_pair": RoleInfo(
        "input_pair", "差分输入对", "Input pair", "input_pair",
        "A transistor of a differential input pair.",
    ),
    "current_mirror": RoleInfo(
        "current_mirror", "电流镜", "Current mirror", "current_mirror",
        "A transistor that mirrors a current set by a reference device.",
    ),
    "cascode": RoleInfo(
        "cascode", "共源共栅", "Cascode", "cascode",
        "A stacked transistor inserted to raise output impedance or isolate.",
    ),
    "tail_current": RoleInfo(
        "tail_current", "尾电流源", "Tail current source", "tail_current",
        "The current source feeding the common source of a differential pair.",
    ),
    "output_stage": RoleInfo(
        "output_stage", "输出级", "Output stage", "output_stage",
        "A large-signal or drive transistor at an output node.",
    ),
    "pass_device": RoleInfo(
        "pass_device", "功率/传输管", "Pass device", "output_stage",
        "The large pass transistor of a regulator or power switch.",
    ),
    "compensation": RoleInfo(
        "compensation", "补偿电容", "Compensation capacitor", "compensation",
        "A capacitor used for loop compensation or feed-forward.",
    ),
    "decap": RoleInfo(
        "decap", "去耦电容", "Decoupling capacitor", "decap",
        "A capacitor across a supply rail or a low-impedance reference node.",
    ),
    "bias": RoleInfo(
        "bias", "偏置", "Bias", "bias",
        "A device in a bias generation or distribution branch.",
    ),
    "reference": RoleInfo(
        "reference", "基准", "Reference", "bias",
        "A device in a self-biased reference or reference-select network.",
    ),
    "feedback": RoleInfo(
        "feedback", "反馈网络", "Feedback", None,
        "A passive device in the feedback divider or feedback path.",
    ),
    "enable_switch": RoleInfo(
        "enable_switch", "使能开关", "Enable switch", "enable_switch",
        "A switch controlled by an enable/power-down signal.",
    ),
    "adj_switch": RoleInfo(
        "adj_switch", "Trim/选择开关", "Adjust/select switch", "adj_switch",
        "A switch controlled by a trim, select, or configuration signal.",
    ),
    "switch": RoleInfo(
        "switch", "通用开关", "Switch", None,
        "A switching device whose control function is not resolved.",
    ),
    "logic": RoleInfo(
        "logic", "逻辑/电平转换", "Logic / level shift", None,
        "A digital or level-shifting subcircuit instance.",
    ),
    "sense": RoleInfo(
        "sense", "检测/采样", "Sense", "sense",
        "A device in a current/voltage sense path.",
    ),
    "esd": RoleInfo(
        "esd", "ESD 保护", "ESD", "esd",
        "An ESD protection device.",
    ),
    "dummy": RoleInfo(
        "dummy", "Dummy", "Dummy", "dummy",
        "An electrically inactive matching/uniformity device.",
    ),
    "passive": RoleInfo(
        "passive", "无源器件", "Passive", None,
        "A resistor or other passive that is not yet assigned a function.",
    ),
    "unknown": RoleInfo(
        "unknown", "未标注", "Unknown", "unknown",
        "Not enough evidence to propose a role.",
    ),
}

ROLE_ORDER = list(ROLES)

# Structure ids are *facts*, not roles. One device can carry several.
STRUCTURES = {
    "diode_connected": "Gate tied to drain (or base tied to collector).",
    "mirror_member": "Shares gate and source with a mirror reference.",
    "mirror_reference": "The diode-connected reference of a mirror cluster.",
    "mirror_candidate": "Shares a mirror gate/source but needs review.",
    "diff_pair": "Member of a differential pair.",
    "tail": "Feeds the common source of a differential pair.",
    "cascode": "Source is the drain of another transistor in a stack.",
    "stack_member": "Part of a series stack, position not resolved.",
    "pass": "Very large device connected to an output/port/rail.",
    "inverter": "Complementary pair with tied gates and drains.",
    "mux": "Two branches selecting one node from two sources.",
    "level_shift": "A subcircuit instance that shifts a control level.",
    "cap_to_rail": "Capacitor with one terminal on a rail.",
    "series_divider": "Resistor in a series divider between output and rail.",
    "degeneration": "Resistor in a transistor source/emitter path.",
    "control_switch": "Gate driven by an enable/select/trim control net.",
    "source_follower": "Common-drain stage: drain at a rail/AC ground, source drives a load or the next gate.",
    "common_source": "Common-source stage: source at a rail, drain drives a load/current source, gate is the input.",
    "supply": "Device directly connected to a rail.",
}

BLOCK_KINDS = {
    "amplifier": "信号路径上的放大级",
    "bias": "偏置产生与分发",
    "reference": "基准/自偏置参考",
    "startup": "启动/踢偏电路",
    "output": "输出/功率级",
    "feedback": "反馈分压/补偿网络",
    "control": "使能、选择、trim 与电平转换",
    "passive": "未归类的无源网络",
    "unknown": "未能归类",
}


def a2l_role(role: str) -> str | None:
    info = ROLES.get(role)
    return info.a2l_role if info else None


def role_description(role: str) -> str:
    info = ROLES.get(role)
    return info.description if info else ""


def is_known_role(role: str) -> bool:
    return role in ROLES and role != "unknown"