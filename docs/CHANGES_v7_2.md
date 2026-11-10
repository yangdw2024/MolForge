# MolForge v7.2 修改与验证记录

## Studio 界面

- `ui/shells/document_tabs.py`：三个独立 Studio 使用底部 `QTabWidget`，文档各自持有 `DocumentSession`、CommandBus、SelectionService；支持新建、打开、复制、重命名、关闭、切换、MDI 平铺/层叠、合并到三栏主系统。
- `ui/shells/studio_2d.py`、`studio_3d.py`、`studio_split.py`：接入标签与中文可浮动工具栏。多视口仍复用同一 VTK RenderWindow 的 SetViewport。
- `ui/window.py`：经典三栏的中央区域改为文档标签；新建/打开建立文档页，右侧属性跟随活动文档，右键菜单支持复制/重命名/弹出 2D 或 3D Studio。
- `ui/welcome_window.py`：欢迎卡片说明对齐设计目标；命令行指定 mode 的入口保留。

## 科学工作流

- `molforge/workflows/assets/`：随项目保留用户提供的 ESP、HOMO/LUMO、OSC 能级、平面性、偶极和 OSC/MD 工作流脚本/说明，用于追溯和复现。
- `molforge/workflows/scientific_workflows.py`：fchk 流式读取、log/fchk 能级核对、平面性拟合、总偶极提取、串行 Multiwfn/VMD 运行、OSC 输出三种 SVG 图、CSV/JSON、Excel 和可编辑 PPTX（openpyxl/python-pptx 可选依赖）、逐帧 MDAnalysis RMSD/Rg、氢键占有率（可检测时）与 RMSD/Rg 特征聚类、跨分子氢键/接触和 GROMACS 能量分量差计算。
- `ui/shells/workflow_inputs.py` 与 `ui/qc_result_dialog.py`：Results 菜单新增 ESP、HOMO/LUMO、OSC、平面性、偶极、相互作用、GROMACS 分量差和 MD 后处理对话框。较长外部流程在工作线程运行。
- 无具名专项计算分支的 Results 项继续标记 Experimental；分类清单见 `docs/RESULTS_FAKE_FEATURES.md`。
- `requirements-md.txt`：MDAnalysis 为可选依赖，未加入主 GUI 依赖。

## 验证

- Python compileall：通过。
- 用合成的 formatted-checkpoint 与 Gaussian log 文本核对能级解析；用平面与非平面坐标检查拟合平面计算。
- 从 OSC/MD 用户工作流包复制的 GROMACS 脚本留作参考。脚本中的工作目录参数、分组拓扑和 `TPR_REF` 必须由具体项目提供，未伪称为开箱即跑。
- 现有 `run_molforge.bat` 已包含任务书指定 D 盘 Python 路径。

## 仍需本机验证

运行 Multiwfn/VMD、Windows GUI 启动与交互、多视口截图，需要用户机现有引擎路径和真实量化文件；这份上传包没有 fchk 输入，也没有 Gaussian、Multiwfn、VMD 或 GROMACS 二进制。MDAnalysis、MD轨迹的逐帧后处理需要按 `requirements-md.txt` 安装后验收。

相互作用中的 π 堆积识别、完整分量拓扑准备/自动运行、sobEDA、完整 18 种 MD 分析以及跨标签 2D/3D 并排比较仍未完成。保留源文件旁的 `.bak` 供人工回滚。
