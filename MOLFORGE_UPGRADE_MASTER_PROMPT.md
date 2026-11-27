# MolForge 全新升级与架构治理指令（Master Architecture Prompt）

> **使用说明**：本提示词用于直接交付给负责重构升级 MolForge 的 AI Agent、系统架构师或开发团队。旨在彻底终结过去“头痛医头、反复打补丁、越修越崩”的恶性循环，为 MolForge 建立稳定、坚固、现代的分子工作台底座。

---

## 一、项目定位与上下文（Context & Identity）

**MolForge** 是一款桌面级交互式分子工作台（定位对标 GaussView / ChemDraw / Avogadro），负责化学结构 2D 绘制、3D 渲染查看、内坐标编辑（键长/键角/二面角调节、官能团接枝）以及计算化学作业输入/输出管理。
它与底层量子化学计算内核 **CalChem**（高性能纯 Rust 内核，通过 `calchem._core` 导出 C-ABI / NumPy 零拷贝接口）协同工作。

---

## 二、历史病灶深度审视与根因清单（Root-Cause Analysis）

在着手修改代码前，**必须清醒认识到 MolForge 目前存在的 6 大致命架构病根**：

1. **GUI 与底层渲染的“死亡组合”（PyQt6 + VTK + QWebEngineView）**：
   - VTK 内部强引用 C++ 指针，与 PyQt6 的 Qt 对象生命周期及 Python GC 频繁冲突，在 Windows 平台频繁触发 `0x8001010d`（COM RPC 跨线程调用冲突）以及 `0xC0000005`（内存访问越界）致命闪退。
2. **“伪全功能”通胀与系统肥胖（Mock Syndrome / Feature Bloat）**：
   - 盲目铺设 79 个高级分析入口（ESP、HOMO/LUMO、AIM/QTAIM、EDA、MD 轨迹、拉曼/红外谱等），审计发现其中 **64 项是 Experimental（甚至用共用估算冒充真实结果），11 项是 Missing Data**！
   - 虚假功能带来了庞大的死代码与依赖负担，掩盖了核心编辑功能的缺陷。
3. **状态与事实源撕裂（Single Source of Truth 破坏）**：
   - **原子选择丢失顺序**：`selection.py` 使用无序集合 `set[AtomId]`，导致三原子测角 `angle(A, B, C)` 时中心原子 $B$ 被随机错选，二面角调节把错误基团拉扯畸变！
   - **会话分裂**：多窗口克隆时各自分配了独立的 `CommandBus`、`UndoHistory` 与 `SelectionService`，造成同一份分子的编辑历史与状态脱节踩踏。
4. **目录结构重叠混乱**：
   - 代码库中竟然同时并存 `molforge/render/` 与 `molforge/rendering/` 两个包；
   - 遗留了 8 个临时的 `molstar_debug*.html` 以及大量 `_repair`、`_perf_fix` 副本，导入关系错综复杂。
5. **GUI 主线程混杂重度计算**：
   - 在主界面按钮回调中直接执行 RDKit 坐标生成、力场松弛或阻塞式进程拉起，通过 `QApplication.processEvents()` 勉强维持响应，极易引起重入（Reentrancy）崩溃。
6. **与 CalChem 算力内核割裂**：
   - CalChem 已实现毫秒级 Rust 解析梯度、BFGS 优化与 3D 轨道网格生成，但 MolForge 桥接粗糙，未能利用结构化内存直通。

---

## 三、全新升级核心战略与定则（Engineering Directives）

重构升级必须坚决贯彻以下 **四大战略定则**：

### 定则 1：大刀阔斧“瘦身断骨”，去伪存真（Cut the Bloat）
- **绝不保留任何假功能**：将目前 60+ 项无法独立运行、冒充科学结果的“伪功能菜单”彻底下线或收归到单独的扩展插件中。
- **牢牢守住核心黄金三角**：
  1. **分子三维查看与编辑**：丝滑无崩溃的 Ball-and-Stick / Space-Filling 渲染，支持选点、拖拽、旋转。
  2. **精确内坐标调整**：严格保序的 2 原子键长、3 原子键角、4 原子二面角几何修改，必须保持连接基团的刚体几何，必须支持单次事务撤销（Undo）。
  3. **计算化学作业中心**：标准化对接 Gaussian / ORCA / xTB / CalChem 的输入生成、状态监控与结果回填。

### 定则 2：单一事实源与严格命令总线（Single Source of Truth & Command Bus）
- **一个文档，唯一事实**：`MoleculeDocument` 是唯一的几何与化学真相。UI 视口、2D 渲染器、3D 渲染器仅作为该真相的观察者（Observer），严禁在 UI 控件内持有自己的修改副本。
- **保序选择器**：`SelectionService` 必须使用保序队列 `list[AtomId]`，严格记录用户点击原子的时序（First=A, Second=Apex B, Third=C）。
- **结构变更全事务化**：任何官能团接枝、氢原子补全、构象优化回填，必须打包为单一 `CompoundCommand`，实现“一步操作，单次撤销”。

### 定则 3：渲染层解耦与线程安全（Thread & Process Safety）
- **GUI 线程绝对零阻塞**：所有涉及文件读写、RDKit 优化、CalChem 调用的逻辑，必须使用独立后台 `QThread` / `Worker` 或子进程，仅通过 Qt 信号槽将结果传回主线程。
- **渲染目录清洗归一**：彻底废弃删除 `molforge/render/`，统一收拢为现代、清晰的 `molforge/rendering/`。若使用 VTK，必须严格隔离 VTK 对象的生命周期，严禁跨线程访问 GPU 视口句柄。

### 定则 4：全面打通 CalChem 现代高性能底座（CalChem Native Integration）
- **放弃文本文件解析中转**：当用户在 MolForge 中点击“快速优化”或“查看分子轨道”时，直接通过内存调用 `calchem._core.run_optimize` 或 `calchem._core.eval_orbital_cube_zero_copy`。
- **零拷贝渲染**：通过 `numpy_to_vtk` 或 WebGL 共享内存将网格数据直通视口，实现分子轨道 3D 等值面的瞬时秒级呈现。

---

## 四、具体重构实施路线图（Implementation Roadmap）

### Phase 1：目录大扫除与死代码剔除（P0）
1. 彻底删除 `_integration_perf_fix/`、`backup_20261030/`、重复的 `molforge/render/` 及未使用的 `debug_*.html`。
2. 修复 `main.py` 与启动脚本中的硬编码绝对路径。

### Phase 2：修复化学几何核心与选择器（P0）
1. 重构 `selection.py` 为有序列表 `OrderedSelection`，消除测角顶点错位 Bug。
2. 重构 `ModifyInternalCoordDialog` 与坐标微调命令：
   - 键长修改：移动末端及其连接基团；
   - 键角修改：以顶点为旋转轴，旋转臂侧子图；
   - 二面角修改：绕旋转轴键旋转下游子图，不再弹出伪图表。
3. 保证测量服务 `MeasurementService` 不再对 frozen dataclass 做非法属性赋值。

### Phase 3：多视口与会话架构归正（P1）
1. 规范 `DocumentSession`，确保多窗口（G:M:V）共享相同的 `CommandBus` 与数据版本，解决窗口间编辑分裂。
2. 强化后台异步计算队列，避免界面进入“无响应”。

### Phase 4：CalChem 原生集成验证（P2）
1. 完善 `molforge_bridge.py`，实现与 CalChem Rust 扩展的无缝协同。
2. 编写自动化 GUI/科学回归测试，确保在 Windows 10/11 环境无底层崩溃。
