# AnalogNetlistLabel

> **NetlistLabel v0.2.0 demo。** schema 和 API 仍可能变化；用于展示与复核，不用于生产签核。

> 给一个陌生网表一个**可复核的语义层**：端口是什么、器件在做什么、每个 net 属于什么电气类别/结构角色、哪些必须匹配、依据是什么、哪里还需要人确认。

NetlistLabel 面向开源社区里大量“只有连接关系和尺寸、没有语义”的模拟网表。它不改电路、不改 W/L、不发明规则；它输出一份带证据和置信度的**语义 overlay**，供工程师复核后写回或供下游工具消费。

**语义是契约，名字是渲染。** 原始器件名/net 名永远保留；规范名只是可选建议。

## 三分钟看懂

- **输入**：一个陌生、扁平、只有连接和尺寸的模拟 SPICE 网表；
- **输出**：带 evidence / confidence / review 的 ports、devices、nets、blocks 语义 overlay；
- **不改源文件**：原名字保留；annotated.sp 是独立提案副本；
- **当前 demo**：LDO 41/41 MOS 人工确认，generic OTA 26/26；41 个测试通过；
- **一条命令**：make demo（生成 annotation 和 gold evaluation）；
- **定位**：不是仿真器，不是版图工具，是陌生网表的语义入口。

## 1. 为什么做

现实中的开源模拟网表经常长这样：

    XM46 VX VBIAS_P AVDD AVDD sky130_fd_pr__pfet_g5v0d10v5 L=7 W=1 nf=1 m=1
    XM52 VX VREF net1 AVSS sky130_fd_pr__nfet_g5v0d10v5 L=0.5 W=2 nf=1 m=1
    XM53 VY VM net1 AVSS sky130_fd_pr__nfet_g5v0d10v5 L=0.5 W=2 nf=1 m=1

名字是 XM46，不是 M1_DP；没有 role=，没有 group=，也没有原理图注释。对下游工具来说，它只是一团 MOS 和节点：面积无法按角色估算，版图不知道谁和谁要匹配，设计意图完全丢失。

在 GUI 里，工程师同时看到名字、空间位置、层次、颜色、端口符号和设计记忆。AI 只看到文本：器件类型、连接、参数、名字。名字是其中信息密度最高、但最不可靠的一层：

- 命名规范好时，VINP/VINN、EN、ATD、IBP 几乎直接给出 domain/direction/function；
- 命名缺失时，结构是唯一证据；
- 命名错误或复制粘贴时，名字会主动误导 AI。

所以正确的关系不是“名字是事实”，而是：**名字是 prior，结构是 evidence，port 是强 prior，最终标注是 posterior。**

Analog2Layout 的标注模型已经把“名字 token → role/match/group”这条路走通了，但它自己写明了边界：名字没有语义 token 时，不拿拓扑硬猜成确定角色。真正需要补上的，正是这一段：

- 以 port 为锚点，恢复 CELL 的接口语义；
- 从连接关系识别基本结构：二极管连接、电流镜、差分对、尾电流、cascode 堆叠、开关、电容/电阻网络；
- 从结构恢复功能块：误差放大器、偏置、基准、启动、输出/功率级、反馈、使能/trim 控制；
- 恢复 net 的电气类别/结构角色/可恢复的功能语义；
- 给每个结论附上可检查的证据、竞争候选和置信度；
- 把“不确定”显式放进 review queue，而不是悄悄猜一个 role。

这就是 NetlistLabel 的定位：**不是另一个仿真器，也不是版图工具，而是陌生网表的语义入口。**

## 2. 项目定义

给定一个陌生的、扁平的模拟 CELL 网表及其端口，在不修改源网表的前提下，恢复：

- **ports**：方向、类别/接口、差分/总线分组；
- **devices**：role、match、group、结构标签；
- **nets**：电气类别、结构角色、差分/总线分组；
- **blocks**：功能块及其端口；
- **evidence/confidence/review**：正/负证据、竞争候选、冲突、待人工确认项。

输出是非破坏性的语义 overlay；原始名字保留，规范名可选。subckt 名字暂不处理，但 **port 名、方向、接口类型、差分/总线分组必须进入第一版**。

## 3. 输出是什么

一条命令：

    python3 -m netlistlabel analyze examples/generic_ota/generic_ota.sp --out out/generic_ota

当前得到三个文件：

| 文件 | 作用 |
| --- | --- |
| annotation.json | 机器可读的语义层：ports / devices / nets / blocks / candidates / evidence / review |
| annotation.md | 人读的复核报告：端口、net、器件、功能块、覆盖率、需要确认的项 |
| <design>.annotated.sp | 在原网表上追加 role= / match= / group= 的提案副本；原文件不动 |

