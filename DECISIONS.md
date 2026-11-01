# DECISIONS

NetlistLabel 的长期决策记录。每条写清楚：选择、理由、排除了什么。只有明确的人类指示才重新讨论。

## D001 — 范围：语义归一化，不是仿真/版图

- **决策：** 产品是陌生、扁平模拟 CELL 的语义层：解析、识别结构、提出 device role、net class/role、block/match，附加 evidence/confidence，输出可复核 overlay。不做仿真、sizing、place、route 或 signoff。
- **理由：** 开源网表只有能被理解才有价值。Analog2Layout 已覆盖下游面积/floorplan；重复做会模糊边界。
- **排除：** 以“跑 SPICE 从波形标注”或“直接把网表丢给 LLM”为主架构。

## D002 — 确定性事实优先，AI 语义第二

- **决策：** 连接、器件类型、W/L、diode、mirror/pair/stack、port class 都由确定性代码算。role/block 由规则提出；LLM 以后只能在事实上提议名字/解释，不能替代事实。
- **理由：** 可复现、可复核。没有证据的标签比 unknown 更糟。
- **排除：** 以 LLM-only 标注作为 baseline。

## D003 — 扩展 taxonomy + 显式 a2l 映射

- **决策：** NetlistLabel 保留比 a2l 更宽的语义 role（pass_device、feedback、reference、switch、logic、passive），并显式给 a2l_role 映射。a2l 的 role 表仍由 Analog2Layout 拥有。
- **理由：** pass FET、反馈电阻、level shifter 在陌生网表里有意义，即使 a2l 的版图 taxonomy 没有独立 id。
- **排除：** 静默重载 a2l role，或未经 owner 同意给 a2l 加 id。

## D004 — overlay 输出；源网表只读

- **决策：** 输出 annotation.json、annotation.md、<design>.annotated.sp（追加 role/match/group）。绝不修改输入。
- **理由：** 提案要可复核、可回退；用户源数据必须保留。
- **排除：** 原地改写或“修复”网表。

## D005 — 在通用名上 benchmark，参考不是真值

- **决策：** 主 benchmark 是外部 Analog2Layout checkout 里的 SKY130 LDO raw（41 MOS，通用名）。已有 ldo.annotated.sp 只作为对比参考，明确不是 ground truth。
- **理由：** 它真实、非平凡、正好覆盖“名字没有语义”的缺口。把旧 agent 提案当真值会把它的错误洗进 benchmark。
- **排除：** 不对参考做人工复核就报告 accuracy。

## D006 — 零运行时依赖

- **决策：** 核心只用 Python 标准库。
- **理由：** 方便在开源网表和 CI 上跑。可选 parser adapter 可以用外部工具，但不能成为核心路径。
- **排除：** 核心依赖 NetworkX、LLM SDK 或图库；它们只能出现在可选、单独文档化的层。

## D007 — v0.1 block 标签由规则生成

- **决策：** functional block 标签由 role 组合和图连通性生成；v0.1 不用 LLM naming。
- **理由：** block 层最不稳定；先建立确定性、可检查的 baseline，再加概率命名。
- **排除：** 第一里程碑就宣称 LLM 级 block naming。

## D008 — v0.1 暂时把结构和功能放在一个 role 里

- **决策：** 每个器件一个 semantic role + 一组 structural tags。role 可能混合结构和功能（cascode vs bias、mirror vs bias）；歧义通过 evidence、alternatives、block、review 暴露。
- **理由：** 一个 role 是对 Analog2Layout 和首轮 review 最小可用的 payload；现在就拆成独立 structure/function 字段会让 schema 在 taxonomy 校准前翻倍。
- **后果：** 与旧参考的 5 个 LDO disagreament 是预期的；v0.2 应引入显式 function 字段，而不是让一个 role 回答两个问题。

## D009 — logic inverter 的动态 a2l 映射

- **决策：** 输入是传播后的 enable/select net 的 logic inverter，保持 role=logic，但 a2l_role 设为 enable_switch 或 adj_switch。
- **理由：** a2l 需要 layout-facing role，而语义真值是“这是一对反相器”。overlay 因此写 role=<a2l>、nll_role=logic。
- **排除：** 为了满足 a2l 把 semantic role 改成 switch，或让这些器件没有 a2l role。

