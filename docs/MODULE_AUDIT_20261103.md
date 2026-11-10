# 模块审计 2026-11-03 / 7.3.3

153个Python模块导入成功；79项注册入口均构造成功；237个主菜单末级动作均有连接。上述检查不是全部科研计算端到端验收。

以咖啡因结构、无额外波函数/轨迹输入检查旧79项注册入口：4项本地可执行，64项Experimental，11项Missing Data。
11项缺输入也不代表补文件即有完整专项算法。独立MD/四点法/ESP等工作流与这份旧注册表分开评估。

| ID | 功能 | 本轮状态 | 检查结果/边界 |
|---|---|---|---|
| CORE-01 | 计算结果摘要 Summary | Ready | 本地实现可执行 (Gaussian/ORCA/cclib)；外部引擎未据此认证 |
| CORE-02 | 优化过程 Optimization | Experimental | 注册入口缺少对应专项算法/可靠输入链；共用估算不能冒充此项。请使用已验证的独立工作流。 |
| CORE-03 | 电子结构结果表 Atom/Bond Properties | Experimental | 尚无独立专项算法，不能作为正式科学结果 |
| CORE-04 | 势能扫描 Scan | Experimental | 尚无独立专项算法，不能作为正式科学结果 |
| CORE-05 | IRC 与反应路径 | Experimental | 尚无独立专项算法，不能作为正式科学结果 |
| CORE-06 | 表面与等值线管理 | Experimental | 尚无独立专项算法，不能作为正式科学结果 |
| WFN-01 | ESP 表面+σ²+、σ²−、ν、Π、MPI | Experimental | 注册入口缺少对应专项算法/可靠输入链；共用估算不能冒充此项。请使用已验证的独立工作流。 |
| WFN-02 | HOMO/LUMO 能级与等值面 | Experimental | 注册入口缺少对应专项算法/可靠输入链；共用估算不能冒充此项。请使用已验证的独立工作流。 |
| WFN-03 | OSC 给体受体能级对比 | Experimental | 注册入口缺少对应专项算法/可靠输入链；共用估算不能冒充此项。请使用已验证的独立工作流。 |
| WFN-04 | ELF 电子定域函数 | Missing Data | [WFN-04] 需加载外部波函数或计算输出文件 (有效波函数)；当前仅生成可复现批处理脚本。 |
| WFN-05 | LOL 局域轨道定位器 | Missing Data | [WFN-05] 需加载外部波函数或计算输出文件 (有效波函数)；当前仅生成可复现批处理脚本。 |
| WFN-06 | Mayer/Wiberg 键级 | Experimental | 尚无独立专项算法，不能作为正式科学结果 |
| WFN-07 | Hirshfeld 电荷 | Experimental | 注册入口缺少对应专项算法/可靠输入链；共用估算不能冒充此项。请使用已验证的独立工作流。 |
| WFN-08 | ADCH 电荷 | Missing Data | [WFN-08] 需加载外部波函数或计算输出文件 (有效波函数及对应分析支持)；当前仅生成可复现批处理脚本。 |
| WFN-09 | NPA 自然布居电荷 | Missing Data | [WFN-09] 需加载外部波函数或计算输出文件 (含 NPA/NBO 分析段的源结果)；当前仅生成可复现批处理脚本。 |
| WFN-10 | 电子-空穴分布 | Missing Data | [WFN-10] 需加载外部波函数或计算输出文件 (激发态波函数或跃迁密度)；当前仅生成可复现批处理脚本。 |
| WFN-11 | IRI 弱相互作用区域 | Missing Data | [WFN-11] 需加载外部波函数或计算输出文件 (有效波函数或支持的密度输入)；当前仅生成可复现批处理脚本。 |
| WFN-12 | NCI/RDG/s(ρ) 图 | Missing Data | [WFN-12] 需加载外部波函数或计算输出文件 (密度/密度梯度或波函数)；当前仅生成可复现批处理脚本。 |
| WFN-13 | AIM/QTAIM 拓扑 | Missing Data | [WFN-13] 需加载外部波函数或计算输出文件 (波函数/密度)；当前仅生成可复现批处理脚本。 |
| WFN-14 | 电荷密度与 Laplacian | Experimental | 尚无独立专项算法，不能作为正式科学结果 |
| WFN-15 | 差分密度与密度重排 | Experimental | 尚无独立专项算法，不能作为正式科学结果 |
| WFN-16 | 轨道组成 DOS/PDOS | Experimental | 尚无独立专项算法，不能作为正式科学结果 |
| WFN-17 | 自旋密度与多参考指标 | Experimental | 尚无独立专项算法，不能作为正式科学结果 |
| PROP-01 | 平面性与二面角分布 | Ready | 本地实现可执行 (NumPy/RDKit)；外部引擎未据此认证 |
| PROP-02 | 偶极矩矢量 | Experimental | 注册入口缺少对应专项算法/可靠输入链；共用估算不能冒充此项。请使用已验证的独立工作流。 |
| PROP-03 | SASA 与体积 | Experimental | 尚无独立专项算法，不能作为正式科学结果 |
| PROP-04 | logP 模型预测 | Ready | 本地实现可执行 (RDKit Crippen)；外部引擎未据此认证 |
| PROP-05 | pKa 模型预测 | Experimental | 尚无独立专项算法，不能作为正式科学结果 |
| PROP-06 | MW/TPSA/HBD/HBA/可旋转键 | Ready | 本地实现可执行 (RDKit Descriptors)；外部引擎未据此认证 |
| PROP-07 | 形状、PMI 与三维描述符 | Experimental | 尚无独立专项算法，不能作为正式科学结果 |
| PROP-08 | 多构象性质比较 | Experimental | 尚无独立专项算法，不能作为正式科学结果 |
| INTER-01 | EDA 能量分解 | Missing Data | [INTER-01] 需加载外部波函数或计算输出文件 (带明确分解方案的结果)；当前仅生成可复现批处理脚本。 |
| INTER-02 | 氢键网络 | Experimental | 注册入口缺少对应专项算法/可靠输入链；共用估算不能冒充此项。请使用已验证的独立工作流。 |
| INTER-03 | π-π 堆积 | Experimental | 注册入口缺少对应专项算法/可靠输入链；共用估算不能冒充此项。请使用已验证的独立工作流。 |
| INTER-04 | 范德华接触 | Experimental | 注册入口缺少对应专项算法/可靠输入链；共用估算不能冒充此项。请使用已验证的独立工作流。 |
| INTER-05 | 盐桥与阳离子-π | Experimental | 注册入口缺少对应专项算法/可靠输入链；共用估算不能冒充此项。请使用已验证的独立工作流。 |
| INTER-06 | 蛋白质-配体接触指纹 | Experimental | 注册入口缺少对应专项算法/可靠输入链；共用估算不能冒充此项。请使用已验证的独立工作流。 |
| INTER-07 | 分子配对/结合能比较 | Experimental | 注册入口缺少对应专项算法/可靠输入链；共用估算不能冒充此项。请使用已验证的独立工作流。 |
| SPEC-01 | IR 红外与模式动画 | Experimental | 共用模型估计路径，不等同于独立TD-DFT/实验光谱 |
| SPEC-02 | Raman 拉曼 | Experimental | 共用模型估计路径，不等同于独立TD-DFT/实验光谱 |
| SPEC-03 | UV-Vis/TD-DFT | Experimental | 共用模型估计路径，不等同于独立TD-DFT/实验光谱 |
| SPEC-04 | NMR 化学位移与谱模拟 | Experimental | 共用模型估计路径，不等同于独立TD-DFT/实验光谱 |
| SPEC-05 | CD/ECD 圆二色谱 | Experimental | 共用模型估计路径，不等同于独立TD-DFT/实验光谱 |
| SPEC-06 | ORD 旋光色散 | Experimental | 共用模型估计路径，不等同于独立TD-DFT/实验光谱 |
| SPEC-07 | 振电耦合 Vibronic | Experimental | 共用模型估计路径，不等同于独立TD-DFT/实验光谱 |
| SPEC-08 | 振动模式表与同位素比较 | Experimental | 共用模型估计路径，不等同于独立TD-DFT/实验光谱 |
| MD-01 | MD 设置向导 | Experimental | 旧注册项共用路径，请使用真实轨迹综合分析工作台 |
| MD-02 | 轨迹播放器 | Experimental | 旧注册项共用路径，请使用真实轨迹综合分析工作台 |
| MD-03 | RMSD | Experimental | 旧注册项共用路径，请使用真实轨迹综合分析工作台 |
| MD-04 | RMSF | Experimental | 旧注册项共用路径，请使用真实轨迹综合分析工作台 |
| MD-05 | 回旋半径 Rg | Experimental | 旧注册项共用路径，请使用真实轨迹综合分析工作台 |
| MD-06 | 轨迹氢键占有率 | Experimental | 旧注册项共用路径，请使用真实轨迹综合分析工作台 |
| MD-07 | RDF | Experimental | 旧注册项共用路径，请使用真实轨迹综合分析工作台 |
| MD-08 | 二面角时间序列 | Experimental | 旧注册项共用路径，请使用真实轨迹综合分析工作台 |
| MD-09 | 能量与温度压力 | Experimental | 旧注册项共用路径，请使用真实轨迹综合分析工作台 |
| MD-10 | 构象聚类 | Experimental | 旧注册项共用路径，请使用真实轨迹综合分析工作台 |
| MD-11 | PCA 与自由能景观 | Experimental | 旧注册项共用路径，请使用真实轨迹综合分析工作台 |
| MD-12 | MSD/扩散系数 | Experimental | 旧注册项共用路径，请使用真实轨迹综合分析工作台 |
| MD-13 | SASA / 二级结构时间演变 | Experimental | 旧注册项共用路径，请使用真实轨迹综合分析工作台 |
| MD-14 | 原子接触/盐桥持久性 | Experimental | 旧注册项共用路径，请使用真实轨迹综合分析工作台 |
| MD-15 | 伞形采样 WHAM/PMF | Experimental | 旧注册项共用路径，请使用真实轨迹综合分析工作台 |
| MD-16 | Metadynamics 重加权 | Experimental | 旧注册项共用路径，请使用真实轨迹综合分析工作台 |
| MD-17 | FEP/TI/BAR/MBAR | Experimental | 旧注册项共用路径，请使用真实轨迹综合分析工作台 |
| MD-18 | MM/PBSA 或 MM/GBSA | Experimental | 旧注册项共用路径，请使用真实轨迹综合分析工作台 |
| OSC-01 | D/A 能级真空基准对齐 | Experimental | 注册入口缺少对应专项算法/可靠输入链；共用估算不能冒充此项。请使用已验证的独立工作流。 |
| OSC-02 | 电子/空穴转移 NTO | Missing Data | [OSC-02] 需加载外部波函数或计算输出文件 (TDDFT 转换数据)；当前仅生成可复现批处理脚本。 |
| OSC-03 | 激子/CT 指标与跃迁密度 | Missing Data | [OSC-03] 需加载外部波函数或计算输出文件 (激发态计算文件)；当前仅生成可复现批处理脚本。 |
| OSC-04 | 重组能 λh/λe | Experimental | 注册入口缺少对应专项算法/可靠输入链；共用估算不能冒充此项。请使用已验证的独立工作流。 |
| OSC-05 | 光谱与吸收边比较 | Experimental | 注册入口缺少对应专项算法/可靠输入链；共用估算不能冒充此项。请使用已验证的独立工作流。 |
| OSC-06 | 电子耦合与电子转移路径 | Experimental | 注册入口缺少对应专项算法/可靠输入链；共用估算不能冒充此项。请使用已验证的独立工作流。 |
| DRUG-01 | Lipinski/Veber/PAINS 快速评估 | Experimental | 注册入口缺少对应专项算法/可靠输入链；共用估算不能冒充此项。请使用已验证的独立工作流。 |
| DRUG-02 | 质子化/互变异构体枚举 | Experimental | 注册入口缺少对应专项算法/可靠输入链；共用估算不能冒充此项。请使用已验证的独立工作流。 |
| DRUG-03 | ADMET/QSAR 预测 | Experimental | 注册入口缺少对应专项算法/可靠输入链；共用估算不能冒充此项。请使用已验证的独立工作流。 |
| DRUG-04 | 受体-配体接触与口袋测量 | Experimental | 注册入口缺少对应专项算法/可靠输入链；共用估算不能冒充此项。请使用已验证的独立工作流。 |
| DRUG-05 | 对接结果整理与重评分 | Experimental | 注册入口缺少对应专项算法/可靠输入链；共用估算不能冒充此项。请使用已验证的独立工作流。 |
| INFRA-01 | Analysis Registry 目录 | Experimental | 尚无独立专项算法，不能作为正式科学结果 |
| INFRA-02 | 结果图表与论文导出 | Experimental | 尚无独立专项算法，不能作为正式科学结果 |
| INFRA-03 | 批量分析/高通量运行 | Experimental | 尚无独立专项算法，不能作为正式科学结果 |
| INFRA-04 | AI 辅助分析助手 | Experimental | 尚无独立专项算法，不能作为正式科学结果 |

## 实际运行的独立链路
- 本机GFN2-xTB水分子优化（无冻结/冻结O两组）成功；冻结坐标误差0，源文档未变。
- GROMACS --version退出0；这是启动探测，没有提交GPU模拟。
- 四原子平面样例：SVD RMSD=0 Å，JSON/CSV/PQR生成；是已知几何反例。
- 四点法：已知合成SCF能量日志，λ总=1.36057 eV，输出JSON/图表；验证解析/代数，不是Gaussian计算实跑。
- 实际VTK离屏渲染1000×760，透明/彩色Gaussian柔光改变像素；已运行纯3D导出与14个自然编号合成。

Gaussian、Multiwfn、VMD的本轮状态是路径检测；未提供本轮真实波函数任务，不宣称这些引擎全部计算成功。
真LLM请求、独立MCP协议、完整79项专项算法、干净机器安装器、双屏长时拖拽及原生美观验收仍未闭合。
