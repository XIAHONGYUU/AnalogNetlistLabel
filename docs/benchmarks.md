# 基准 — 2026-10-31

本页记录 v0.1/v0.2 baseline。它是诊断，不是“通用准确率”声明。下面的 reference 是早期 agent 写的提案，不是 ground truth。

## 测试对象

| 对象 | 规模 | 用途 |
| --- | --- | --- |
| examples/generic_ota/generic_ota.sp | 8 MOS + 1 C | 合成 two-stage OTA；全部 XM*/XC*，无 role token |
| sky130_am_ip__ldo_01v8 / ldo.sp | 41 MOS + 3 R + 2 C + 2 X | 真实开源 LDO；所有 MOS 都是 XM* 通用名 |
| sky130_am_ip__ldo_01v8 / ldo.annotated.sp | reference | 旧 agent 提案，仅用于对比 |

LDO 网表从外部 Analog2Layout checkout 读取，不复制进仓库；上游 Apache-2.0。

## 合成 generic OTA

命令：

    python3 -m netlistlabel analyze examples/generic_ota/generic_ota.sp --out out/generic_ota

| 指标 | 值 |
| --- | --- |
| device role coverage | 9/9 = 100% |
| MOS role coverage | 8/8 = 100% |
| matched devices | 4/9 = 44% |
| review items | 2 |
| mean confidence | 0.83 |
| blocks | AMP（XM1–XM5）、OUT（XM6–XM7）、BIAS（XM8）、PASSIVE（XC1） |

主要提案：

| 器件 | role | group | match | 依据 |
| --- | --- | --- | --- | --- |
| XM1/XM2 | input_pair | AMP | DP_AMP | shared source tail、gates inp/inn、对称 PMOS load |
| XM3 | tail_current | AMP | — | drain tail 是 pair source，source vss |
| XM4/XM5 | current_mirror | AMP | LOAD_AMP | diode XM4 设 PMOS load mirror |
| XM6 | output_stage | OUT | — | drain out，width 6 µm ≥ 2× median |
| XM7/XM8 | current_mirror | OUT/BIAS | — | 共享 gate pbias，XM8 是 diode reference |
| XC1 | compensation | PASSIVE | — | n2–out 之间的 cap；block 边界有歧义 |

review 项：XC1（cap 结构清楚，但 AMP/OUT 边界模糊）。

## SKY130 LDO raw

命令：

    python3 -m netlistlabel analyze /path/to/sky130_am_ip__ldo_01v8/ldo.sp --out out/ldo_raw

| 指标 | 值 |
| --- | --- |
| device role coverage | 48/48 = 100% |
| MOS role coverage | 41/41 = 100% |
| matched devices | 16/48 = 33% |
| review items | 7 |
| mean confidence | 0.77 |
| blocks | AMP、OUT、BIAS、REF、START、CTRL_EN、CTRL_SEL、FB、PASSIVE |

恢复出的结构：

- 输入对 XM52/XM53、tail XM54；
- PMOS load mirror XM46/XM56、cascode XM57/XM58；
- 第二级 mirror XM48/XM55；
- pass device XM61（m=1000）、pass driver XM59、gate current source XM60；
- bias mirror/cascode XM62–XM69、degeneration resistor XR6；
- reference stack XM79–XM82；
- startup chain XM70–XM74；
- enable inverter/switch family XM83–XM90 和 x1；
- select/trim mux family XM75–XM78 和 x2；
- feedback divider XR4/XR5 at VM。

## 与旧 reference 的对比

命令：

    python3 -m netlistlabel compare /path/to/ldo.sp /path/to/ldo.annotated.sp --out out/ldo_eval

| 指标 | 值 |
| --- | --- |
| compared MOS | 41 |
| exact role agreement | 31/41 = 75.6% |
| a2l-role agreement | 36/41 = 87.8% |
| partition pair agreement | 97.8% |
| exact match groups | 6（precision 85.7%，recall 100%） |

### role 分歧

| 器件 | NetlistLabel | reference | 评价 |
| --- | --- | --- | --- |
| XM48 | current_mirror | bias | 两边都能解释。XM48 是 XM48/XM55 第二级 mirror 的 diode reference；结构上 current_mirror，功能上可叫 bias。 |
| XM55 | current_mirror | bias | 同 XM48；reference 把整条第二级 bias 分支叫 bias。 |
| XM68 | bias | current_mirror | XM68 是单个 diode PMOS，生成 VBIAS_C 给 cascode；形状像 mirror reference，但没有同 source 的 partner，所以 v0.1 保持 bias。 |
| XM74 | current_mirror | bias | XM74 是 startup chain 里的 VBIAS_N mirror；结构 role current_mirror，功能 block START。 |
| XM80 | cascode | bias | XM80 是 self-biased reference stack 的 upper device；结构 cascode，功能 bias 更宽。 |

