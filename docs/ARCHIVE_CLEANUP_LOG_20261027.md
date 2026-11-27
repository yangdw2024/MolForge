# Trae_Chemdraw 旧项目归档清理记录

- 日期：2026-10-27
- 操作人：Doubao（按用户指令执行）
- 项目路径：`E:\YDW\Trae_Chemdraw`
- 目的：旧 Python/PyInstaller 实现整个废弃，准备从语言与底层设计上完全重构；旧物清理到 Windows 回收站（可恢复），只留新重构资产、设计文档和可独立运行的成品程序。

## 一、清理前盘点（2026-10-27 实测）

| 目录 / 文件 | 大小 | 最后修改 | 定性 |
|-------------|------|----------|------|
| `dist/`（ChemDrawPro + ChemDrawUltra 两个 onedir 成品） | 219.6 MB | 2026-07-06 | **保留**：自包含运行时，双击 exe 可独立运行 |
| `docs/`（7 份设计报告） | 0.1 MB | 2026-10-26 23:12–23:49 | **保留**：全新重构的前期设计/选型文档 |
| `data/elements/`（elements/bond_lengths/geometry 三个 JSON） | 7.5 KB | 2026-10-26 23:44 | **保留**：为新重构准备的元素数据，非旧垃圾 |
| `架构设计_完整方案.md`（根目录，与 docs/00_ 同份） | 13.6 KB | 2026-10-26 23:49 | **保留**：设计文档 |
| `build/`（PyInstaller 中间产物） | 37.5 MB | 2026-07-06 | 删除（回收站） |
| `chemdraw_beautifier/`（旧 Python 源码包） | 1.2 MB | 2026-07-06 | 删除（回收站） |
| `__pycache__/`（根目录与包内） | <0.1 MB | 2026-07-06 | 删除（回收站） |
| `output/`（旧测试输出图，7/3–7/5） | 0.4 MB | 2026-07-05 | 删除（回收站） |
| `examples/`（旧 demo） | <0.1 MB | 2026-07-06 | 删除（回收站） |
| `test_data/`（旧 mol/sdf） | <0.1 MB | 2026-07-05 | 删除（回收站） |
| `config/`（空目录） | 0 | — | 删除（回收站） |
| 根目录旧脚本/spec/图标：`命令行.bat`、`启动图形界面.bat`、`build_exe.bat`、`run_editor.py`、`run_gui.py`、`run_pro_gui.py`、`create_icon.py`、`test_rdkit_cdx.py`、`trae_framework.py`、`build_exe.spec`、`build_ultra.spec`、`ChemDrawPro.spec`、`app_icon.ico`、`icon.png` | <0.1 MB | 2026-07-06 | 删除（回收站） |

## 二、保留清单（重构后直接可用）

1. `docs/`：
   - `00_架构设计_完整方案.md`
   - `分子编辑器技术栈深度选型报告_2026.md`
   - `分子编辑器重构技术选型报告.md`
   - `好看的分子编辑器技术方案.md`
   - `化学数据库标准报告.md`
   - `技术栈深度对比.md`
   - `碾压GaussView_3D渲染技术对比报告.md`
2. `data/elements/`：`elements.json`、`bond_lengths.json`、`geometry.json`
3. `dist/`：`ChemDrawPro\ChemDrawPro.exe`、`ChemDrawUltra\ChemDrawUltra.exe`（均为 onedir 自包含，不依赖根目录源码，可独立运行）
4. 根目录 `架构设计_完整方案.md`

## 三、删除方式与回滚

- 全部删除项走 Windows **回收站**（`Microsoft.VisualBasic.FileIO.FileSystem.DeleteDirectory/DeleteFile`，`RecycleOption.SendToRecycleBin`），不是永久删除。
- 回滚：打开 E 盘回收站，把对应条目还原即可；回收站清空前均可恢复。
- 未对 `dist/`、`docs/`、`data/`、根目录设计文档做任何修改。
- 未安装任何软件、未改动系统环境。

## 四、重构起点建议（记录，非本次执行内容）

- 旧实现为 Python 3.12/3.13 + PyQt（或 tkinter 类 GUI）+ RDKit + Pillow，PyInstaller 打包为 onedir；新重构按 `docs/` 七份报告选定的技术栈重做，不沿用旧源码。
- 旧成品 exe 仅作"历史可运行版本"留存，不再基于它迭代。
