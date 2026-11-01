# CURRENT_TASK

## 目标

把 **NetlistLabel** 做成面向大型、层次化模拟网表的语义归一化层。最终目标是：一个大 .sp（top + 很多 subckt）先从 top 层层拆解到 leaf cell，再聚合回 full-netlist 语义图。当前 v0.2 先完成 leaf-cell annotation；输入 cell 网表和端口，输出非破坏性、可复核的语义 overlay：

- **port** 是一等对象：方向、类别/接口、差分/总线分组；
- **device**：role、match/group、结构标签；
- **net**：电气类别、结构角色、差分/总线分组；
- **block**：功能块及其端口；
- evidence、confidence、竞争候选、冲突、review queue。

原始名字永远保留；规范名只是可选建议。源网表只读。

## 当前状态（2026-11-01）

- 仓库已发布：https://github.com/XIAHONGYUU/AnalogNetlistLabel（public），tag v0.2.0，release https://github.com/XIAHONGYUU/AnalogNetlistLabel/releases/tag/v0.2.0。
- baseline 已提交；Git identity 使用 Zuokaiyuann <zuokaiyuann@foxmail.com>。
- GitHub Actions CI 在 main 和 v0.2.0 上通过（Python 3.11/3.12）；仓库已转 public。
- v0.2 semantic core 已在 v0.1 原型上实现：
  - SPICE 子集解析：MOS / R / C / D / BJT / subckt、.subckt、.PININFO、.global、续行、注释；
  - facts：rail、diode、mirror clusters、pairs、tails、cascodes、inverters、muxes、pass/output candidates、control propagation；
  - port 一等对象：direction、class、interface、quantity、polarity、差分/总线、anchors、candidates、conflicts、review；
  - net 一等对象：class、structural role、差分/总线、block、candidates、conflicts、anchors、review；
  - device：role/match/group + evidence/confidence/alternatives/candidates/top_score/margin；
  - blocks：AMP、OUT、BIAS、REF、START、CTRL_EN、CTRL_SEL、FB、PASSIVE、UNKNOWN；
  - 输出 annotation.json / annotation.md / *.annotated.sp，schema v0.2；
  - typed review queue（device/port/net）；
  - review 命令：中文 Markdown + 可编辑 review.csv + gold.json；
  - evaluate 命令：strict/lenient accuracy、confusion、auto precision、review rate，支持 CSV/JSON gold；
  - compare 命令：对照参考标注。
- 41 个 unittest 通过，包括 device abstention、metamorphic invariance/OOD、review/evaluate/CSV、LDO/OTA gold smoke。
- 首轮人工复核发现：XM59 是 PMOS source follower，net2 是 cascode 输出 + common-source 输入（interstage signal）；已补 source_follower/common_source 结构和测试。
- 首轮人工复核 ldo_quick 24/24 已确认（device 10/10、net 6/6、port 8/8）；已沉淀为 benchmarks/gold/ldo_quick.gold.json，这是 smoke gold，不是全局准确率。
- generic_ota 26/26 已确认（device 9/9、net 10/10、port 7/7）；已沉淀为 benchmarks/gold/generic_ota.gold.json，用于换拓扑回归。
- v0.2 范围仍是 leaf-cell annotation；full-netlist、subckt selection、跨层聚合、post-sim/mixed-signal/logic 是后续阶段。
- LDO 41/41 MOS 已确认；合并 gold benchmarks/gold/ldo_reviewed.gold.json 覆盖 44 device + 6 net + 8 port = 58 项。仍未复核的是 LDO 剩余 27 个 net 和 XC3/XR6 两个无源器件。
- benchmark：generic OTA 与 SKY130 LDO raw；LDO 对既有参考：
  75.6% exact role、87.8% a2l-role、97.8% partition pair、6/6 reference match group。
- prior-art 分析在 docs/prior-art-analysis.md。
- 决策 D001–D015 已接受；v0.2 关键决策：
  - D010：弃权优先，coverage 不是 KPI；
  - D011：先保留 imperative recognizer，加 evidence/candidates，再迁移声明式 pattern；
  - D012：默认自研 parser，可选外部 adapter；
  - D013：语义优先，名字是可选渲染，保留源数据；
  - D014：v0.2 语义核心 port-first，不是 device-only；subckt 名延后；
  - D015：确定性 workflow/CLI 先做，MCP 延后，skill 在 schema 冻结后写。