v0.2 schema 已实现（alpha，字段仍可能调整）：

    {
      "schema_version": "0.2",
      "design": {"name": "ldo", "ports": [...], "rails": [...]},
      "ports": [
        {"original_name": "VINP", "direction": "input", "class": "signal",
         "interface": "analog_input", "differential_group": "VIN", "confidence": 0.95, "evidence": [...]}
      ],
      "devices": [
        {"original_name": "XM52", "role": "input_pair", "match": "DP_AMP",
         "group": "AMP", "confidence": 0.86, "evidence": [...]}
      ],
      "nets": [
        {"original_name": "net1", "class": "signal", "structural_role": "tail",
         "block": "AMP", "confidence": 0.85, "evidence": [...]}
      ],
      "blocks": [...],
      "review_queue": [...],
      "coverage": {...}
    }

注意：v0.2.0 demo 已实现 port-first semantic core、device abstention/margin、变形/OOD 测试和 review/evaluate/CSV；仍待 100–300 device gold 校准、parser include/param/黑盒/diagnostics 和层次展开。

## 4. 设计原则

1. **语义与名字分开。** role/class/group/match 是契约；规范名是可选渲染；原始名字永远保留。
2. **port-first。** port 是接口契约和最强锚点；没有 port，图是对称的、歧义的。
3. **事实与推断分开。** 连接、类型、W/L、二极管连接、端口方向是事实；role/class/block 是提案。
4. **每条结论都要有证据。** 证据必须可检查（共享节点、gate==drain、源接轨、对称负载、端口方向）。
5. **允许弃权。** 功能 role 可以是 unknown/ambiguous；结构事实和电气类别仍尽量高覆盖。覆盖率不是 KPI。
6. **名字是证据，不是事实。** 名字冲突要显式记录；结构/端口证据仲裁，不静默覆盖。
7. **非破坏性。** 原网表只读；输出是独立 JSON、报告和提案副本；重命名副本只是可选导出。
8. **确定性核心 + AI 语义层。** 图结构、端口锚定和规则由 Python 确定性地算；LLM 只负责在证据之上提议/解释，不能改几何和数值。
9. **workflow 先于 MCP。** 先有确定性 CLI/workflow；schema 冻结后再写 SKILL.md，最后做薄 MCP wrapper。
10. **不发明。** 不发明 W/L、foundry 规则、net 功能；不声称 DRC/LVS/PEX。

## 5. 处理链

    .sp netlist
       |
       v
    [parse] 器件 / 节点 / 端口 / 子电路 / 参数 / diagnostics
       |
       v
    [ports] 方向、类别、接口、差分/总线分组、锚定结构
       |
       v
    [facts] 轨/域、二极管连接、镜像簇、差分对、尾电流、cascode、反相器、传输门
       |
       v
    [candidates] 所有可能的结构匹配；positive/negative evidence、score、margin
       |
       v
    [decisions] port/block/supply/signal-chain 上下文 -> role/class/group/match
       |
       v
    [review] unknown/ambiguous/冲突/低置信度
       |
       v
    annotation.json / annotation.md / *.annotated.sp

## 6. 快速开始

要求：Python 3.11+，无第三方依赖。

    git clone https://github.com/XIAHONGYUU/AnalogNetlistLabel.git
    cd AnalogNetlistLabel
    python3 -m unittest discover -s tests -v
    make demo

或者逐步运行：

    python3 -m netlistlabel analyze examples/generic_ota/generic_ota.sp --out out/generic_ota

真实例子（仓库外，sky130 开源 LDO 原始网表，41 MOS 全部是 XM* 通用名）：

    python3 -m netlistlabel analyze \
      /path/to/sky130_am_ip__ldo_01v8/ldo.sp \
      --out out/sky130_ldo_raw

对比参考标注（用于评估，不作为真值）：

    python3 -m netlistlabel compare \
      /path/to/ldo.sp \
      /path/to/ldo.annotated.sp \
      --out out/ldo_eval

生成人工复核包（中文 Markdown + review.csv + gold.json）：

    python3 -m netlistlabel review out/v02_ldo/annotation.json --out review/ldo

复核后评分（推荐直接改 review.csv，Excel 友好）：

    python3 -m netlistlabel evaluate out/v02_ldo/annotation.json review/ldo/review.csv --out out/eval/ldo

review.csv 里只改 decision 和标签字段；decision=accept/correct/ambiguous。gold.json 也支持。

## 7. 当前状态（2026-11-01）

v0.2 semantic core 已实现：

- SPICE 子集解析：MOS / R / C / D / 子电路实例、.subckt、.PININFO、续行、注释；
- 轨识别、器件事实、二极管连接、镜像簇、差分对、尾电流、cascode、反相器/传输门；
- **port 一等对象**：方向、类别、接口、quantity、polarity、差分/总线分组、anchors、候选、冲突；
- **net 语义层**：电气类别（power/bias/signal/control/...）+ 结构角色（tail/mirror_gate/pass_gate/feedback/gain_node/...）+ 差分/总线分组；
- 器件级 role / match / group 提案，带 evidence、confidence、alternatives、candidates；
- 功能块级聚合：信号路径、偏置、控制、反馈、输出；
- 三件套输出 + 分层覆盖率 + 类型化 review queue（device/port/net）；
- 在通用名 OTA 与 sky130 LDO 原始网表上的 smoke/benchmark（数字见 docs/benchmarks.md）；
- 41 个 unittest 通过；
- 人工 smoke gold：LDO 41/41 MOS（合并 58 项）+ generic OTA 26/26；
- LDO 对既有参考：75.6% exact role、87.8% a2l-role、97.8% partition pair、6/6 match group。