这 5 个是**语义边界**，不是 parser 失败。其中 4 个（XM48/XM55/XM74/XM80）说明 taxonomy 把 structure 和 function 混在一起；v0.2 应拆开，而不是让一个 role 回答两个问题。

### match group

reference 的 6 个 match group 全部被精确恢复：

- DP_AMP = XM52/XM53
- LOAD_AMP = XM46/XM56
- CAS_AMP = XM57/XM58
- MIR_BIAS_VBIAS_P = XM62/XM64
- CAS_BIAS = XM63/XM65
- MIR_BIAS_DEG = XM66/XM67

另外多提了一个 XM48/XM55（第二级 bias mirror）。它不在 reference 的 match list 里，所以 precision 是 85.7% 而不是 100%。这个额外 group 结构上合理，但需要人工确认。

## v0.2 semantic core 补充

v0.2 增加了 port/net first-class 对象。同一批 fixture：

| fixture | ports | port class coverage | nets | net class coverage | net structural-role coverage | review |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| generic OTA | 7 | 100% | 10 | 100% | 100% | 2 |
| SKY130 LDO raw | 8 | 100% | 33 | 100% | 100% | 7 |

LDO 恢复的例子：AVDD/AVSS power/ground；ENA enable；VREF_EXT reference；SEL_EXT select；VOUT output；VPASS pass_gate；VM feedback；VERR gain_node；VSTART startup；VREF_INT reference。generic OTA 里 inp/inn 是差分 signal group IN，nbias/pbias 是 bias，tail/mirror/output net role 正确。

注意：这些 coverage 是结构/类别分配，不是 ground-truth accuracy。net class 仍有保守的 signal/internal fallback；invariance/OOD 测试已加入，但不能替代人工 gold set。这是 smoke baseline，不是泛化声明。

## 当前 review queue（LDO）

| 器件/net | 原因 |
| --- | --- |
| XM60 | mirror vs bias fan-out；pass driver 的 current source |
| XM79 | mirror vs bias fan-out；reference stack 的 current source |
| XM70 | 低置信度 bias/startup 器件 |
| XM82 | 低置信度 self-biased reference bias 器件 |
| XC1 | rail cap：decap vs compensation 有歧义；无 stated capacitance |
| XC3 | rail cap：decap vs compensation 有歧义；无 stated capacitance |
| VERR | gain_node 置信度 0.65，低于 0.70 |

## 人工复核 smoke（2026-11-01）

| gold | 范围 | 结果 | 说明 |
| --- | --- | --- | --- |
| ldo_quick.gold.json | LDO 10 device + 6 net + 8 port = 24 | 24/24 accept | 人工逐项确认；含 XM59 source follower、XM55 common-source、XM48 mirror reference、net2 interstage 修正 |
| generic_ota.gold.json | OTA 9 device + 10 net + 7 port = 26 | 26/26 accept | 换拓扑回归；规则不是只对 LDO 过拟合 |
| ldo_reviewed.gold.json | LDO 44 device + 6 net + 8 port = 58 | 58/58 accept | LDO 41/41 MOS 全覆盖；net/port 仍是抽样，未覆盖 27 net + XC3/XR6 |

这不是独立双盲准确率：所有项都是人工逐项 accept；它的作用是 regression smoke，证明“已确认样本”与当前输出一致。文件在 benchmarks/gold/，源网表不提交。

## 已知限制

1. 层次不展开。x1/x2 从 model/port 判断为 level-shift logic，但内部器件不可见。
2. passive 值不发明。sky130 MIM cap 只有 W/L/m，不换算 pF；XR* 只有 L，不换算 ohm。报告标 value_known=false。
3. block 边界粗。第二级 bias diode XM48 在 AMP；comp cap XC1 在 PASSIVE；两者都记录/标注。
4. match group 是局部的。大 bias fan-out 不变成一个巨大 match group；只提同 block 的 two-device group 和显式退化 mirror pair。
5. 无 waveform/operating-point 证据。只靠偏置电压才合理的器件无法完全解决。
6. reference label 不是 truth。75.6% exact agreement 是讨论起点，不是 accuracy 声明。

## Analog2Layout 集成

overlay 可直接被当前 a2l parser 消费：

    cd /path/to/project_analog2layout
    python3 -m a2l validate /path/to/ldo.annotated.sp --require-known-roles

结果：41 devices，OK: no structural errors。仍有 6 个 match-group warning（XM54、XM60、XM69、XM74、XM79、XM80）：结构识别出来了，但还没有 two-device local match proposal。这是下一步信号，不是 parse failure。

## 复现

    python3 -m unittest discover -s tests -v
    python3 -m netlistlabel analyze examples/generic_ota/generic_ota.sp --out out/generic_ota
    python3 -m netlistlabel analyze /path/to/ldo.sp --out out/ldo_raw
    python3 -m netlistlabel compare /path/to/ldo.sp /path/to/ldo.annotated.sp --out out/ldo_eval