# Contributing

## 先读

- AGENTS.md：项目边界和不可协商规则；
- DECISIONS.md：已接受的设计决策；
- CURRENT_TASK.md：当前目标和下一步；
- docs/evaluation.md：怎么判断标注是否正确。

## 环境

    python3 --version        # 3.11+
    python3 -m unittest discover -s tests -v
    make demo
    make test

核心零第三方运行时依赖；jsonschema 只用于可选的 schema 测试。

## 修改规则

- 源网表只读；不要原地重命名或修改 W/L。
- 新增/修改 role、net class、block label：先更新 taxonomy/schema/docs，再更新测试。
- 每条 device/net/port 结论必须有 evidence；没有 evidence 的提案视为 bug。
- 不确定时输出 unknown/confirm，不要为了 coverage 硬猜。
- 规则改动必须跑测试和 gold smoke，并报告 coverage/review/accuracy 变化。
- 不提交公司 PDK、未公开网表、规则文件或个人信息路径。
- 不复制 GPL 代码；复用外部代码必须保留 license/attribution。

## 提交前

    python3 -m unittest discover -s tests -v
    python3 -m netlistlabel analyze examples/generic_ota/generic_ota.sp --out out/generic_ota
    make demo

真实 LDO benchmark 需要外部路径：

    python3 -m netlistlabel analyze /path/to/ldo.sp --out out/ldo_raw
    python3 -m netlistlabel evaluate out/ldo_raw/annotation.json benchmarks/gold/ldo_reviewed.gold.json

## 风格

- 中文文档为主；代码标识符、JSON key、role id 保持英文。
- 提交信息用 feat:、fix:、docs:、test:、refactor: 前缀。
- 小步提交；不要把生成物、虚拟环境、review/、out/ 提交进仓库。
