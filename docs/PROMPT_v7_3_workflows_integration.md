# MolForge v7.3 — 科学工作流集成完整提示词

## 任务目标

你是 MolForge 的首席架构师。用户提供了大量真实的科研工作流文档和脚本，你需要：

1. **通读所有工作流文档**，理解每个工作流的输入、输出、步骤、依赖工具
2. **整理成标准化的 MolForge 工作流模块**，每个工作流对应 Results 菜单下的一个独立对话框
3. **写清楚每个工作流的调用方式**：输入什么文件、调用什么外部程序、输出什么结果
4. **不要凭空发明功能**——只实现文档里真实存在的工作流

---

## 输入材料

### 工作流包结构（MolForge_Workflows_Complete_20261030.zip）

```
├── esp-surface-analysis/          # ESP 表面分析（Multiwfn + VMD）
│   ├── SKILL.md
│   └── scripts/
│       ├── compute_descriptors.py
│       ├── draw_ESP.tcl
│       ├── ESPiso_input.txt
│       ├── parse_surfanalysis.py
│       ├── plot_esp_hist.py
│       └── run_esp_surface.ps1
│
├── homo-lumo-plot/                # HOMO-LUMO 能级图
│   ├── SKILL.md
│   ├── extract_orb_energy.py
│   ├── make_level_plot.py
│   ├── render_one.tcl
│   ├── render_straight.tcl
│   └── run_pipeline.py
│
├── osc-energy-level-diagram/      # OSC 能级图
│   ├── SKILL.md
│   └── scripts/
│       ├── extract_levels.py
│       ├── make_editable_pptx.py
│       ├── make_energy_table.py
│       ├── make_level_lines_diagram.py
│       ├── make_rectangle_diagram.py
│       ├── render_one.tcl
│       └── verify_from_log.py
│
├── OSC_MD_workflows/              # OSC 分子动力学后处理（15 个工作流）
│   ├── 00-总览与数据流转.md
│   ├── 01-MD模拟工作流.md
│   ├── 02-RDF分析工作流.md
│   ├── 03-二面角-质心距分析工作流.md
│   ├── 04-二维密度图与粗糙度工作流.md
│   ├── 05-相互作用能IE工作流.md
│   ├── 06-重组能计算工作流.md
│   ├── 07-偶极矩计算工作流.md
│   ├── 08-电子耦合VDA工作流.md
│   ├── 09-电荷转移动力学K工作流.md
│   ├── 10-自由体积FVR工作流.md
│   ├── 11-IGMH弱相互作用工作流.md
│   ├── 12-单体性质工作流.md
│   ├── 13-项目关系分析.md
│   ├── 14-工作流复刻指南.md
│   ├── 15-三元分子对提取逆向分析与二元复刻依据.md
│   └── templates/                 # 全套脚本和模板
│       ├── params.yaml
│       ├── README.md
│       ├── 01-MD/                 # minim/npt/md/ta mdp + 删溶剂脚本
│       ├── 02-RDF/                # 提取原子 + gmx rdf 脚本
│       ├── 03-堆积几何/           # 二面角/质心距分析
│       ├── 04-二维密度/           # RMS 粗糙度 + XPM 密度图
│       ├── 05-IE/                 # 相互作用能计算
│       ├── 06-重组能/             # 中性/阴离子优化 + 单点 gjf
│       ├── 07-偶极矩/             # 偶极矩计算脚本
│       ├── 08-电子耦合/           # VDA GMH 输入
│       ├── 09-速率/               # Marcus 速率计算
│       ├── 11-IGMH/               # IGMH 弱相互作用 gjf + 脚本
│       └── 12-单体性质/           # ESP + UV-Vis gjf
│
├── YDW_Workflow_001/              # 逆向工程出来的工作流报告
│   ├── _workflow_reverse_engineering.md
│   ├── 三重态3CT分析工作流逆向.md
│   ├── 项目总工作流逆向.md
│   ├── 重组能计算工作流逆向.md
│   ├── 自动化重构方案与脚本说明.md
│   ├── 最终数据汇总工作流逆向.md
│   ├── IFCT_full_workflow_analysis.md
│   ├── IFCT_workflow_reverse_engineering.md
│   ├── RDF分析工作流逆向.md
│   ├── w值与W-2数据工作流逆向.md
│   ├── batch_optdftw.sh
│   ├── deep_analysis.py
│   └── opv_pipeline.py
│
└── Trae_Gromacs_docs/             # GROMACS GUI 项目文档
    ├── README.md
    ├── 说明书.md
    ├── 开发工作流规范.md
    ├── docs/                      # 开发文档
    ├── scripts/                   # 工具脚本
    ├── examples/                  # MD 示例（mdp/itp 配置）
    └── 运维操作文档/
```

---

## 具体任务

### 第一步：调研整理（先不要写代码）

通读所有工作流文档，整理出一张**完整的工作流清单表**：

