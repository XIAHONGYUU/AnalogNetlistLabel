# 设计 — NetlistLabel v0.2

> **状态：** 本文描述 v0.1/v0.2 的机制。v0.2 port-first 核心已落在 ports.py 和 nets.py，schema 为 v0.2；device 级 abstention/margin、invariance/OOD、review/evaluate/CSV 已实现。仍待补：人工 gold set 校准、parser include/param/black-box/diagnostics、provenance。

## 一句话问题

开源模拟网表通常只告诉你“什么连着什么”，不告诉你“电路在做什么”。任务是把连接关系变成可复核的语义，同时不发明数值、不静默猜测。

## 三层

    layer 1  facts        解析 + 连接 + 器件类型 + W/L + rail + port
    layer 2  structures   diode、mirror、pair、tail、cascode、inverter、mux
    layer 3  semantics    role、match、class、block、confidence、evidence、review

只有 layer 1 被当作事实。layer 2/3 都是带证据的提案。源网表永远不改。

## Layer 1 — 事实

spice.py 解析：

- MOS 四端子、model、W/L/nf/m；
- R/C/D/Q 和 subckt instance；
- .subckt ports、.PININFO、.global；
- 续行、注释、bus 名称；
- XQ* MOSFET vs BJT 按 model 消歧。

facts.py 提供：

- rail：电源类 port、body 连接的 net、global supply；
- diode-connected MOS（gate net == drain net）；
- control net：control-like port，经 inverter 和 digital/level-shift subckt 传播；
- 按总宽度相对 median 的 pass/output 候选；
- 按 (type, gate, source) 的 mirror cluster；
- shared source、distinct gate/drain、对称 load 的 differential pair；
- 从 rail 喂 pair source 的 tail；
- upper source 是 lower drain、局部 series net、bias-like gate 的 cascode；
- shared drain、不同 source、control gate 的 mux。

每个事实都带 net/device 名，evidence 可人工核对。

## Layer 2 — 结构

structure id 和 role 故意分开：

- diode_connected、mirror_member、mirror_reference、mirror_candidate；
- diff_pair、tail、cascode、stack_member；
- inverter、mux、level_shift、control_switch；
- pass、pass_driver、output_stage；
- cap_to_rail、series_divider、degeneration、supply。

一个器件可以有多个 structure；role 是最终选中的语义答案。

## Layer 3 — role、net class、block

role taxonomy 在 taxonomy.py。它比 Analog2Layout 宽，因为陌生网表需要 pass_device、feedback、reference、logic、switch。

a2l_role 映射是显式的，静态映射之外只有一个动态情况：输入是传播后的 enable/select net 的 logic inverter，语义 role 仍是 logic，但 a2l_role 映射为 enable_switch/adj_switch。这样 overlay 对 a2l 有用，又不假装 inverter 是功能 role。

port 分类在 ports.py：

- direction：input/output/bidirectional/power/ground/unknown；
- class：power/ground/reference/bias/signal/control/clock/reset/enable/select/interface/unknown；
- interface、quantity、polarity、差分/总线、anchors、candidates、conflicts。

net 分类在 nets.py：

- class：power/ground/reference/bias/signal/control/clock/reset/enable/select/interface/unknown；
- structural role：supply/ground/input/output/tail/mirror_gate/cascode_mid/pass_gate/feedback/reference/startup/gain_node/degeneration/bias_bus/control/internal/unknown；
- block、差分/总线、candidates、conflicts、anchors。

block 聚合故意粗：

- AMP：从非 rail/非 control/非 bias 的 signal input port 可达的 signal path，排除 pass 和它的 gate-drive 网络；
- OUT：pass device + gate-drive 网络上的器件，或 output-port 上的大器件；
- BIAS/REF/START：signal path 外的 bias-role 器件，按 ref/start hint 和局部 source/drain 增长拆分；
- CTRL_EN/CTRL_SEL：enable/select 开关和 inverter family；
- FB：驱动 amplifier input 的 divider resistor；
- PASSIVE：剩余无源；
- UNKNOWN：没有结构 signature。

