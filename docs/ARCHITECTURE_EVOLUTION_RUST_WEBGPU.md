# MolForge 长期架构演进评估：Python + PyQt6 + VTK 向 Rust / WebGPU 迁移路线

日期：2026-11-16  
基线版本：MolForge v7.4.2

## 1. 当前架构的天花板诊断

当前 `MolForge v7.4.2` 采用 **Python 3.13 + PyQt6 + VTK (pyvistaqt) + RDKit + NumPy**：

| 维度 | 当前实测表现（v7.4.2） | 架构瓶颈根因 |
|---|---|---|
| **32 万原子加载** | ~8.60 秒，峰值工作集 ~1.58 GB | Python 对象循环（`Atom` / `Bond` dataclass、Dict 邻接表）与 RDKit `Mol` 双份内存驻留 |
| **32 万原子单步编辑** | 删除重原子+末端氢+刷新 ~13.67 秒 | `CommandBus` 拓扑重建 + 全量 VTK `PolyData` 重建与 CPU 端 glyph 变换 |
| **2D 绘布渲染** | >1500 原子已强制禁用，>3000 原子硬熔断 | QPainter 逐节点绘制与 RDKit 2D 坐标生成在万级原子下复杂度爆炸 |
| **百万至千万级原子 60 FPS** | 无法达标 | CPU 端生成球体/圆柱三角面片，未做 GPU Instancing + 空间八叉树/LOD 剔除 |

结论：在 **中小分子（< 2,000 原子）与常规量子化学前后处理** 场景下，Python + PyQt6 + VTK 已经能满足稳定交付；但若目标是 **10 万～1000 万原子高分子/MD 盒子流畅 60 FPS 交互**，继续在 Python 层打补丁无法突破 GIL 与对象内存开销，必须将“数据结构 + 渲染管线”下沉。

---

## 2. 推荐演进架构：Rust Core + GPU Instancing（两条可行路线）

### 路线 A：渐进式混合架构（推荐，风险最低）
- **保留**：现有 `PyQt6` 桌面壳与 Python 科研生态（RDKit、cclib、Gaussian/ORCA/Multiwfn 驱动、MCP 服务）。
- **下沉（PyO3 / maturin）**：
  1. 用 **Rust SoA (Structure of Arrays)** 替代 Python `Atom`/`Bond` 对象字典：连续 `Vec<f32>` 存坐标、`Vec<u8>` 存元素序数、`Vec<u32>` 存键索引，32 万原子内存可从 ~1.5 GB 降至 **< 30 MB**，加载时间降至 **< 0.3 秒**。
  2. 在 Rust 中实现空间哈希成键、最小镜像 PBC 测量、Kabsch 对齐与轨迹帧零拷贝读取。
- **渲染升级**：在 VTK 中启用真正的 GPU `vtkGlyph3DMapper` 硬件实例化（或嵌入独立原生 wgpu 视口窗口），仅传输每帧变动的 Instance Buffer（坐标 + 半径 + RGBA）。

### 路线 B：下一代原生桌面架构（Tauri 2 + WebGPU/wgpu + Rust）
- **前端**：TypeScript + React/Svelte 轻量 UI + WebGPU 渲染管线（Impostor Sphere Raymarching 球棍着色器，无需生成三角面片，单帧可稳跑 500 万+ 原子）。
- **后端**：Rust 核心引擎直接管理拓扑、力场、轨迹流式读取与本地 MCP 服务；通过本地 RPC/PyO3 桥接调用 RDKit 与量子化学解析器。
- **适用时机**：当决定彻底重写桌面前端、脱离 PyQt6 时采用。

---

## 3. 分阶段实施建议

1. **阶段 1（当前已完成）**：`v7.4.2` 稳态基线 —— 对 >3,000 原子体系硬熔断 2D 画布，修复刷新去重与 LOD，确保中小体系与量化分析工作流可靠。
2. **阶段 2（1~2 周）**：将大体系 PDB/GRO/XTC 解析、空间网格成键与距离矩阵下沉至 Rust (`molforge_core` PyO3 扩展)，消除 Python 循环内存膨胀。
3. **阶段 3（3~4 周）**：3D 视口切换至 Impostor Shader（单原子仅需 1 个 Billboard Quad / 4 顶点），实现 30 万~200 万原子 60 FPS 旋转缩放。
4. **阶段 4（长期）**：如全面转向 Web/跨平台桌面，再基于已沉淀的 Rust Core 切换至 Tauri + WebGPU 前端。
