# Results 79 项功能核查（v7.2）

审查依据为 Results 注册表与 `CapabilityResolver.execute_analysis` 的具体分支。这里标明代码有无具名计算路径；它不是对数值精度的认证。

| 分类 | 对应 ID | 当前实现状态 |
| --- | --- | --- |
| 专项分析分支 | CORE-01, CORE-02, PROP-01, PROP-02, PROP-04, PROP-06, WFN-01, WFN-02, WFN-03, WFN-07, OSC-01, OSC-04, OSC-05, OSC-06, INTER-02, INTER-03, INTER-04, INTER-05, INTER-06, INTER-07, DRUG-01, DRUG-02, DRUG-03, DRUG-04, DRUG-05 | 各自进入具名分支。需分别确认输入来源与方法边界；不能视为全都由外部量化程序计算。 |
| 光谱共用分支 | SPEC-01 至 SPEC-08 | 共用 TD-DFT/紧束缚 UV-Vis 和谐振振动路径；不代表八个子项均有独立的文献级方法。 |
| MD 共用分支 | MD-01 至 MD-18 | 注册功能仍共用同一 RMSD/Rg 表与 GROMACS 脚本，不能据此认为 RMSF、RDF、氢键、聚类等各项都已完成。另新增的 Results「MD 轨迹 RMSD/Rg 后处理」使用可选 MDAnalysis 逐帧计算 RMSD 和 Rg。 |
| 通用摘要（28 项） | CORE-03, CORE-04, CORE-05, CORE-06; WFN-04, WFN-05, WFN-06, WFN-08, WFN-09, WFN-10, WFN-11, WFN-12, WFN-13, WFN-14, WFN-15, WFN-16, WFN-17; PROP-03, PROP-05, PROP-07, PROP-08; INTER-01; OSC-02, OSC-03; INFRA-01, INFRA-02, INFRA-03, INFRA-04 | 无对应具名专项分支。现在按 Experimental 展示，不会把通用原子坐标/Rg 摘要标为 Ready。 |

**计数**：79 项；25 项具名分支、8 项共用光谱路径、18 项共用 MD 路径、28 项通用摘要。分类可能交叉（例如注册描述与实际共享算法不同），故不要把这些数相加当作“完成数”。

## 新增菜单工作流

- **ESP**：已接入用户 Multiwfn/VMD 说明的串行调用器。工作流需要本机引擎配置；原始输出、日志和产生的图像留在新建结果目录。描述符只保存实际从引擎输出解析到的字段。
- **HOMO/LUMO 与 OSC**：实现 fchk 流式轨道读取；OSC 需要同一计算的 fchk/log，差异大于 0.05 eV 即停止。输出三种 SVG 图、CSV/JSON、Excel 和可编辑 PPTX（可选依赖）；HOMO 流程另调用 Multiwfn/VMD 生成轨道图。
- **平面性**：对重原子坐标做最佳拟合平面计算，报告 RMSD、最大离面距离和跨度。
- **偶极矩**：从 fchk 报告总偶极向量和 Debye 值；未自动推断分子片段偶极。
- **分子间相互作用**：坐标检测显式 N/O/S 氢键、重原子接触，以及 RDKit 可识别的平行/T 型芳香环堆积；接触/角度阈值是筛查判据。
- **MD**：可选 MDAnalysis 后处理逐帧 RMSD/Rg，要求使用者预处理适当的周期边界。
- **能量分量**：可由 CSV 计算经典力场的 `E_AB-E_A-E_B`。随附 GROMACS 脚本模板需要拓扑、索引和轨迹，并不是 sobEDA；未包装成量子化学 EDA 结果。

外部执行依赖 Multiwfn/VMD 或可选 MDAnalysis。这里没有这些 Windows 可执行程序和 `.fchk` 样例，因而只验证了解析器、几何计算和流程控制代码，实际外部图像生成仍需在用户环境验收。