## demo 余项

- device hard unknown/soft confirm 和 margin 已输出，但阈值还没在人工 gold set 上校准；
- block 边界仍是启发式；port-first 已消除 XM8 pbias 改名回归，但真实 IP 的块边界仍需金标准检验；
- 变形/OOD 测试已加入，但样本还小，需要更多真实 IP 变体；
- parser 已支持 bus 名称、XQ* MOSFET/BJT 消歧；include/param/黑盒/diagnostics 仍缺；
- evidence 还没有 source line provenance；未展开 subckt 还没有显式 black-box 边界；
- 规范名仍保守，大多数内部 net 不生成建议；
- 已有 LDO/OTA smoke gold，但还没有 100–300 device 的正式 gold set，所以 calibration 和泛化 accuracy 仍未测；
- SKILL.md 和 MCP 按 D015 延后。

## 下一步原子动作

1. [done] 冻结/实现 v0.2 semantic core schema：ports、devices、nets、blocks、candidates、evidence、confidence、review、conflicts。
2. [done] port/net 分类与 first-class 输出。
3. [done] port-first block anchoring；device hard unknown/soft confirm/margin 已输出。
4. [done] metamorphic/OOD 测试：device/net rename、shuffle、case、W/L scale、subckt rename、RC/divider/digital；XM8 pbias regression。
5. 扩展 parser：include/param/black-box/diagnostics；加可选 adapter（analog-design-cli / spice-canonical），不作为核心依赖。
6. [done] v0.2.0 demo 文件：CHANGELOG、CITATION、DISCLAIMER、CONTRIBUTING、Makefile、scripts/demo.sh、gold；LDO 41/41 MOS + generic_ota 26 项已确认。
7. [done] 建 GitHub 仓库 XIAHONGYUU/AnalogNetlistLabel（已转 public）、push main + tag v0.2.0，并创建 v0.2.0 release；GitHub profile README 已加入展示图。
8. [pending] 补 LDO 剩余 net/passive 或 100–300 device 的人工 gold set；再跑 HF 130k 分层抽样和 analog-topology-classifier / CircuitGenome 对照。
9. [done] CI 和开源卫生：无个人路径、无外部网表、demo 状态。
10. schema 冻结后写 SKILL.md；CLI 稳定后做薄 MCP wrapper（一个高层 annotate_cell + 只读 inspection tools）。

## 约束

- 不修改源网表；不依赖重命名后的名字做下游身份。
- 不发明 W/L、规则、电容/电阻值、net 功能或电路意图。
- 名字是证据，不是真值；port 名是强证据，但仍可复核。
- 功能 role 可以是 unknown/ambiguous；结构事实仍要有用。
- 每个 role/net class 都要有 evidence；冲突和低置信度进 review。
- v0.2 中 port 是一等对象；subckt 名延后。
- 默认零第三方运行时依赖；可选 parser adapter 不能成为核心路径硬依赖。
- 未经明确指示不 push。

## v0.2 完成条件

- annotation.json 包含 first-class ports/devices/nets/blocks，原始名保留，规范名可选。
- port direction/class/interface、差分/总线、anchors、evidence/confidence 输出；缺失信息显式。
- device 有 role/match/group/structure/confidence/evidence；net 有 class/structural role/group/evidence。
- unknown/ambiguous 是合法输出；review queue 包含竞争候选和原因。
- v0.1 benchmark 仍通过，invariance/OOD 测试通过（含 XM8 pbias regression）。
- parser 输出 diagnostics，未展开 subckt 标 black box。
- README、design、schema、benchmarks、evaluation、CURRENT_TASK 反映真实状态。

## 待定问题

- .PININFO 缺失时，port direction 能推多少，哪些应该保持 unknown？
- 最小可用的 net-class taxonomy 是什么，才不会变成一套命名标准？
- 可选 canonical-name renderer 的 naming profile/grammar 怎么定？
- 130k 数据集里先人工标哪 100–300 个器件？
- constraints（mirror ratio、same-L/finger、cascode compliance）放 v0.3，还是能从 role/match 下游推导？