| 编号 | 工作流名称 | 输入文件 | 调用工具 | 输出结果 | 对应菜单位置 |
|------|-----------|---------|---------|---------|-------------|
| WF-01 | ESP 表面分析 | fchk | Multiwfn + VMD | sigma2+/sigma2-/nu/Pi/MPI + ESP 表面图 | 结果 → 波函数分析 → ESP 表面分析 |
| WF-02 | ... | ... | ... | ... | ... |

要求：
- 至少整理出 20+ 个独立工作流
- 每个工作流写清楚：输入是什么、中间步骤是什么、输出是什么
- 标注哪些是"已经有 Python 实现的"、哪些是"只有文档没有代码的"

### 第二步：分类到 Results 菜单

把所有工作流分类到 Results 菜单的子菜单里：

```
结果(&R)
├── 基础性质
│   ├── 分子量 / 分子式 / TPSA
│   ├── 偶极矩
│   └── 分子平面性
├── 波函数分析 (Multiwfn)
│   ├── ESP 表面分析
│   ├── HOMO/LUMO 能级图
│   ├── 轨道可视化
│   ├── 键级分析 (Mayer)
│   └── 电荷分析 (Hirshfeld/ADCH/NPA)
├── 分子间相互作用
│   ├── IGMH 弱相互作用分析
│   ├── 氢键检测
│   ├── π-π 堆积检测
│   └── 能量分解分析 (EDA)
├── 光谱
│   ├── IR 光谱展宽
│   ├── UV-Vis 光谱展宽
│   └── 激发态分析 (空穴/电子)
├── OSC 专题
│   ├── HOMO-LUMO 能级阶梯图
│   ├── OSC 能级对齐图
│   ├── 重组能计算
│   ├── 电子耦合 VDA
│   └── 电荷转移动速率
├── 分子动力学 (GROMACS)
│   ├── MD 模拟设置向导
│   ├── RDF 径向分布函数
│   ├── 二面角/质心距分析
│   ├── 二维密度图与粗糙度
│   ├── 回旋半径 Rg
│   ├── RMSD/RMSF
│   ├── 氢键统计
│   ├── 自由体积 FVR
│   └── 相互作用能 IE
└── 数据导出
    ├── 导出结果表格 (CSV/Excel)
    ├── 导出图表 (PNG/SVG)
    └── 导出可复现脚本
```

### 第三步：实现核心工作流对话框

至少实现以下 8 个工作流的完整对话框（能选择输入文件、显示进度、输出结果）：

1. **ESP 表面分析** — 选择 fchk → 调用 Multiwfn → 输出描述符表格 + BWR 表面图
2. **HOMO-LUMO 能级图** — 选择多个 fchk → 提取能级 → matplotlib 画阶梯图
3. **OSC 能级对齐图** — 给体+受体 fchk → 画能级对齐图
4. **重组能计算** — 输入中性/阴离子结构 → 计算 λh/λe
5. **偶极矩分析** — 读取 fchk/log → 显示偶极矩矢量
6. **分子平面性分析** — SVD 最佳拟合平面 → RMSD + 最大离面距离
7. **MD 后处理：RDF** — 选择轨迹文件 → 调用 gmx rdf → 画 RDF 曲线
8. **IGMH 弱相互作用** — 生成 gjf → 调用 Gaussian → 可视化 IGMH 等值面

### 第四步：外部工具探测

实现一个统一的**工具路径配置对话框**：
- 自动探测本机的：Gaussian 16、Multiwfn、GROMACS、VMD、OpenBabel、xtb
- 用户可以手动指定路径
- 配置保存在 QSettings 里
- 在 `计算 → 引擎状态...` 菜单里打开

---

## 技术约束

1. **所有对话框都用中文**
2. **外部调用用 subprocess**，不要阻塞 GUI 线程（用 QThread 或 QRunnable）
3. **工作流脚本放在 `molforge/workflows/` 目录下**
4. **每个工作流一个 Python 文件**，比如 `esp_surface.py`、`homo_lumo_plot.py`
5. **不要硬编码个人路径**——所有路径从配置里读
6. **先实现"能跑通"的最小版本**——不要追求完美，先把流程走通

---

## 交付物

1. **工作流清单表**（`docs/WORKFLOWS_CATALOG.md`）：所有工作流的完整列表
2. **8 个核心工作流对话框代码**
3. **工具路径配置对话框**
4. **Results 菜单更新**——把所有工作流挂到菜单里
5. **修改记录**——改了哪些文件、怎么验证

---

## 注意事项

- 先读所有工作流文档，理解清楚再写代码
- 不要凭空发明功能——只实现文档里真实存在的工作流
- 每个工作流对话框要诚实：如果外部工具没配置好，就提示用户配置，不要假装成功
- 用户是 OSC 方向的研究生，这些工作流都是他实际用过的，不要瞎编
