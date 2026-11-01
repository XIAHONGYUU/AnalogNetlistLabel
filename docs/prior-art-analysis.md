# 同类技能/工具深度分析与借鉴

日期：2026-10-31。方法：clone 仓库、读 README/设计文档/核心代码/测试，而不是只看 star。
星数和许可证是快照；结论按“对 NetlistLabel 有没有可复用的工程经验”排序。

## 0. 一句话结论

- **最值得学“认识论”的是 analog-topology-classifier**：事实与推断分层、正/负证据、规则支持度 vs 置信度、显式弃权、变形不变性测试。
- **最值得学“识别架构”的是 CircuitGenome**：声明式 pattern DAG、候选生成与决策分离、外部端口/信号链过滤、未知器件清单。
- **最值得学“解析与 skill 工程”的是 analog-design-cli 和 spice-canonical**：方言覆盖、层级/别名/域、provenance/diagnostics、SKILL.md 的边界写法。
- **最值得学“闭环交互”的是 diagen**：提案 → 渲染/报告 → 观察 → 修正；MCP 返回结构化报告 + 可看的预览。
- **最值得学“领域知识组织”的是 analog-agents**：checklist、anti-pattern、effort level、review report；但它的拓扑识别是 prompt-only，不能当确定性事实。
- **pyckt 是概念先行、实现为空**；不能作为可用依赖。**HF 130k 数据集**是最好的规模化 benchmark 语料，但没有逐器件 role 标签。

## 1. 评估维度

我用这 8 个维度看每个项目：

1. 输入覆盖：SPICE/Spectre/HSPICE/CDL、层级、include、参数、总线；
2. 结构识别：二极管、镜像、差分对、cascode、尾电流、开关、无源；
3. 语义粒度：整网表一个标签，还是逐器件 role/match/block；
4. 证据与置信度：有没有正/负证据、margin、abstention、review；
5. 层次与边界：子电路展开、黑盒、端口方向、源文件 provenance；
6. 输出与集成：JSON schema、CLI、MCP、下游可消费性；
7. 可测试性：单测、回归 fixture、变形不变性、OOD；
8. agent 可用性：SKILL.md、触发词、工作流、输出解释边界、许可证。

## 2. analog-topology-classifier（ATC）

### 它是什么

parser → terminal-aware bipartite graph（NetworkX）→ 两层特征 → 4 个独立 topology scorer → 排序 + 弃权。
支持 4 种拓扑：basic current mirror、cascode current mirror、differential pair、common-source amplifier。

### 强项

- **两层特征，避免循环论证**：Tier 1 是原始结构事实（diode、shared gate/source、stack、matched W/L、tail、passive），Tier 2 才是候选结构（mirror candidate、diff pair candidate）。这比“先猜 role 再用 role 找证据”干净得多。
- **正证据 + 负证据 + 惩罚**：每个 scorer 同时输出 positive_evidence、negative_evidence、positive_score、penalty。比如 basic mirror 会因为检测到 cascode stack 被扣 0.5 分。这比只给一个 role 可信得多。
- **rule_support 与 confidence 分离**：rule_support 是规则满足度，confidence 是 HIGH/MEDIUM/LOW/AMBIGUOUS/UNKNOWN 的定性判断。
- **显式弃权优先于歧义**：top score < 0.50 → UNKNOWN；margin < 0.10 → AMBIGUOUS；然后才是 HIGH/MEDIUM/LOW。这个优先级值得直接采用。
- **端口/网络角色推断**：reference、power、bias、signal_input、signal_output、tail、load、internal；优先用 body/source/port/DC source 证据，名字只是弱提示。
- **变形不变性测试**：节点改名、器件改名、行序打乱、W/L 整体缩放、大小写变化，预测必须不变；OOD 的 RC filter / resistor divider 必须返回 UNKNOWN。这个测试思想比它支持的 4 个拓扑更有价值。
- **终端感知图**：D/G/S/B 各自保留边，diode-connected 不会因为 gate/drain 同网而丢边。

### 弱项

- 只做**整网表单标签分类**，不支持一个 LDO 里多个功能块、逐器件 role/match/group。
- 只有 4 个拓扑、4 个示例网表；规则权重是手调的，不是校准过的概率。
- 依赖 NetworkX + matplotlib + pyvis；与我们的零依赖约束冲突。
- 没有层级展开、没有 annotation overlay、没有 review queue。
- 负证据是 topology 级别，不是 per-device 级别；无法告诉用户“这个管子为什么不是 mirror”。

