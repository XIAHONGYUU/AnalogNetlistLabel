# 评测 — 如何判断标注是否正确

短答：**不能靠看一次输出来判断，也不存在对每个语义标签都绝对的“正确”。** 我们只能在一个明确的 rubric、一个留出的人工金标准、以及一套 review 协议下，测出“这个系统有多好”。本文定义这套协议，并说明当前仓库能证明什么、不能证明什么。

## 1. “正确”是什么意思

语义标签是人在某个 taxonomy 下的判断。两位工程师对边界情况（bias vs current_mirror、decap vs compensation、startup vs bias）有不同意见是正常的。因此：

- 用 **rubric** 定义 role/class，并给例子；
- 允许每个对象有 **可接受标签集合**，而不是永远只有一个字符串；
- 把 **clear 子集** 和 **ambiguous 子集** 分开；
- 同时报告 **strict** 和 **lenient** 指标；
- 高置信度但错误，比显式 unknown 更糟。

本项目里的“正确”是指：**在 rubric 下、在留出集上、与专家共识一致，并且证据可检查**；不是“和某一个参考文件完全相同”。

## 2. 四层验证

### L0 — 结构事实

parser 和图事实：器件端子、rail、port、diode、shared gate/source、W/L、bus 名称、层次边界。

验证方式：

- 合成网表的 unit test；
- 变形不变性：器件/net 改名、行序打乱、大小写、W/L 缩放、subckt 改名；
- parser 边界：XQ* MOSFET vs BJT、Spectre 端口列表、bus、续行、注释；
- 对照源文件抽查少量 net。

这一层可以接近 100% 正确，是后面所有层的前提。

### L1 — 局部结构识别

有没有找对 diode、mirror、pair、tail、cascode、inverter、mux、divider、pass device？

验证方式：

- pattern 级金标准：期望的器件集合/端子；
- 对 pattern 算 precision/recall，不只看“有没有 role”；
- 反例：没有 diode reference、source 不同、source degeneration、堆叠、假 pair。

### L2 — 语义：device role、net class/role、port、block

这是主要标注层，需要 **人工标签**。

建议金标准：

- 10–20 个 cell，100–300 个器件；
- 覆盖 5T、two-stage、LDO、bandgap/reference、comparator、startup、enable/trim、ATD/DTA 边界；
- 同时包含命名良好和通用名的网表；
- 两位标注者独立标，分歧由第三人裁决；
- 每个对象记录 clear/ambiguous；
- 留出 test split，按 topology 和命名质量分层。

指标：

| 层 | 指标 |
| --- | --- |
| port | direction / class / interface accuracy；差分/总线分组 |
| device | micro/macro precision、recall、F1；per-role confusion |
| match | device-set precision/recall；pairwise agreement |
| net | class accuracy；structural-role accuracy；差分分组 |
| block | pairwise co-membership / adjusted Rand index |
| naming（可选） | 人工接受率；同义词感知，不做 exact string |
| abstention | coverage、selective accuracy、review rate、false auto-accept |
| calibration | reliability diagram / ECE（按 confidence bin） |

报告 **strict**（单一期望标签）和 **lenient**（可接受集合）两套结果。不要把边界情况藏进一个 accuracy 数字里。

### L3 — 下游效用

overlay 真的有用吗？

- a2l validate 能接受 overlay；
- area/floorplan/white-line 用对 role/group；
- layout review 看到正确的 match group；
- AI agent 能回答“输入对在哪”“enable 是哪个 net”“反馈分压是什么”；
- 可以生成 renamed copy，但不改源文件。

效用不是正确性证明，但它能发现“技术上说得通、实际没用”的标签。

## 3. 选择性预测：怎么信任一个标签

系统不应只说 input_pair，还要说 **多少输出可以安全自动接受**。

按 confidence/score 排序，测：

