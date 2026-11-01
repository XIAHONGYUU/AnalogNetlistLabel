# 同类项目与数据集 — 开源 landscape

搜索日期：2026-10-31。来源：GitHub repository search、README、Hugging Face dataset card。star/license 是快照，不代表质量。

## 深分析

每个项目的优势、劣势、代码级经验和 NetlistLabel 的具体改造建议，见 [prior-art-analysis.md](prior-art-analysis.md)。本页是索引，那一页是工程 memo。

## 短答

没有找到完全符合 NetlistLabel 契约的项目：

- 逐器件 role + match + group；
- 功能块划分；
- evidence + confidence + review queue；
- 可被 Analog2Layout 消费的 overlay。

但有几个很近的项目，其中一个在结构层的哲学几乎一样。

## 最接近的项目

| 项目 | 做什么 | 重叠 | 差距 |
| --- | --- | --- | --- |
| [analog-topology-classifier](https://github.com/Muntaha15/analog-topology-classifier)（MIT，0★） | terminal-aware graph、primitive facts、rule scoring、evidence + confidence + abstention，4 种 topology | 几乎相同的“facts → structures → evidence → confidence → unknown”哲学 | 整网表 4 分类；没有 per-device role/match/group，没有 block，没有 a2l overlay |
| [CircuitGenome](https://github.com/analog-ml/CircuitGenome)（MIT，7★） | op-amp 正向合成 + 反向识别 functional block/role（diff pair、mirror、cascode load、bias、CMFB、compensation） | 最接近“从 flat SPICE 恢复功能 role” | op-amp 中心；有自己的网表约定；不是通用 LDO/陌生 IP 标注器 |
| [analog-design-cli](https://github.com/L-Trump/analog-design-cli)（MIT，5★） | SPICE/Spectre/HSPICE parser + 结构查询 CLI，层级、alias、focus/trace、JSON/YAML；自带 skills/SKILL.md | 最好的“agent 读网表” skill；明确把语义留在外面 | 没有 role/block/annotation proposal；它是结构证据层 |
| [pyckt](https://github.com/cda-tum/pyckt)（4★，未检测到 license） | ACST 风格 topology generation、结构识别、stage partitioning | 学术先例 | recognition/partitioner 是 stub；研究骨架，不是可用工具 |
| [netlist-parser](https://github.com/rohaansch/netlist-parser)（MIT，5★） | SPICE/Spectre/CDL/DSPF parser | 可复用 parser | 只有 parser |
| [circuitgraph](https://github.com/circuitgraph/circuitgraph)（132★） | circuits as graphs | 图基础设施 | 偏数字/门级，不是 analog role |
| [spice-canonical](https://github.com/smldis/spice-canonical)（0★） | Eldo/ngspice canonical connectivity；Codex agent skill | 图规范化 + agent-facing parser | 早期；不是语义 |
| [general-mna](https://github.com/GLODI-Engineering/general-mna)（0★） | MNA + hierarchy flattening + block-graph | 层次/flatten 基础设施 | 仿真导向，不是 annotation |
| [diagen](https://github.com/Chaoos-404/diagen)（GPL-3.0，2★） | netlist → TikZ/SVG schematic；MCP + Claude Code skill | agent-facing netlist skill | 画图，不是语义 |
| [EEschematic](https://github.com/eelab-dev/EEschematic)（MIT，39★） | multimodal LLM：SPICE netlist → editable schematic | LLM + netlist understanding | 可视化，不是 role/block annotation |

## Agent skill 生态

| skill/hub | 相关性 |
| --- | --- |
| [awesome-ams-skills](https://github.com/Arcadia-1/awesome-ams-skills)（35★） | AMS skill 目录：Virtuoso/Spectre bridge、gm/ID sizing、Verilog-A、SAR ADC、block design、IO agent。没有直接“陌生网表标注” skill。 |
| [analog-agents](https://github.com/Arcadia-1/analog-agents)（84★） | 12 skills / 4 agents；librarian 会识别 topology，analog-audit 做静态 netlist audit。设计流程框架，不是 annotation overlay。 |
| [AnalogGym-Opt](https://github.com/Computing-Intelligent-Decision-Team/AnalogGym-Opt)（6★） | sizing/optimization + Claude Code skills + MCP；不标注陌生器件。 |
| [mcp-spice](https://github.com/zesun33/mcp-spice)（0★，Apache badge） | MCP 跑 ngspice 返回 .meas；仿真，不是语义。 |
| [AnalogAgent](https://github.com/TheWind-upBird/Analogagent)（MIT，14★） | multi-agent analog design/sizing；不是 annotation。 |
| [PANDA](https://github.com/PKU-IDEA/PANDA)（22★） | LLM topology → sizing → layout；不是陌生网表 annotation。 |
| [AnalogLoop](https://github.com/XIAHONGYUU/AnalogLoop)（CC-BY-4.0，0★） | semantic-netlist manifest（roles.yaml、validator、area gate）用于已知设计；不是陌生网表推断。 |

## 数据集

| 数据集 | 相关性 |
| --- | --- |
| [pphilip/analog-circuits-sky130](https://huggingface.co/datasets/pphilip/analog-circuits-sky130)（Apache-2.0） | 130,409 条 ngspice 仿真 SKY130 网表，49 topology families，topology-aware split，netlist_json + performance metrics。标签是 topology/performance 级，不是 per-device role/match/group；适合大规模 benchmark。 |

## 对 NetlistLabel 的意义

1. “evidence + confidence + abstention”不是独有；analog-topology-classifier 已经在 4 种 topology 上做了。NetlistLabel 的差异是 **per-device 语义、任意多 block 网表、下游 overlay**。
2. CircuitGenome 是 op-amp role 识别最强的先例；适合做 op-amp 对照，但不是通用陌生网表标注器。
3. analog-design-cli 是最值得复用的 parser/结构查询；它的 SKILL.md 是 agent skill 的好模板。它明确停在 connectivity evidence，这正是 NetlistLabel 要跨过的边界。
4. 生态里缺的不是“解析网表”和“仿真网表”，而是 **给不是自己写的网表做可复核语义 overlay**。
5. 130k 数据集适合规模化 benchmark，但没有 device-level ground truth；仍需要人工小子集。

## 下一步实验

1. 在 130k 数据集分层抽样，测 coverage/review/abstention，不只看覆盖率。
2. 在 analog-topology-classifier 的 4 个 topology 上对比；如果它更严谨，借它的 terminal-aware 特征。
3. 在 op-amp 子集上对比 CircuitGenome，记录它哪些假设在 LDO/reference/startup 上失效。
4. 复用 analog-design-cli 的 parser/skill 契约做层次和方言，而不是再写一个 parser。

## 许可证提示

- MIT：analog-design-cli、analog-topology-classifier、CircuitGenome、netlist-parser、EEschematic；可研究/复用，保留归属。
- Apache-2.0：130k SKY130 数据集；mcp-spice 带 Apache badge。
- GPL-3.0：diagen；不要把代码复制进 Apache-2.0 项目。
- 未检测到 license：pyckt、awesome-ams-skills、analog-agents、PANDA；复用前读条款，链接没问题。
