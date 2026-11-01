# Changelog

## v0.2.0 — 2026-11-01

**首个展示版：陌生模拟网表的语义标注 demo。** 不是生产签核版本。

### 顶层路线

- 真实输入是大型 .sp（top + 很多 subckt），不是单个 flat cell；
- 目标链路：top 接口 → subckt/cell 分解 → leaf annotation → 跨层聚合；
- v0.2 先完成 leaf-cell annotation；full-netlist / subckt selection / 后仿真 / 混合信号 / logic 是后续阶段。
- 顶层价值：开源模拟网表 ↔ AI 的语义接口；可延伸到 PERC-like 检查、整体版图检查、AI 驱动网表修改。

### 核心

- port-first annotation：ports / devices / nets / blocks / evidence / confidence / review；
- 语义层：device role、match/group、net class/structural role、功能块、差分/总线分组；
- 结构识别：diode、mirror、diff pair、tail、cascode、inverter、mux、pass device、source follower、common-source；
- 负证据、竞争候选、device top_score/margin、hard unknown / soft confirm；
- 中文 review.md + Excel 友好 review.csv + gold.json；
- evaluate：strict/lenient accuracy、confusion、auto precision、review rate，支持 CSV/JSON gold；
- 非破坏性 overlay：annotation.json / annotation.md / *.annotated.sp，源网表只读。

### 数据集与评测

- LDO：41/41 MOS 人工确认；合并 gold 覆盖 44 device + 6 net + 8 port = 58 项；
- generic OTA：26/26 全量人工确认；
- 41 个 unittest 通过；
- 变形不变性：device/net rename、shuffle、case、W/L scale、subckt rename；
- OOD：RC filter、resistor divider、digital inverter 不产生假 analog role；
- JSON Schema v0.2 校验；
- GitHub Actions CI（Python 3.11/3.12）。

### 已知限制

- LDO 仍有 27 个 net、XC3/XR6 未人工复核；
- 人工 gold 是 smoke/regression，不是独立双盲准确率；
- confidence 阈值尚未在 100–300 device gold set 上校准；
- parser 仍缺 include/param/black-box/diagnostics；
- 层次不展开，subckt 内部器件不可见；
- 规范名生成器只覆盖少量结构名；
- SKILL.md / MCP 按 D015 延后。

## v0.1.0

- v0.1 原型：SPICE 子集解析、role/match/group、面积/版图 handoff 的 annotation overlay；
- LDO 参考对比：75.6% exact role、87.8% a2l-role、97.8% partition pair、6/6 match group。