block 边界是提案。边界器件要记录，不静默重新分配。

## 置信度

confidence 不是“为真的概率”，是启发式接受度：

| 范围 | 含义 | 动作 |
| --- | --- | --- |
| 0.85–0.98 | 强局部结构 + port 锚定 | auto |
| 0.70–0.85 | 结构清楚但功能归属可争 | auto，可能仍 review |
| 0.55–0.70 | 合理候选 | confirm |
| < 0.55 | 弱/未解决 | confirm/unknown |

每个 device/net/port 至少一条 evidence。unknown 必进 review；低 confidence 也进 review。v0.2 还输出 device top_score/margin/candidates；阈值是启发式，需在 gold set 上校准。

## 规则目录（v0.2）

| 识别器 | 主要条件 | 典型 role |
| --- | --- | --- |
| pass | width ≥ 10× median，且在 output port | pass_device |
| output stage | output-port 端子，width ≥ 2× median | output_stage |
| diff pair | shared source、distinct gates/drains、对称 load、tail | input_pair |
| tail | drain 是 pair source，source 是 rail | tail_current |
| cascode | upper source = lower drain，局部 series net，bias-like gate | cascode |
| control switch | gate net 从 enable/select port 传播 | enable_switch/adj_switch |
| inverter | complementary pair，same gate/drain，opposite rail | logic（a2l: enable/adj switch） |
| mux | same drain、不同 source、两个 gate 都是 control net | adj_switch |
| mirror | same type/gate/source，diode reference 或两个 | current_mirror |
| degenerated mirror | same gate，一 source 接 rail，一 source 经 resistor | current_mirror |
| diode | gate == drain | bias 或 mirror reference |
| rail cap | 一端在 rail | decap |
| signal cap | 两个非 rail net | compensation |
| divider | resistor 共享 midpoint，驱动 pair gate | feedback |
| degeneration | resistor 从 MOS source 到 rail | bias |
| digital subckt | model 像 stdcell/buffer/level shift | logic |

## 假阳性防护

- cascode 需要局部 series 节点，不是 bias bus；
- control gate 不是 current mirror；
- 大 bias fan-out 不变成一个巨大 match group；只提同 block 的 two-device group 和显式退化 mirror pair；
- 接 rail 的 diode 不自动当 signal-stage load；
- match group 是一次性决策，不通过单器件传递式增长；
- port-first 后，bias port 不再靠名字（pbias→pb0 仍能识别）。

## 与 Analog2Layout 的集成

    raw .sp
      -> NetlistLabel annotation.json / .annotated.sp
      -> a2l validate --require-known-roles
      -> a2l analyze / build / white-line

overlay 只写 a2l_role 存在的 role=，并总是写 nll_role=，语义不丢。源文件不动。

## v0.2 新增对象

- ports.py：端口分类/锚定；nets.py：net class/结构角色/分组；
- model.py：PortAnnotation、NetAnnotation、Candidate、DeviceAnnotation、Block；
- infer.py：组装 ports -> devices -> nets -> blocks，输出 typed review queue；
- review.py：中文 review.md + review.csv + gold.json；
- evaluate.py：strict/lenient accuracy、confusion、auto precision、review rate，支持 CSV/JSON gold；
- 结构层新增 source_follower / common_source；cascode 输出驱动 common-source gate 的 net 标 signal + mirror_gate + interstage_signal（例如 LDO 的 net2）。

## 已知设计债

1. structure 和 function 还混在 role 字段里；v0.3 应拆 function。
2. 层次只识别，不展开；subckt instance 还是黑盒。
3. block 增长仍用 start/ref 名字 hint（有 hint 时）；generic net 只能靠连接。
4. 无值 passive 无法验证；model/W/L 不换算成电容/电阻。
5. evidence 还没有 source line provenance；黑盒边界未显式。
6. 无人 gold set 校准，所以 confidence 还不是统计置信度。
7. LLM 层尚未存在；先保持 deterministic baseline 可检查。