### 可借鉴

1. Tier 1 事实 / Tier 2 候选 / 最终决策 三层分离。
2. 正证据、负证据、惩罚项、margin 一起输出。
3. rule_support 与 confidence 分开；UNKNOWN 优先于 AMBIGUOUS。
4. 端口/网络角色推断用 body/source/port 证据，名字弱化。
5. 变形不变性测试 + OOD 弃权测试，直接纳入我们的测试套件。
6. 终端感知图而不是简单 net→device 列表。

### 不要照搬

- 不要用“整网表一个标签”去描述 LDO。
- 不要为了它现有的 4 个拓扑而收窄我们的 scope。
- 不要把 NetworkX 引入核心；我们可以在测试/可视化层可选使用。

## 3. CircuitGenome

### 它是什么

3 层识别：

- Layer 0：flat SPICE 解析为 ParsedNetlist；
- Layer 1：Subcircuit Recognizer，用声明式 pattern 库匹配原语/复合结构，输出**所有重叠候选**；
- Layer 2：Functional Block Recognizer，用 topology template 做 slot assignment，或在无 topology 时按 category/block 分组，并用外部端口、信号链过滤假候选。

pattern 库规模：6 个 primitive + 7 个 structural + 49 个 op-amp pattern；YAML 声明 devices、same_net、pins、children、exclusive、priority、hook。

### 强项

- **声明式 pattern DAG**：新增一个结构变体往往只改 YAML，不写代码。primitives 是 exclusive（每个器件只归一个原语，按 priority），composites 按层级匹配，允许 DAG 共享子结构。
- **候选与决策分离**：Layer 1 故意保留所有重叠候选，Layer 2 才根据 topology context 选择。这避免“第一个匹配就当真”。
- **外部端口/信号链过滤**：真实差分对的 in1/in2 通常接外部端口；偏置镜像不会。用 external_port_score、signal-chain following、source 轨过滤来压掉假阳性。
- **topology-free 分组**：没有 topology template 时，按 circuit_block/category 分组，并做三遍过滤/拆分；这对陌生网表比“必须给一个已知 topology”更现实。
- **hooks 处理不规则结构**：constructed bias legs、cascode_vdd leg、resistor load rail check 等用 hook 扩展模板，而不是把异常写死进主匹配器。
- **未知器件清单**：unrecognized_devices 是显式输出，不静默丢弃。
- **真实模型名/尺寸方言**：支持 SKY130 模型名、x 前缀 MOSFET、W/L/nf/m 参数；识别只看拓扑，尺寸只作为证据。

### 弱项

- **op-amp 中心**：slot/category 是 input_pair/load/tail/bias/compensation/output/cmfb，不能直接覆盖 LDO 的 pass device、feedback divider、startup、reference select、enable/trim。
- pattern 匹配是组合搜索；代码注释提到 8–9 器件 CMFB pattern 可能很慢，需要 partial same_net 剪枝。
- 完整 FBR 依赖 topology template；topology-free 模式仍是启发式排序。
- 没有 provenance/line evidence、没有 annotation overlay、没有 review queue。
- 没有层级展开；对 x1/x2 这类子电路仍是黑盒。
- README 没有给出公开的识别准确率；需要自己 benchmark，它的价值更多是架构和 pattern 设计。

### 可借鉴

1. 声明式 pattern 库（YAML/JSON），包含 devices、same_net、pins、children、exclusive、priority、hook。
2. 候选生成 → 上下文决策两阶段，不要单遍贪心。
3. 外部端口、轨、信号链过滤，压掉“看起来像”的假阳性。
4. unrecognized devices 显式输出。
5. hooks 处理偏置腿、退化镜像、rail 校验等不规则结构。
6. 识别在拓扑上做，尺寸只作为证据，不把 W/L 当唯一依据。

### 不要照搬

- 不要把 op-amp slot 体系当成通用 taxonomy。
- 不要在没有剪枝的情况下做组合爆炸。
- 不要把 pattern match 直接当最终事实；它仍然需要 confidence/review。

## 4. analog-design-cli

### 它是什么

