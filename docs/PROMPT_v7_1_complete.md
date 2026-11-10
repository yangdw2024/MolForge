# MolForge v7.1 完整架构规划提示词

## 项目背景
MolForge 是一个自研分子建模工作台，目标是对标 GaussView / ChemDraw / Chem3D / VMD。
当前版本 v7.0，基于 PyQt6 + VTK 9.7.1，Python 3.13。

## ⚠️ 重要警告：不要包装现有窗口！

**不要把 Studio2DWindow / Studio3DWindow / StudioSplitWindow 做成 MolForgeWindow 的包装类！**

你需要创建**全新的 QMainWindow**，从零构建简洁的 GaussView 风格窗口。

---

## 核心需求：真正的 GaussView 风格简洁窗口

### 窗口布局（以 Studio3DWindow 为例）

```
┌─────────────────────────────────────────────────┐
│ File  Edit  Build  View  Calculate  Results  Help│ ← 顶部菜单栏
├─────────────────────────────────────────────────┤
│                                                 │
│                                                 │
│                                                 │
│              VTK 3D 画布                         │ ← 中央占满整个区域
│              (占满整个中央区域)                   │
│                                                 │
│                                                 │
│                                                 │
├─────────────────────────────────────────────────┤
│ Atoms: 12  Electrons: 46  Charge: 0  Spin: 1   │ ← 底部状态栏
└─────────────────────────────────────────────────┘
```

### 明确禁止
- ❌ 不要左侧导航栏（模板库、元素周期表等）
- ❌ 不要右侧属性面板
- ❌ 不要顶部工具栏（Build/Select 按钮栏）
- ❌ 不要包装 MolForgeWindow
- ❌ 不要改个标题就说是新窗口

### 明确要求
- ✅ 顶部菜单栏（只有菜单，没有工具栏）
- ✅ 中央 VTK 画布（占满整个中央区域）
- ✅ 底部状态栏（原子数、电子数、电荷、自旋）
- ✅ 所有功能通过菜单弹出对话框
- ✅ 全新的 QMainWindow，不继承 MolForgeWindow

---

## 三大独立系统

### 1. Studio2DWindow（2D 化学绘图系统）
- 对标 ChemDraw
- 顶部菜单：File / Edit / Structure / Build / View / Calculate / Results / Help
- 中央：2D 画布（QGraphicsView）
- 底部：状态栏
- 所有编辑工具通过菜单或右键菜单触发

### 2. Studio3DWindow（3D 建模系统）
- 对标 GaussView
- 顶部菜单：File / Edit / Build / View / Calculate / Results / Windows / Help
- 中央：VTK 3D 画布（支持 1/2/4 视口）
- 底部：状态栏（Atoms / Electrons / Charge / Spin）
- 支持 G:M:V 多窗口并排

### 3. StudioSplitWindow（2D-3D 分屏系统）
- 左半：2D 画布
- 右半：3D 画布
- 共享同一 DocumentSession
- 跨画布选择/编辑同步

---

## 欢迎界面

### WelcomeWindow
- 启动时显示
- 四个大卡片：2D 设计 / 3D 设计 / 2D-3D 分屏 / 经典三栏
- 点击进入对应的全新窗口（不是包装 MolForgeWindow）

---

## Results 菜单（完整后处理分析）

### 波函数分析（Multiwfn 集成）
- ESP 表面分析
- HOMO/LUMO 能级图
- OSC 能级图
- ELF 电子定域化函数
- LOL 定域轨道定位器
- Mayer 键级分析
- Hirshfeld 电荷分析
- ADCH 电荷分析
- NPA 电荷分析
- 电子空穴分析
- IRI 相互作用区域指示

### 分子性质
- 平面性分析
- 偶极矩计算
- 分子体积与表面积
- logP 预测
- pKa 预测
- 分子描述符

### 分子间相互作用
- 能量分解分析（EDA）
- NCI 非共价相互作用
- AIM 分子中的原子理论
- 氢键分析
- π-π 堆积分析

### 光谱分析
- IR 红外光谱
- Raman 拉曼光谱
- UV-Vis 紫外可见
- NMR 核磁共振
- CD 圆二色谱

### 分子动力学（GROMACS 集成）
- MD 模拟设置
- 轨迹可视化
- RMSD / RMSF 分析
- 回旋半径
- 氢键分析
- 径向分布函数（RDF）
- 二面角分析
- 能量分析
- 聚类分析

---

## 技术栈
- Python 3.13 + PyQt6 6.11.0 + VTK 9.7.1
- OpenBabel 3.2.1
- xtb（路径：E:\ORCA\software\ORCA6.1.1\xtb-6.7.1pre\xtb.exe）
- Gaussian 16（路径：D:\G16W）
- Multiwfn 3.8（路径：D:\Multiwfn\Multiwfn_3.8_bin_Win64\Multiwfn.exe）
- GROMACS
- VMD（路径：D:\VMD\vmd.exe）

---

## 交付物
1. 全新的 Studio2DWindow / Studio3DWindow / StudioSplitWindow（不包装 MolForgeWindow）
2. 真正的欢迎界面（默认启动显示）
3. Results 菜单完整功能
4. Multiwfn 工作流集成
5. GROMACS 工作流集成

---

## 再次警告

**不要包装 MolForgeWindow！不要改个标题就说是新窗口！**

你需要创建**全新的 QMainWindow**，从零构建简洁的 GaussView 风格窗口。

旧的 MolForgeWindow（三栏布局）作为"经典三栏"选项保留，不要动它。