## D010 — 弃权是一等公民；人工 review 决定

- **决策：** functional role 可以是 unknown 或 ambiguous。结构事实和电气类别仍尽量高覆盖。Coverage 不是 KPI；正确性和 review 质量才是。
- **理由：** 错 role 会传播到面积、版图匹配、sizing 和 review 工具。错的 mirror/pass 比显式 unknown 更糟。
- **形式：** hard abstention（role=unknown）+ soft confirmation（role=..., confidence<0.7, review=confirm），附竞争候选和 evidence。
- **排除：** 为了让 coverage 好看，给每个器件硬塞一个 role。

## D011 — 先保留 imperative recognizer，再迁移复合模式

- **决策：** 在 port-first schema 和 2–3 个 benchmark 就位前，不把 recognizer 重写成声明式 pattern engine。先给现有代码加 positive/negative evidence、candidates、score/margin、abstention；再把 mirror/pair/cascode/tail/switch/divider 迁到声明式 pattern 表，复杂情况保留 hook。
- **理由：** big-bang 重写会推迟验证，也分不清问题在规则还是 schema。声明式 pattern 是维护性投资，不是第一版语义层的前提。
- **排除：** 让 if/else 无限增长而没有迁移路径。

## D012 — 默认自研 parser；可选外部 adapter

- **决策：** 默认 parser 留在本项目。先补高价值能力：include、param、bus、black-box、diagnostics。保留可选 adapter 接口，接 analog-design-cli 或 spice-canonical；只有自研 parser 在真实 deck 上失败时才复用外部代码，且保留 license/attribution。
- **理由：** parser 是地基；硬依赖 alpha 外部 parser 会把语义绑到它的 bug 上。但重写所有 SPICE 方言也是无底洞。
- **排除：** 现在就全量重写 parser，或核心路径静默依赖外部 parser。

## D013 — 语义优先；名字是可选渲染

- **决策：** 契约是语义层（role、class、group、match、evidence、confidence），不是网表的新拼写。原始名字永远保留。规范名只是从已接受语义渲染出的可选建议；可以另外导出 renamed copy，但它不是主产物。
- **理由：** 名字不唯一（VBIAS_P vs VBP）、有歧义（ENN、VP、IBP）、可能误导，exact-name 评测很脆。破坏性重命名还会破坏 LVS、backannotation、testbench 和下游 net 引用。
- **排除：** naming-first 契约、原地重命名、用 exact string replacement 作为主要评价。

## D014 — v0.2 语义核心是 port-first，不是 device-only

- **决策：** v0.2 annotation core 包含：
  - port 一等对象：原始名、direction、class/interface、差分组、bus、confidence、evidence、conflicts；
  - device：role、match、group、structural tags、confidence、evidence、conflicts；
  - net：electrical class、structural role、差分/总线分组、confidence、evidence；
  - block：功能分组及端口；
  - review 状态和竞争候选。
  subckt 名延后；canonical name 可选；constraints（mirror ratio、same-L/finger、cascode compliance）phase 2。
- **理由：** port 是 CELL 的接口契约，也是内部推断最强的锚点。device-only 会丢失 ATD/DTA、enable、reference、差分语义。一次吞下所有字段会导致 schema churn 和不可验证的承诺。
- **排除：** device-only v0.2、给每个 net 硬塞功能名、把 constraints/skill/MCP 排在 semantic core 之前。

## D015 — 确定性 workflow 先做；MCP 是接口，不是编排

- **决策：** v0.2 提供确定性 CLI/workflow：
  parse -> port classify -> facts -> candidates -> decisions -> review -> export。
  MCP 延后。schema 冻结后写 SKILL.md；CLI 稳定后做薄 MCP wrapper（一个高层 annotate_cell + 只读 inspection tools）。多步组合、重试、fallback、人工 gate 留在代码/orchestrator，不放 MCP server。
- **理由：** MCP 定义“怎么调用工具”，不定义顺序、状态、重试、fallback 或审批。agent-only 编排难以复现和审计。薄 wrapper 保持核心确定性、接口可替换。
- **排除：** 把业务逻辑放进 MCP server，或把 agent 即兴编排 annotation workflow 作为主路径。