3.6k 行 parser + click CLI + graph/formatter + alias/domain；44 个测试文件、338 个 test 函数、约 7.5k 行核心代码。
支持 SPICE/Spectre/HSPICE/PEX、层级、bus、alias、电源/地/衬底/参考电压域、参数表达式 AST 安全求值、focus/trace、JSON/YAML/device/net 视图。
自带 skills/SKILL.md，明确边界：只给 connectivity evidence，不证明 current flow、timing、logic truth、stability、operating point。

### 强项

- **方言与边界覆盖极深**：Spectre 括号端口、HSPICE、PEX、subckt 路径、bus、参数默认值、include、alias、电源域。338 个测试说明它不是玩具。
- **skill 写得像操作手册**：安装、命令、输入输出、路径语义、排除 net、输出解释边界、常见坑。对 agent 非常友好。
- **“不证明语义”的边界**：它反复声明 outputs are connectivity evidence；这避免 agent 把结构查询当电路结论。
- **域分类**：AVDD/DVDD/AVDDH/AVDDL/IO/SUB/REF/CLK/BUS，避免把不同电源域误合并。这个对匹配/隔离/电平转换很有价值。
- **别名与作用域**：subckt-local alias、selected topcell 的 local connection truth，避免全局同名误合并。
- **零重依赖**：核心 parser 只用标准库；click 只在 CLI。

### 弱项

- **没有语义推断**：classify.py 的 circuit type 分类依赖外部 semantic_nodes.yaml，而且 CLI 里已 deprecated；不提供 role/block/match。
- 输出是结构视图（device/net/json），不是 annotation proposal。
- alpha 状态；alias/domain 规则复杂，仍有边界 bug 的可能。
- skill 只覆盖“怎么查连接”，不覆盖“这个管子是什么”。

### 可借鉴

1. 不要重写 parser；优先复用/移植它的方言、层级、alias、域分类能力（MIT，保留归属）。
2. SKILL.md 的写法：触发条件、命令、输出 schema、解释边界、常见坑。
3. 测试组织：fixture + regression + 真实网表；338 个 test 是质量护城河。
4. 域分类：电源/地/衬底/参考/时钟/总线，不只做“是不是轨”。
5. “连接证据 ≠ 电气结论”的边界语言。

### 不要照搬

- 不要把“解析成功”当成“理解电路”。
- 不要为了覆盖所有方言而把核心做成 3.6k 行；可以分层/可选依赖。

## 5. spice-canonical

### 它是什么

确定性的 canonical connectivity 提取：SPICE/Eldo/ngspice → Circuit/Device/Net 表；递归 include、黑盒、bus、诊断、evidence source lines；自带 agent skill。

### 强项

- **“不发明”原则**：未解析的器件保留 unresolved + raw text + diagnostic；未定义子电路保留 positional pins 和 BlackBox 标记；不猜 terminal 名。
- **diagnostics 是一等公民**：缺 include、未解析结构、重复命名等都有 source/line/message；strict 模式把不完整提取变成失败。
- **provenance**：extract_with_evidence 记录 device/definition 的源文件行、include 结果、根作用域 PARAM/MODEL。
- **canonical 表**：DEVICE_TABLE / NET_INCIDENT_TABLE 互为倒数，读写校验；consumer 不需要重开源文件。
- **include/黑盒边界**：stop_include、external_subcircuits、BLACK_BOX_TABLE，明确“这里没有内部信息”。
- **skill 边界清晰**：只教操作 extractor，不改变实现；明确 canonical 是结构视图，不是仿真输入。

### 弱项

- 只做连接提取，不做 role/block；没有语义。
- 只支持 Eldo/ngspice（不是 Spectre/HSPICE），与很多开源 IP 不完全匹配。
- 自定义表格式，不是 SPICE；下游需要适配。
- 早期项目（0★），但工程思路很成熟。

### 可借鉴

1. 每个 annotation 带 source line + provenance；不完整的层次要显式标注。
2. diagnostics / strict 模式：解析不完整时不让下游误以为完整。
3. 黑盒边界：x1/x2 未展开就标 black_box，不猜内部 role。
4. “不发明 terminal 名/不发明连接”的原则。
5. 读写可校验的 canonical 中间表示，便于回归和 diff。

### 不要照搬

- 不要为了 canonical 表而放弃 JSON schema；我们的 annotation 需要 role/evidence。
- 不要只支持两种方言；至少保留扩展点。

## 6. pyckt

