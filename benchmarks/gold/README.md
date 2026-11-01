# Gold sets

这里存放人工确认过的 gold packet。它们只包含语义标签、decision 和 comment，不包含源网表。

## ldo_quick.gold.json

- 范围：LDO 的 10 个器件、6 个 net、8 个 port，共 24 项；
- 来源：NetlistLabel 中文复核包，人工逐项确认；
- 用途：smoke/regression gold，不是全局准确率；
- 源网表：外部 SKY130 LDO（ldo.sp），不提交到仓库；
- 决策：全部 accept，包含 D08/D09/D10 的功能备注；
- 已知语义修正：
  - XM59 是 PMOS source follower / common-drain；
  - XM55 是 common-source / mirror output；
  - XM48 是 current mirror reference，不是 dummy；
  - net2 是 cascode 输出 + common-source 输入，标 signal / mirror_gate / interstage_signal。

评测命令：

    python3 -m netlistlabel analyze /path/to/ldo.sp --out out/v02_ldo
    python3 -m netlistlabel evaluate out/v02_ldo/annotation.json benchmarks/gold/ldo_quick.gold.json --out out/eval/ldo_quick

注意：这是 24 项人工复核结果，不是 41 个 MOS 的完整 accuracy；它只证明这些被确认的样本与当前输出一致。

## generic_ota.gold.json

- 范围：synthetic two-stage OTA 的 9 个器件、10 个 net、7 个 port，共 26 项；
- 来源：NetlistLabel 中文复核包，人工逐项确认；
- 用途：换拓扑的 smoke/regression gold，检验规则不是只对 LDO 过拟合；
- 源网表：仓库内 examples/generic_ota/generic_ota.sp，可公开；
- 决策：全部 accept。

评测命令：

    python3 -m netlistlabel analyze examples/generic_ota/generic_ota.sp --out out/v02_generic
    python3 -m netlistlabel evaluate out/v02_generic/annotation.json benchmarks/gold/generic_ota.gold.json --out out/eval/generic_ota

注意：这是 26 项人工确认样本，不是通用 OTA 准确率。

## ldo_mos_rest.gold.json

- 范围：LDO 剩余 34 个 MOS（不含 ldo_quick 已确认的 7 个 MOS）；
- 用途：补全 41 个 MOS 的分批复核记录；
- 决策：全部 accept，含 START bias stack 备注。

## ldo_reviewed.gold.json

- 范围：合并 ldo_quick + ldo_mos_rest，44 个 device + 6 个 net + 8 个 port，共 58 项；
- 覆盖：LDO 41/41 MOS，另有 XR4/XR5、XC1；
- 未覆盖：LDO 剩余 27 个 net，以及 XC3/XR6；
- 决策：全部 accept；
- 用途：LDO MOS 全量 + net/port 抽样的 smoke gold，不是整个 LDO 的全量准确率。

评测命令：

    python3 -m netlistlabel evaluate out/v02_ldo/annotation.json benchmarks/gold/ldo_reviewed.gold.json --out out/eval/ldo_reviewed