- **coverage**：自动接受的比例；
- **selective accuracy**：自动接受子集的准确率；
- **review rate**：送人工的比例；
- **false auto-accept**：高置信度但错误（最危险的指标）；
- **risk–coverage curve / AURC**：coverage 上升时 accuracy 怎么变；
- **ECE**：confidence bin 是否匹配实际准确率。

当前实现已经输出 review（auto/confirm/unknown）、candidates 和 device margin。阈值是启发式的，尚未校准；必须在 gold set 上校准后，才能声称 confidence 有意义。

## 4. 当前仓库能证明什么

自动验证：

- 41 个 unittest 通过；
- 变形不变性：device/net rename、shuffle、case、W/L scale、subckt rename；
- OOD：RC filter、resistor divider、digital inverter 不会产生假 input_pair/mirror/tail/pass；
- hard abstention：无法识别的 MOS → unknown + review；
- JSON Schema v0.2 校验；
- CLI smoke test；CI（Python 3.11/3.12）；
- a2l validate 接受 LDO overlay（结构检查，不是语义真值）。

尚未证明：

- device/net/port 对人工标签的准确率；
- confidence 校准；
- 在 HF 130k 上的泛化；
- 层次展开和 parser diagnostics。

所以目前最诚实的说法是：

> 结构层已经测过；语义层有证据、可复核，但还没有在人工金标准上测过准确率。

## 5. 现在就能做的 10 分钟抽查

1. 打开 out/v02_ldo/annotation.md，或 review/ldo_quick/review.md。
2. 随机挑 5 个 device、5 个 net。
3. 对照 ldo.sp 检查证据：
   - 引用的 net/device 是否存在？
   - diode 是否真的 gate == drain？
   - shared source/gate 是否真实？
   - port anchor 是否合理？
4. 看 review queue：它是否包含你也会犹豫的器件？
5. 做一次改名推演：pbias 改成 pb0，label 还成立吗？（测试套件已经覆盖）

如果证据是错的，即使 role 看起来合理，也应视为错误。evidence correctness rate 应作为单独指标，按 role/class 抽样。

## 6. 什么情况会证伪系统

- 明确案例上，高置信度标签被专家否定；
- 改 net/device 名字后语义标签变化；
- OOD 电路出现 confident 的 input_pair/pass_device/cascode；
- review queue 空了但错误仍在；
- a2l 接受 overlay，但 area/layout intent 系统性错误；
- evidence 引用了不存在的节点。

这些测试比 headline coverage 更重要。

## 7. 建议的 release gates（目标，不是当前成绩）

在称为“可用 alpha”之前：

- clear 子集 device macro-F1 >= 0.85；
- 自动接受 device precision >= 0.95；
- gold set 上 review rate <= 20%；
- port direction/class accuracy >= 0.90；
- net class accuracy >= 0.85；
- 定义好的变换 invariance pass rate = 100%；
- OOD false-positive rate = 0；
- schema validation 和 CI 全绿；
- evidence 抽样正确率 >= 0.95。

这些数字要等 gold set 存在后才可信。不要把它们当已达成。

## 8. 当前的 review/evaluate 流程

复核包和 evaluator 已经可用：

    python3 -m netlistlabel review out/v02_ldo/annotation.json --out review/ldo_quick
    # 编辑 review/ldo_quick/review.csv（推荐）或 gold.json
    python3 -m netlistlabel evaluate out/v02_ldo/annotation.json review/ldo_quick/review.csv --out out/eval/ldo_quick

evaluator 输出 strict/lenient device accuracy、net class/role accuracy、port direction/class/interface accuracy、match/group accuracy、auto precision、decision 分布和 confusion。它是抽样 review 结果，不是全局准确率。

下一步：用两位标注者标 10–20 个 cell、100–300 个器件，再跑 HF 130k 分层抽样，测 coverage/review/robustness（不是 device-level truth）。

## 9. 结论

在 gold set 出现之前，正确姿势是：

> **结构事实已测试；语义标签是带证据和 review 的提案，不是已验证的真值。**
