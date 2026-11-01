# Disclaimer

AnalogNetlistLabel / NetlistLabel 输出的是**语义提案**，不是已经签核的电路事实。

- 不替代 SPICE 仿真；
- 不做 DRC / LVS / PEX；
- 不声称版图、面积或硅后结果正确；
- 不修改源网表；overlay 和 annotated.sp 都是独立副本；
- 所有 role / class / block 都需要人工复核，尤其是 review=confirm / unknown；
- 不包含任何公司 PDK、未公开网表、NDA 数据或 foundry 规则；
- 真实开源网表只作为外部 benchmark 引用，不默认复制进仓库；
- 评测数字是 smoke/regression 结果，不是通用的生产准确率。

如果用于真实项目，请把输出当作“带证据的起点”，由设计 owner 做最终确认。
