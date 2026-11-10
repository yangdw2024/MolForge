# MolForge

**AI-native Molecular Workbench**

下一代分子科学工作台，目标是碾压 ChemDraw / Chem3D / GaussView / VMD。

## 快速启动

### 方式 1：双击运行
```
run_molforge.bat
```

### 方式 2：命令行
```bash
cd E:\YDW\Trae_Chemdraw\MolForge
D:\YDW\Trae_Gromacs\miniconda3\envs\molforge-webengine\python.exe scripts\run_ui.py
```

## 当前版本（v1.0 Alpha）已实现

### 架构
- 四层架构：domain / application / rendering / ui / io / ai
- 统一 MoleculeDocument
- 命令总线（CommandBus）+ 撤销/重做
- 事件系统（EventBus）
- 选择服务（SelectionService）

### UI
- 深色主题（#09121E 背景）
- 三栏布局：左侧导航 + 中央工作区 + 右侧面板
- 字体 14px
- 强调色 #66DEC9
- 右侧 5 个 Tab：属性检查、AI 助手、任务、历史、设置

### 2D 编辑器
- 自研 QPainter 2D 绘制
- RDKit 化学引擎
- 原子、键、环、电荷
- 快捷键支持

### 3D 查看器
- VTK 渲染后端
- 球棍 / CPK / 表面模式
- PBR 材质
- SSAO 环境遮蔽
- 交互式点选
- 旋转 / 缩放 / 平移

### AI 助手
- AI 工具注册表（权限分级）
- 提案审批系统
- 可回滚的操作
- 分子摘要查询

### 其他
- 完整元素周期表（120 种元素）
- 格式保真矩阵
- 科学溯源系统
- 插件 SDK
- 国际化（中文）
- 快捷键配置
- .mforge 原生格式

## 示例分子

| 分子 | 化学式 | 原子数 |
|---|---|---|
| 咖啡因 | C₈H₁₀N₄O₂ | 24 |
| 阿司匹林 | C₉H₈O₄ | 13 |
| 苯 | C₆H₆ | 12 |
| 乙醇 | C₂H₆O | 9 |
| 葡萄糖 | C₆H₁₂O₆ | 24 |
| 甲烷 | CH₄ | 5 |
| 水 | H₂O | 3 |

## 项目结构

```
MolForge/
├── molforge/           # 主代码包
│   ├── domain/         # 领域层
│   │   ├── document.py      # MoleculeDocument
│   │   ├── topology.py      # 分子拓扑
│   │   ├── coordinate_store.py  # 坐标存储
│   │   ├── elements.py      # 元素周期表（120 种）
│   │   ├── ids.py          # 稳定 ID
│   │   ├── provenance.py   # 科学溯源
│   │   └── biomolecule.py   # 生物分子
│   ├── application/    # 应用层
│   │   ├── command_bus.py  # 命令总线
│   │   ├── selection.py    # 选择服务
│   │   ├── measurement.py  # 测量三件套
│   │   ├── builtin_commands.py  # 内置命令
│   │   ├── ai_proposals.py # AI 提案系统
│   │   ├── plugins.py      # 插件 SDK
│   │   ├── invalidation.py # 失效机制
│   │   ├── jobs.py         # 任务中心
│   │   ├── events.py        # 事件系统
│   │   ├── reaction.py     # 化学反应
│   │   ├── trajectory.py    # 轨迹播放
│   │   ├── bio_selection.py # 生物分子选择
│   │   └── ports/          # 端口接口
│   ├── rendering/      # 渲染层
│   │   ├── vtk_backend.py  # VTK 后端
│   │   ├── molstar_backend.py  # Mol* 后端
│   │   ├── contracts.py     # Renderer3D 接口
│   │   ├── materials.py     # 材质预设
│   │   ├── orbitals.py      # 分子轨道
│   │   ├── benchmark.py     # 性能基准
│   │   ├── ketcher_bridge.py  # Ketcher 桥接
│   │   └── ketcher_id_mapping.py  # Ketcher ID 映射
│   ├── ui/             # UI 层
│   │   ├── window.py       # 主窗口
│   │   ├── panels.py       # 面板组件
│   │   ├── render3d_widget.py  # 3D 渲染组件
│   │   ├── editor2d_widget.py  # 2D 编辑器组件
│   │   ├── settings_panel.py   # 设置面板
│   │   ├── element_picker.py    # 元素选择器
│   │   ├── theme.py        # 主题样式
│   │   ├── hotkeys.py      # 快捷键
│   │   ├── i18n.py         # 国际化
│   │   └── views.py        # 视图
│   ├── io/             # 输入输出层
│   │   ├── rdkit_adapter.py    # RDKit 适配器
│   │   ├── mforge_storage.py   # .mforge 格式
│   │   ├── conformers.py       # 构象生成
│   │   ├── cclib_adapter.py    # cclib 适配
│   │   ├── calculators.py      # 计算引擎
│   │   └── format_matrix.py    # 格式保真矩阵
│   └── ai/             # AI 层
│       ├── observation.py  # AI 观察
│       └── tools.py        # Tool Registry
├── scripts/            # 运行脚本
├── docs/               # 文档
├── build/              # 构建脚本
└── release/            # 发布材料
```

## 开发路线图

### P0（已完成基本框架）
- [x] 四层架构
- [x] MoleculeDocument
- [x] CommandBus
- [x] VTK 渲染
- [x] 2D/3D 联动
- [x] AI 工具闭环

### P1（进行中）
- [ ] 完整元素周期表 UI
- [ ] 构象搜索
- [ ] 分子轨道可视化
- [ ] 计算结果工作区
- [ ] 大分子基础支持

### P2（规划中）
- [ ] 百万原子交互
- [ ] 长轨迹播放
- [ ] 插件生态
- [ ] AI 科研自动化

## 许可证

内部研究使用，暂不对外分发。

## 致谢

- RDKit
- VTK
- PyVista
- PyQt6
- Ketcher
- Mol*
