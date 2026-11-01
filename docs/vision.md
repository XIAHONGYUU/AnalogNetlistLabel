# 顶层设计 — 从大网表到可复核语义

## 1. 问题不是“一个小 cell”

真实交付给我们的，通常不是一张只有 10 个管子的 flat cell，而是：

    top.sp
      top
        X1  amp_core
        X2  bias_gen
        X3  ldo_loop
        ...
      .subckt amp_core ...
      .subckt bias_gen ...
      .subckt ldo_loop ...

一个大 SPICE 文件，里面有顶层、很多 subckt、层次实例、控制逻辑、无源网络，名字大多没有语义。人可以在 GUI 里靠层次、颜色、位置和记忆理解它；AI 只看到文本。

所以 NetlistLabel 的目标不是“给一个小网表打标签”，而是：

> **把大型、层次化的模拟网表，从上到下层层拆解，恢复成可复核的语义结构。**

## 2. 核心判断

1. **先分解，再标注。** 不把整张网表当成一团，也不只标一个 leaf cell。先看 top 的接口、电源、subckt 实例和控制关系，再逐层下钻。
2. **port 是每一层的锚点。** top 有 top 的端口；subckt/cell 有 cell 的端口。方向、类别、接口、差分/总线是跨层对齐的关键。
3. **leaf annotation 是第一步，不是终点。** 当前 v0.2 先把 leaf cell 的 device/net/block 语义做对；下一步才是 full-netlist annotation、subckt selection 和层次聚合。
4. **语义是独立 overlay，不是重命名。** 原始名字、层次和源文件保留；语义层可以写回，也可以被下游工具消费。
5. **证据优先，允许弃权。** 每个结论带 evidence/confidence；不确定的进 review，不用覆盖率换假确定。

## 3. 处理链（目标形态）

    large .sp
      |
      v
    [parse]       top / subckt defs / instances / ports / parameters
      |
      v
    [hierarchy]   top interface + subckt graph + instance bindings
      |
      v
    [decompose]   choose subckt/cell -> leaf annotation
      |
      v
    [annotate]    ports / devices / nets / blocks / evidence / review
      |
      v
    [aggregate]   cell semantics -> subckt semantics -> full-netlist graph
      |
      v
    semantic overlay + review queue + gold evaluation

当前 v0.2 实现的是：

    parse -> leaf-cell ports/devices/nets/blocks -> evidence/review -> overlay

还没有实现：

- 自动选择“哪些 subckt 值得先标”；
- 层次展开/折叠和跨层 port 对齐；
- full-netlist block graph；
- 后仿真/混合信号/逻辑感知。

## 4. 为什么值得做：四个下游方向

语义层不是终点，而是 **AI 进入开源模拟网表素材库的接口**。公开电路通常没有 GUI，只有大 .sp；AI 能理解网表之后，才有下面这些可能：

1. **开源素材库 ↔ AI**：给公开网表建立语义索引，做全库搜索、比较、问答、按结构检索，而不是只靠文件名和 topology label。
2. **PERC-like 检查**：浮空 gate、bias 缺失、drive 冲突、body/well 连接、GUI 低级错误，都可以变成结构化规则；AI 提供语义上下文，规则负责判定。PERC/DRC/LVS 的签核仍需要正式工具和 owner。
3. **整体版图检查**：有了 hierarchy、role、match group，才能检查分组、对称、bias 走线、镜像/匹配是否合理；这不是 DRC/LVS 的替代。
4. **AI 驱动网表修改**：如果 AI 能理解语义，就可以在上下文里做 repair、改网表、再验证，接近 “vibe analog” 的交互；当前仍是只读分析，修改是后续阶段。

这一层做对之后，价值不在“多了一个标注文件”，而在**把模拟设计里最稀缺的语义上下文，变成 AI 可以消费的结构**。

## 5. 新老网表对比

| | 老网表 | 新网表 / overlay |
| --- | --- | --- |
| 结构 | top + subckts + 一堆实例 | 同一层次，但每个节点带语义 |
| 器件 | XM46、XM59，未知 role | output_stage + source_follower + evidence |
| net | net1、net2、VERR | tail / mirror_gate / gain_node + block |
| 匹配 | 看不出来 | LOAD_AMP、DP_AMP、CAS_BIAS |
| 可信度 | 只能靠人猜 | confidence / candidates / review |
| 修改 | 直接改名会破坏下游 | 源文件只读，overlay 独立 |

新网表不是“换了一套名字”，而是**多了一层可检查的语义**。

## 6. 范围与阶段

| 阶段 | 范围 | 状态 |
| --- | --- | --- |
| v0.2 | leaf-cell annotation：ports/devices/nets/blocks + evidence/review | 已跑通；LDO 41/41 MOS、OTA 26/26 |
| next | full-netlist annotation：层次解析、subckt selection、跨层聚合 | 设计/待实现 |
| later | pre-sim -> post-sim -> mixed-signal；logic/digital-aware | 方向 |

“现在跑通的 demo”是这条路线的一个例子，不是项目的全部。

## 7. 为什么先做 leaf

- leaf cell 是语义最密集、最可验证的一层；
- 只有 leaf 的 role/net class/block 稳定，聚合到 subckt 才有意义；
- 先把 evidence/confidence/review 的协议跑通，再扩到层次，避免在大图上放大错误；
- 真实 LDO/OTA 已经能提供可复核的样本，适合做 gold/regression。

## 8. 不做什么

- 不把“大网表”简化成一个小 cell 来回避层次问题；
- 不把 LLM 当仿真器或版图签核工具；
- 不发明 W/L、PDK 规则、net 功能；
- 不重命名源网表；
- 不声称 full-netlist/hierarchy 已经完成。