- 结构：src/recognition、src/partitioning、src/topogen；受 ACST/FUBOCO 启发。
- 现实：StructureRecognizer.recognize() 和 Partitioner.partition() 都是 pass；测试断言 assertIsNone。它是概念骨架，不是可用工具。
- 价值：ACST 的功能块组合/分解思想、op-amp 层级生成；可以引用其论文/概念，不要依赖代码。
- 许可：未检测到 license；不要复制。
- 教训：一个项目有漂亮 README 和学术背景，不等于实现可用；评估必须看代码和测试。

## 7. diagen

### 它是什么

netlist → 自动原理图布局（TikZ/SVG）：parse → grouping/symmetry/stacks → Sugiyama 分层 → A* 布线 → report/preview；MCP server + Claude Code skill。

### 强项

- **闭环 agent 交互**：写 netlist → render → 读 report/预览 → 改 netlist，而不是改坐标。MCP 返回 report + TikZ/SVG + PNG preview，模型能自我检查。
- **对称/堆叠分组**：识别 stack、differential pair、current mirror、complementary pair、tail on axis、cross-coupled pair；这些启发式对 match group 和 block 很有参考价值。
- **报告可操作**：OK/INCOMPLETE、wire length、bends、crossings、junctions、dangling nets、warnings；exit code 反映是否全部布通。
- **零依赖**：标准库；MCP 用 stdio JSON-RPC，自包含。
- **skill 明确工作流**：不要手写 TikZ 坐标；检查 report；看预览；改 netlist。

### 弱项

- 面向“画得清楚”，不是“电气语义正确”；分组是视觉/结构启发式，不是匹配证明。
- 主要覆盖小电路/教学电路，不是 PDK 级模拟 IP。
- GPL-3.0：代码不能直接搬进 Apache-2.0 项目，只能学思想/独立实现。
- 没有 role/confidence/review/annotation schema。

### 可借鉴

1. 提案 → 渲染/报告 → 观察 → 修正 的闭环；我们未来可以输出 annotated SVG/HTML 预览。
2. MCP 工具返回“结构化报告 + 可看预览”，让 agent 自检。
3. 对称/堆叠分组的具体启发式，用于 match group 的候选生成。
4. 报告要有 OK/REVIEW/INCOMPLETE 状态，不只是表格。
5. skill 的“改输入，不改坐标”对应我们的“改证据/annotation，不改源网表”。

### 不要照搬

- 不要把视觉分组当电气匹配。
- 不要复制 GPL 代码。

## 8. analog-agents（含 analog-audit / librarian / netlist-crawl）

### 它是什么

12+ skills、4 个角色（librarian/architect/designer/verifier）、checklists、wiki/anti-patterns、cross-model review、effort levels。
analog-audit 做静态网表审计：topology identification → checklist → hand-calc → anti-pattern scan → cross-model review → report。
analog-netlist-crawl 做大寄生网表的图/Laplacian 分析。

### 强项

- **skill 工程**：frontmatter 的 trigger、明确 workflow、结构化 report、edge cases、effort 分级、standalone 使用说明。
- **领域知识资产**：checklists（LDO/current-mirror/differential/folded-cascode/bandgap）、anti-patterns（diode-load CMFB trap）、wiki 知识图谱。这些比代码更难复制。
- **review 流程**：cross-model review、divergence、risk summary；适合人工复核。
- **角色分离**：librarian 先 survey，architect 分解，designer 设计，verifier 审计；避免一个 agent 既写又审。
- **post-layout 处理**：先统计/裁剪寄生，再审计；对大规模网表有现实意义。

### 弱项

- **analog-audit 的 topology identification 是 prompt-only**：没有确定性 parser/recognizer，结果不可复现，不能作为事实层。
- 强依赖 Virtuoso/Spectre/EDA 环境；不是通用开源网表工具。
- 没有 per-device annotation schema；report 是 Markdown，不是机器可消费的 role/block。
- 没有 license 检测到；不能直接复制文本/代码。
- 许多 checklist 的 auto_checkable 为 false，需要人/LLM 判断。

### 可借鉴

1. skill 的写法：trigger、workflow、report 模板、effort level、standalone、边界。
2. checklist / anti-pattern 作为 review 层的知识资产，而不是事实层。
3. 结构化 report：Circuit Summary、Checklist Results、Risk Summary、Recommendations。
4. 角色分离：未来可以做 “annotator / reviewer / arbitrator” 三个 agent 角色。
5. 大规模网表先裁剪再分析。

### 不要照搬

