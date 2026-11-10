# MolForge v6.0 完整规划提示词

## 项目背景
MolForge 是一个自研分子建模工作台，目标是对标 GaussView / ChemDraw / Chem3D / VMD。当前版本 v6.0，基于 PyQt6 + VTK 9.7.1，Python 3.13。

## 当前状态
- 主界面：三栏布局（左侧导航 + 中央工作区 + 右侧属性面板）
- 已实现：3D 点选/拖动、框选/套索、右键菜单、xtb 优化、构象搜索、HOMO/LUMO 轨道渲染、二面角扭转势能曲线
- 问题：测量逻辑错误、官能团功能太弱、缺少欢迎界面和独立系统架构

## 核心需求

### 1. 欢迎界面 + 三大独立系统
- 主界面保持现状（三栏布局，功能完整）
- 启动时显示欢迎界面，提供三个入口：
  - **2D UI 系统**：一整套完整的 2D 编辑系统
  - **3D UI 系统**：一整套完整的 3D 多窗口系统（GaussView G:M:V 风格）
  - **2D-3D 分屏系统**：一整套完整的左右分屏系统
- 每个系统都是一整套完整的系统，不是单个窗口

### 2. 3D UI 系统内部架构（GaussView G:M:V 风格）
- **多窗口系统**：G1:M1:V1, G1:M2:V1, G2:M1:V1...
- **每个窗口都是轻量级**：画布 + 顶部菜单 + 底部状态栏
- **窗口内多视图**：1/2/4 视图布局切换
- **菜单系统**：File / Edit / Tools / Builder / View / Calculate / Results / Windows / Help
- **功能模块**：通过菜单弹出独立对话框（不是侧边栏）
- **底部状态栏**：原子数、电子数、电荷、自旋

### 3. 修复测量逻辑错误
- 选中两个相邻键显示键角 36.93°，但实际应该是 110° 左右
- 问题：测了同侧的小角而不是正常的键角
- 需要检查 `molforge/application/measurement.py` 的 angle 函数

### 4. 官能团功能（对标 Gaussian Element Fragments）
- 现状：只能加单个原子
- 期望：元素按钮右键弹出基团面板
  - 选 C → C原子/乙炔基/乙烯基/异丙基/叔丁基/甲基
  - 选 O → O原子/羟基/羰基/醚键
  - 选 N → N原子/氨基/硝基/氰基

### 5. Gaussian 计算设置对话框
- 标签页式对话框：Job Type / Method / Title / Link 0 / General / Guess / Pop. / PBC / Solvation / Add. Inp. / Preview
- 按钮：Submit / Quick Launch / Cancel / Edit / Retain / Defaults

## 技术栈
- Python 3.13 + PyQt6 6.11.0 + VTK 9.7.1
- OpenBabel 3.2.1（格式转换）
- xtb（半经验优化）
- Gaussian 16（外部计算引擎）

## 交付物
- 完整的架构设计文档
- 分阶段实施计划（P0 / P1 / P2）
- 每个阶段的具体任务清单
- 风险评估和回滚方案

## 要求
- 专业级规划，对标 GaussView / ChemDraw
- 考虑 Windows 11 环境兼容性
- 考虑 VTK 多窗口崩溃问题（0xC0000409）
- 保留现有 v6.0 功能，不破坏现有代码
