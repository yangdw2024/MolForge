# MolForge Studio 8.1.0 升级与遗留问题清零验收报告（2026-11-27）

## 1. 本次升级范围与核心结论

本次工作围绕 `E:\YDW\Trae_Chemdraw`（`desktop/` Electron 35 + React 19 + WebGPU + `molforge-core/` 纯 Rust 后端，版本 `8.1.0`）完成了全部遗留问题清零、**CalChem v0.3.0**（`E:\YDW\Trae_Gaussian`）全泛函与偶极矩集成、Multiwfn 3.8 多波函数分析扩展、纯 Rust MPP/SDP 平面性与成对 RDF 求解、OSC 重组能与 GROMACS 五文件工作流闭环，以及根目录 Git 版本控制初始化。

所有临时探测与 Multiwfn 缓存已统一隔离至 `D:\YDW\MolForge_Scratch\`，C 盘 `%TEMP%\molforge*` 清理并验证归零（`C_TEMP_REMAINING=0`）。

---

## 2. 已完成改造清单

| 模块 | 文件 | 关键改动与验证结论 |
| --- | --- | --- |
| **CalChem v0.3.0 集成** | `molforge-core/crates/molforge-core/Cargo.toml`<br>`molforge-core/crates/molforge-core/src/qc.rs`<br>`molforge-core/crates/molforge-core/src/engines.rs` | 引入 `calchem-prop`，实现 `HF/RHF/UHF/RKS/UKS/DFT` 与 `B3LYP/B3LYP5/PBE/PBE0/BLYP/LDA/SVWN5/CAM-B3LYP/wB97X/wB97X-D` 调度，补全闭壳层/开壳层偶极矩与 `n_ao` 输出；清理唯一编译警告，版本提示更新为 `0.3.0`。 |
| **纯 Rust MPP/SDP 与 RDF** | `molforge-core/crates/molforge-core/src/summary.rs`<br>`molforge-core/crates/molforge-core/src/engines.rs` | 新增 `jacobi_3x3_eigen` 与重原子最小二乘平面 `compute_planarity`（`PROP-MPP`，含 MPP/SDP/逐原子偏离）；新增 `compute_pairwise_rdf`（支持周期性晶胞矩阵或分子包络），单测 `benzene_and_caffeine_planarity`、`caffeine_rdf_has_bond_length_first_peak` 通过。 |
| **Multiwfn 3.8 扩展与诚实边界** | `molforge-core/crates/molforge-core/src/engines.rs`<br>`desktop/electron/main.ts`<br>`desktop/electron/security.ts` | 实机探测验证 stdin 序列并接入 `WFN-01`（ESP：`12\n0\n-1\n-1\nq\n`）、`WFN-06`（Mayer：`9\n1\nn\n0\nq\n`）、`WFN-08`（ADCH：`7\n11\n1\nn\n0\nq\n`）及 `WFN-12`（NCI/RDG）；严格校验波函数扩展名（`.fch/.fchk/.wfn/.wfx/.molden`）并拒绝裸坐标输入；处理非 ASCII 路径；文件读取白名单与对话框扩展至 `.wfn/.wfx/.molden/.fch`。 |
| **后端契约统一与作业/工作流补全** | `molforge-core/crates/molforge-server/src/main.rs`<br>`molforge-core/crates/molforge-core/src/workflow.rs`<br>`molforge-core/crates/molforge-core/src/hub.rs` | 抽取共享 `format_calchem_json()` 统一 `/api/qc/run_calchem` 与 `/api/jobs/submit`（`calchem_sp\|calchem_opt`）契约；补齐 `/api/jobs/submit` 对 `analysis`、`clean_3d`、`md_rdf`/`trajectory_rdf` 的调度；修复 `/api/md/generate_gromacs` 返回 5 个 `.mdp/.sh` 文件及 `gmx_available/gmx_path`；新增 `/api/qc/reorganization_energy` 四点法重组能接口；注册 `trajectory.rdf`、`structure.planarity` 与 `org.molforge.workflow.osc-4char`。 |
| **桌面端 UI 与契约修复** | `desktop/src/services/api.ts`<br>`desktop/src/views/AnalysisView.tsx`<br>`desktop/src/components/layers/CalculationSetupModal.tsx`<br>`desktop/scripts/probe-hotkey-20261120.mjs` | 前端接入全套 CalChem v0.3.0 泛函、MPP/RDF 快捷分析、`WFN-01/06/08/12` 波函数文件选择与 OSC 四点法重组能计算器；移除 `CalculationSetupModal.tsx` 中 `def2-SVP -> 6-31G` 的静默替换；补全 ESLint 声明。 |
| **前次遗留问题 5 项全清零** | `docs/desktop/fix_20261120/FIX_STATE.md` | 1) jobs calchem 臂契约已统一；2) Windows 发行包与 `molforge-server.exe` 已重打包对齐；3) C 盘 `%TEMP%\molforge*` 已清零；4) `md-rdf` 执行适配器已真实接入；5) 仅存的 1 个 Rust 编译警告已消除（0 errors / 0 warnings）。 |

---

## 3. 构建、单测与端到端实测结果

### 3.1 编译与静态检查
- **Rust 核心**：`cargo test --features calchem` 全部 20/20 单测通过；`cargo build --release --features calchem` 退出码 `0`（**0 errors, 0 warnings**）。
- **二进制一致性校验**：
  - `molforge-core/target/release/molforge-server.exe`：`24,092,160` bytes，SHA-256 `61AD6B0E65AD1863ED8E6E50812D653D8BA9AC69F584B6A6A92D6BE5A1BC0C29`
  - `desktop/resources/core/molforge-server.exe`：SHA-256 完全一致
  - `desktop/release/win-unpacked/resources/core/molforge-server.exe`：SHA-256 完全一致
- **桌面端检查与单测**：`npm run typecheck` 通过、`npm run lint` 0 errors、`npm test` 4 个文件共 12 项测试（含 `api_parity_contract.test.ts`）全部通过。
- **Windows 安装包重建**：`npm run pack:win` 退出码 `0`，产出 `desktop/release/win-unpacked/`、`desktop/release/MolForge-Studio-8.1.0-win-x64-setup.exe`（`100,639,895` bytes）及 `desktop/release/MolForge-Studio-8.1.0-win-x64-portable.exe`（`90,383,465` bytes）。

### 3.2 升级专项验收套件（`verify_upgrade.ps1`）
执行日期：2026-11-27，结果：**`TOTAL=11 PASS=11 FAIL=0`**（原始输出见 `docs/desktop/upgrade_20261127/verify_upgrade_output.log`）：
- **U01** `/api/health`：`version=0.1.0 calchem=True`
- **U02** `/api/engines/status`：`calchem=0.3.0 available=True`
- **U03** CalChem v0.3.0 `HF/STO-3G` + 偶极矩 + `n_ao`：`E=-74.9630230993387 dip=1.725304942091846 nao=7`
- **U04** CalChem v0.3.0 `rks + B3LYP/STO-3G`：`E=-75.31252861233484 dip=1.6784381070194418`
- **U05** `/api/jobs/submit` `calchem_sp` 统一契约：`ok=True homo_ev=-3.9234046552655153 dip=1.6784381070194418`
- **U06** `PROP-MPP` 纯 Rust 平面性：`benz_mpp=0.0 caf_mpp=0.0016`
- **U07** `MD-RDF`（`analysis/run` + `jobs/submit` + `workflow`）：`peak=1.1469A wf=completed sha=a7548d29cc1a`
- **U08** OSC 4-char 工作流（TB + MPP）：`status=completed nodes=4`
- **U09** Multiwfn 4 项能力（`WFN-12/01/06/08` + 裸坐标拒假）：`nci_pts=133458 esp_min=-29.50431 mayer_bonds=3 adch_atoms=4`
- **U10** GROMACS 5 文件返回契约 + 四点法重组能：`gmx_files=5 lambda_mev=272.11386246001916`
- **U11** C 盘 Temp 零残留 + D 盘 Scratch 隔离校验：`C_temp=0 D_mwfn_dirs=5`

### 3.3 UI 全量端到端与打包冷启动验证
- **36 项深度交互 E2E（`scripts/fix-retest-e2e-20261120.mjs`）**：**`TOTAL=36 PASS=36 FAIL=0`**，无渲染进程未捕获异常。
- **打包版冷启动 10 场景 E2E（`node scripts/run-electron-e2e.mjs --packaged`）**：基于最新重建的 `desktop/release/win-unpacked/MolForge Studio.exe` 冷启动执行，退出码 `0`（`ALL 10 SCENES & FLOWS PASSED WITH ZERO ERRORS!`），测试后校验 `C_TEMP_REMAINING=0`。