- 不要把 prompt-only topology ID 当确定性结果。
- 不要把完整 EDA 流程塞进 annotation 核心。

## 9. awesome-ams-skills

- 定位：AMS agent skill 目录/索引，35★；没有直接做“陌生网表语义标注”的 skill。
- 价值：skill 发现、分类、安装方式；可以看到 AMS 生态里 parser/simulation/sizing/Verilog-A/ADC 都有 skill，annotation 是空档。
- 教训：skill 需要清晰的 frontmatter、安装路径、触发词、依赖检查；否则“看起来可用”但实际缺工具。
- 不要：把目录当实现，或直接复制无 license 的 skill 文本。

## 10. HF 130k SKY130 数据集

- 130,409 条 ngspice 仿真网表，49 topology families，topology-aware split，Apache-2.0。
- 强项：规模、开源工具链、可复现仿真、netlist_json + metrics、适合 GNN/benchmark。
- 弱项：标签是 topology/performance 级，不是逐器件 role/match/group；生成/仿真分布与真实 IP 有差距；PDK 绑定。
- 借鉴：分层抽样做 benchmark；按 topology family 划分避免泄漏；用 metrics 做辅助验证；需要人工标注小子集做 device-level ground truth。

## 11. 横向对比

| 维度 | 最佳参考 | 关键经验 |
| --- | --- | --- |
| 解析/方言/层级 | analog-design-cli, spice-canonical | 不要重写 parser；要 provenance/diagnostics/黑盒 |
| 结构事实 | ATC | 两层特征；终端感知；正/负证据 |
| 功能块/role 识别 | CircuitGenome | 声明式 pattern DAG；候选与决策分离；外部端口过滤 |
| 弃权/置信度 | ATC | rule_support vs confidence；UNKNOWN 优先；margin |
| 匹配/对称 | diagen, CircuitGenome | stack/symmetry 启发式；W/L/ratio 证据 |
| skill UX | diagen, analog-design-cli | trigger/workflow/report/preview/边界 |
| 领域知识 | analog-agents | checklist/anti-pattern/review report |
| 规模化评估 | HF 130k | topology-aware split；abstention/review rate |
| 许可证 | MIT/Apache 可借鉴；GPL 只学思想 | 保留 NOTICE/归属 |

## 12. 对 NetlistLabel 的具体改造建议

### 12.1 三层输出，不要混在一起

建议把 annotation 内部拆成：

1. facts：器件、终端、轨、端口、diode、stack、shared gate/source、W/L；
2. candidates：所有可能的结构匹配（mirror、pair、cascode、tail、switch、divider），每个带 positive/negative evidence、score、margin；
3. decisions：最终 role/group/match、confidence、review 状态。

当前 schema 只有 decisions + alternatives；建议增加 candidates 区（或 alternatives 带 score/margin/negative_evidence），让 review 能看到“为什么不是另一个”。

### 12.2 采用“正证据 + 负证据 + margin”

每个 role 不要只写一条 evidence。建议：

- positive：支持该 role 的结构事实；
- negative：反对该 role 的事实（例如“没有 diode reference”“不是同一 source”“宽度不匹配”）；
- score：规则支持度；
- margin：与第二候选的差距；
- confidence：由 score + margin + block context 决定的定性等级（HIGH/MEDIUM/LOW/AMBIGUOUS/UNKNOWN）。

这比当前手写 confidence 更可解释，也更容易校准。

### 12.3 弃权优先，接受覆盖率下降

当前 LDO 做到 100% role coverage，但其中有些是“结构性可解释、功能性有歧义”。
建议把 UNKNOWN/AMBIGUOUS 作为一等输出：

- 证据不足 → unknown；
- 两个候选 margin 太小 → ambiguous + review；
- 层次未展开 → black_box，不猜内部；
- 这样 coverage 会下降，但 review queue 更可信。

### 12.4 声明式 pattern 库

把当前硬编码 recognizer 逐步迁移到 YAML/JSON：

    name, priority, exclusive, devices, same_net, pins, children, category, block, hook

先覆盖：diode、mirror、cascode、diff pair、tail、inverter、mux、pass、divider。
复杂情况用 hook（退化镜像、bias legs、rail check）。
好处：规则可审计、可 diff、可扩展；坏处：组合搜索/性能，需要剪枝。

### 12.5 解析层：复用而不是重写

我们的 parser 只有 500 行，覆盖有限。真实开源网表的最大失败模式可能不是“规则不准”，而是“方言没解析”。
建议：