仍然待完成（demo 余项）：

- device 级 hard unknown / soft confirm 与 margin 已输出，但阈值仍需在金标准上校准；
- block 边界仍然是启发式；port-first 锚定已消除 XM8 pbias 改名回归，但真实 IP 的块边界仍需金标准检验；
- 变形不变性/OOD 测试已加入，但还需要更多真实 IP 变体；
- parser 还缺 include/param/黑盒/diagnostics；bus 名称目前只在 port/net 分类层处理；
- 已有 CI；SKILL.md 和 MCP 仍按 D015 延后；
- 规范名生成器仍是保守的（只给 tail/cascode_mid/pass_gate/feedback 等少数结构名），多数内部 net 保持 unnamed。

## 8. 路线图

**v0.2.0 — demo（已完成）**

- [x] port-first schema：ports + devices + nets + blocks + evidence/confidence/review；
- [x] port 分类/锚定；net class/structural role；
- [x] positive/negative evidence、candidate score/margin、device 级 hard unknown/soft confirm；
- [x] 变形不变性 + OOD 测试（device/net rename、shuffle、case、W/L scale、subckt rename、RC/divider/digital）；
- [x] LDO 41/41 MOS + OTA 26/26 人工 smoke gold；
- [~] parser: bus 名称、XQ/MOS 前缀已支持；include/param/black-box/diagnostics + 可选 adapter 接口仍待补。

**v0.3 — constraints 与 skill**

- mirror ratio、same L/finger、cascode compliance 等约束提案；
- SKILL.md（schema 冻结后）；
- 100–300 device 人工金标准 + evaluator；HF 130k 分层抽样 benchmark。

**later — MCP**

- 确定性 CLI 稳定后，做薄 MCP wrapper；
- 一个高层 annotate_cell + 只读 inspection tools；
- 多步组合/重试/人工 gate 留在代码/orchestrator，不放进 MCP server。

## 9. 与 Analog2Layout 的关系

Analog2Layout 从**已有语义的网表**出发做面积/floorplan/白线；NetlistLabel 补的是它前面的那一段：

    开源网表（无标签）
        -> NetlistLabel（ports/devices/nets/blocks + evidence）
        -> a2l annotation overlay / annotated.sp
        -> Analog2Layout area / floorplan / white-line

因此本项目的 a2l_role 字段尽量对齐 a2l 的 14 个 role；语义更细的部分（pass_device、feedback、reference、switch、logic）保留在 NetlistLabel 自己的 role 里，导出时显式映射，不污染 a2l 的所有权边界。

## 10. 设计细节与基准

- 架构、规则表、置信度、失败模式：docs/design.md
- LDO / OTA 基准数字、参考对比、五个分歧：docs/benchmarks.md
- 开源同类工具、agent skill、数据集盘点：docs/landscape.md
- 同类项目逐项优劣势与可借鉴经验：docs/prior-art-analysis.md
- 如何判断标注是否正确、评测协议与 release gate：docs/evaluation.md
- 已接受的决策记录：DECISIONS.md
- 当前行动与 v0.2 验收条件：CURRENT_TASK.md

## 11. 仓库结构

    netlistlabel/
      spice.py       SPICE 子集解析
      facts.py       连接图与结构事实
      ports.py       端口分类、锚定、差分/总线
      nets.py        net 电气类别/结构角色/分组
      model.py       ports/devices/nets/blocks 数据模型
      taxonomy.py    role/块标签/a2l 映射
      infer.py       器件级规则推理与装配
      blocks.py      功能块聚合
      report.py      JSON / Markdown 输出
      review.py      中文复核包 + review.csv + gold.json
      evaluate.py    金标准评分（strict/lenient/confusion）
      benchmarks/gold/ 人工确认的 smoke gold（不含源网表）
      overlay.py     带注释的 .sp 副本
      cli.py         命令行
    schemas/         annotation.schema.json
    examples/        通用名合成网表；真实网表用外部路径
    tests/           unittest + benchmark + gold smoke
    benchmarks/gold/ 人工确认的 smoke gold（不含源网表）
    scripts/demo.sh  一条命令跑 OTA demo
    docs/            设计说明、基准、landscape、prior-art analysis
    CHANGELOG.md     版本记录
    CITATION.cff     引用信息
    DISCLAIMER.md    边界声明
    CONTRIBUTING.md  贡献约定

## 12. License

Apache-2.0。合成网表可自由使用；真实开源网表只作为外部 benchmark 引用，不复制进仓库，除非其许可证明确允许并保留归属。

引用信息见 CITATION.cff；版本记录见 CHANGELOG.md；边界声明见 DISCLAIMER.md。