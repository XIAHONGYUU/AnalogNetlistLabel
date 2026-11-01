# AGENTS.md — NetlistLabel

本文件是 NetlistLabel 仓库的长期协作契约。CURRENT_TASK.md 是当前行动源，先读它。

## Mission

把**没有语义标签的模拟网表**转换成可复核、可回归、可被下游消费的语义层：

1. 保留网表事实（连接、类型、W/L、参数、原始名字），不修改原始文件；
2. 以 port 为锚点：端口方向、类别、接口、差分/总线分组；
3. 识别可检查的结构（二极管连接、镜像、差分对、尾电流、cascode、开关、无源网络）；
4. 在这些结构之上提出 device role/match/group、net class/role、block；
5. 每个结论都带 positive/negative evidence、confidence、competing candidates；
6. 允许 unknown/ambiguous，把不确定性显式交给人工 review；
7. 输出稳定 schema，能被 Analog2Layout 等下游使用。

**语义是契约，名字是渲染。** 原始名字永远保留；规范名只是可选建议。

## 非目标

- 不做仿真、不产生波形、不替代 SPICE；
- 不做 DRC/LVS/PEX，不声称版图正确；
- 不自动修改用户原理图或原始网表；
- 不做破坏性重命名；不把新名字当作下游身份；
- 不发明 W/L、器件参数、foundry/company 规则、net 功能；
- 不做通用“模拟电路问答”；只做网表语义归一化；
- 不把 LLM 输出当作事实。确定性代码负责 facts/结构/流程，AI 负责在证据上提议语义；
- 不在 MCP server 里写业务逻辑；MCP 只是接口，不是 workflow。

## 不可协商的边界

- **源网表只读。** 所有写回都是独立文件；annotated.sp 和 renamed.sp 都是提案副本。
- **port 是一等对象。** 不是 net 的附属字段；方向、类别、接口、差分/总线必须显式。
- **名字是证据，不是事实。** 名字可以缺失、冲突、误导；结构/端口证据必须能仲裁。
- **不静默猜测。** 证据不足时输出 unknown/ambiguous 或低置信度 + review，不用覆盖率换取假确定。
- **证据必须可检查。** 每条 evidence 应能对应到器件/节点/端口/参数/source line；禁止“看起来像”。
- **role/命名规范变更属于人。** 规则可以提出候选，但新增/改名 role、命名规范必须由 owner 确认。
- **不引入专有数据。** 不提交公司 PDK、未公开网表、规则文件；真实 benchmark 用外部路径引用并记录许可证。
- **可回归。** 规则/schema 改动必须更新测试或 benchmark 期望，报告 coverage/review/accuracy 变化。
- **默认零依赖。** 核心只用 Python 标准库；外部 parser 只能作为可选 adapter。

## 架构规则

- spice.py 只做解析，不做语义判断；
- ports.py 只做端口分类/锚定，不修改器件 role；
- nets.py 只做 net 类别/结构角色/分组，不修改器件 role；
- 端口/网络/器件/块的事实与推断分层：facts -> candidates -> decisions；
- facts 层只产出可验证的连接/结构/端口事实，不产出最终 role；
- 推断层消费 facts，输出带 score/margin/evidence 的候选；
- 决策层在 port/block/supply/signal-chain 上下文中选最终 role/class/group；
- report.py / overlay.py 只做序列化，不偷偷改语义；
- model.py 是 ports/devices/nets/blocks 的数据契约；
- taxonomy.py 是 role / block label / a2l mapping 的唯一来源；port/net class 词表
  必须与 schemas/ 和 ports.py/nets.py 保持一致；
- JSON 是公共接口：改字段必须更新 schemas/、docs/ 和测试；
- 外部 parser adapter 只能把外部结构转换成内部 facts，不能绕过证据层。

## 证据与置信度

- confidence 是 0..1 的启发式接受度，不是概率真理；
- 强结构证据 + 端口锚定：0.85+；
- 结构成立但功能归属有歧义：0.60–0.85；
- 只作为候选：<0.60，必须进 review；
- 任何 unknown 必须出现在 review queue；
- 每个 device/net/port 至少一条 evidence；没有 evidence 的提案视为 bug；
- 硬弃权（role=unknown）与软确认（role=..., confidence<0.7, review=confirm）都是合法输出；
- 竞争候选必须给出 score/margin/negative evidence，不能只给一个标签。

## 解析器

- 默认自研 parser，优先补 include/param/bus/black-box/diagnostics；
- 前缀启发式必须让 model/terminal 证据仲裁（例如 XQ 不应无条件当 BJT）；
- 未展开的 subckt 标为 black_box，不猜内部 role；
- 可选 adapter 可接 analog-design-cli / spice-canonical；不能成为核心路径的硬依赖；
- 复用代码必须保留 license/attribution；GPL 代码只学思想，不复制。

## Workflow 与 MCP

- v0.2 是确定性 CLI/workflow：parse -> port classify -> facts -> candidates -> decisions -> review -> export；
- 多步组合（顺序/条件/层次/并行/人工 gate）由代码或 orchestrator 负责；
- MCP 只是工具接口，不是 workflow；
- schema 冻结后再写 SKILL.md；CLI 稳定后再做薄 MCP wrapper；
- 推荐 MCP 形态：一个高层 annotate_cell + 只读 inspection tools；不要把业务逻辑塞进 server。

## 验证

提交前运行：

    python3 -m unittest discover -s tests -v
    python3 -m netlistlabel analyze examples/generic_ota/generic_ota.sp --out out/generic_ota

真实 benchmark（路径存在时）：

    python3 -m netlistlabel analyze /path/to/ldo.sp --out out/ldo_raw
    python3 -m netlistlabel compare /path/to/ldo.sp /path/to/ldo.annotated.sp --out out/ldo_eval

v0.2 起还必须补：

- device/net rename、shuffle、case、W/L scale、subckt rename 的变形不变性测试；
- RC filter / resistor divider / digital netlist 等 OOD 测试；
- port 分类/锚定、net class、abstention、review queue 的测试；
- 至少一个真实开源网表的 regression fixture。

## 文档规则

- README 是门面；快速开始必须可运行。
- 中文是主要文档语言；代码标识符、JSON key、role id 保持英文。
- 设计变更写入 DECISIONS.md；当前状态写入 CURRENT_TASK.md。
- 不维护并行的 status/handoff 文件。
- 名字/语义/privacy 边界必须写清楚：原始数据保留，规范名可选，review 必须可见。

## 仓库卫生

- 只提交源码、schema、合成例子、测试、文档；
- out/、__pycache__/、虚拟环境、外部真实网表不提交；
- 未经明确指示不 push、不发布、不改 remote；
- 如果 Git identity 未配置，只 stage，不发明用户身份。