- 短期：支持 .include/.param/bus/更多模型名；记录 diagnostics；
- 中期：评估直接复用 analog-design-cli parser（MIT）或 spice-canonical（Apache）作为可选前端；
- 层次：未展开的 subckt 标 black_box，保留端口方向/位置，不猜内部；
- 每条 evidence 带 source line，便于人工核对。
- 实测提醒：把 MOS 实例改名为 XQ7 后，parser 会因 X+Q 前缀判成 BJT；前缀启发式必须让 model/terminal 证据仲裁，不能只看首字母。

### 12.6 网络角色/端口推断

当前只区分 rails 和 control。建议增加：

- reference/power/bias/signal_input/signal_output/tail/load/internal/unknown；
- 电源域（AVDD/DVDD/AVDDH/AVDDL/IO/SUB）；
- 端口方向/外部端口评分；
- 用 body/source/port/DC source 证据，名字只是 hint。

这会直接减少“把 bias 当 signal”“把 mirror 当 input pair”的错误。

### 12.7 测试：变形不变性 + OOD

直接借鉴 ATC：

- 节点改名、器件改名、行序打乱、大小写混合、W/L 整体缩放、D/S 交换；
- 注释增删、subckt 改名、net alias；
- OOD：RC filter、resistor divider、digital netlist、空网表、 unsupported device；
- 期望：结构 role/block 不变；OOD 不产生假 amplifier。

当前测试只有 15 个，缺少这些；这是最值得补的工程资产。

我在 generic OTA 上做了一个快速探针（同一网表，只改变命名/顺序/尺寸）：

- device rename：0 差异；
- line shuffle：0 差异；
- W/L 整体缩放：0 差异；
- 大小写变化：0 差异；
- 仅重命名 net：1 个 block 差异——XM8 从 BIAS 变成 AMP，因为 pbias 改成 pb0 后不再命中 BIAS_PORT_RE。

这说明当前 block 归属仍然依赖电源/偏置端口的名字提示。要真正做到“名字只是 hint”，需要把 bias/start/ref 的块划分改成结构驱动（body/source/port/信号链），而不是 net 名匹配。

### 12.8 skill / MCP 包装

建议未来加 SKILL.md + MCP：

- SKILL.md：trigger（“annotate netlist / 网表标注 / 这个网表是什么”）、workflow、CLI 命令、输出解释、review 边界、禁止事项。
- MCP tool：annotate_netlist(netlist, options) → annotation.json + annotation.md + 可选 annotated.sp / SVG 预览。
- 参考 diagen：返回结构化报告 + 可看预览；参考 analog-design-cli：明确“连接证据 ≠ 语义事实”。
- 报告状态：OK / REVIEW / INCOMPLETE，而不是只给覆盖率。

### 12.9 评估

- 小规模：ATC 4 拓扑 + 手写金标准；CircuitGenome op-amp 子集；
- 中规模：Hugging Face 130k 分层抽样，测 review/abstention/覆盖率；
- 大规模：人工标注 100–300 个器件做 precision/recall；
- 指标：device role precision/recall、match group precision/recall、block partition agreement、review rate、invariance pass rate、OOD false-positive rate。

## 13. 不要照搬的清单

1. 不要做“整网表一个标签”（ATC 的限制）。
2. 不要做 op-amp-only slot 体系（CircuitGenome 的限制）。
3. 不要做 prompt-only topology ID（analog-audit 的弱点）。
4. 不要把 parser 当语义层（analog-design-cli 的边界）。
5. 不要依赖 pyckt 的 stub 实现。
6. 不要把 diagen 的视觉分组当电气匹配，也不要复制 GPL 代码。
7. 不要为了覆盖率静默猜测；UNKNOWN 是功能，不是失败。
8. 不要在没有 benchmark 的情况下宣称“通用”。

## 14. 建议的讨论顺序

1. 先决定：是否接受“弃权优先”，允许 role coverage 从 100% 降到 80–90%？
2. 再决定：是否把 recognizer 迁到声明式 pattern 库，还是先保持 imperative、只加 evidence/margin？
3. 再决定：parser 是自研扩展，还是复用 analog-design-cli/spice-canonical？
4. 最后讨论：标注粒度（device / pair / block / net role / constraint）和 skill/MCP 形态。

这些决定会直接改变下一版 annotation schema 和实现顺序。