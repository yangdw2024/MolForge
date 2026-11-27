# 审计经验文档（2026-11-19 MolForge Studio 8.1 真实性审计）

> 触发条件：E2E 脚本四轮执行错误（选择器/交互手法）+ 发现 11 项严重产品 Mock。按项目规则"多次执行错误/严重错误修复必须写经验文档"建立。

## 一、真机 Electron E2E 选择器教训（四轮纠错）

| 轮次 | 错误 | 根因 | 修正 |
|---|---|---|---|
| 1 | `aside` 定位导航超时 | 导航不是 aside 语义标签 | 改用 `[data-testid="nav-editor"]` 等稳定 testid |
| 2 | `[data-testid="canvas-2d"] circle` 匹配 0 | testid 挂在 `<svg>` 自身，Playwright 空格=后代选择器 | `svg[data-testid="canvas-2d"]` |
| 3 | HUD `.fixed`/`.glass-panel` 匹配 0；toast 文本找不到 | FloatingWindow 根 div 用内联 `position:fixed` 但 className 只有 absolute；**通知不是 toast**，是状态栏铃铛→NotificationsDrawer | 用 `div[style.zIndex]` + 标题文本定位浮窗；错误验证改读通知抽屉（button[title="查看事件与通知日志"]） |
| 4 | Shift 多选测量不稳定；砌块库点击无效 | ① 画布空白点若落在 svg padding 区不触发 deselect，shift 点击变成 toggle-off；② 浮窗最小化状态跨开关持久，需先点 button[title='展开']；③ 按 `b` 热键被 App.tsx 抢占为建键工具，后续点击全变建键 | 选分散原子索引；每次测量前确认选择态；操作前按 `v` 回选择工具；浮窗先展开 |

**通用法则**：
1. 先读组件源码拿 testid/结构，再写选择器；不要猜语义标签。
2. 内联 style 定位（zIndex/position）比 class 更稳（tailwind 类名易变）。
3. 测量/选择类断言失败先怀疑"选择态"，用截图+store 双重确认，再下产品结论。
4. API 侧改文档不会刷新前端 store（无轮询）——UI 断言前必须经 UI 动作加载分子，否则徽章/上下文是旧值（I1 首轮误报根因）。

## 二、Zero-Mock 识别方法论（本次验证有效）

1. **耗时指纹**：真外部进程不可能 0.4ms 完成（run_external）；真 LLM 不可能 347ms 返回完整分析（模板）。耗时与物理下限矛盾=Mock 信号。
2. **产物指纹**：真引擎必留工作目录产物（xtb 的 .xtboptok/xtbopt.xyz）。workdir 0 文件=未执行。
3. **数据指纹**：散点图 y 值若等于原子序数序列=占位数据；二面角恒 0.00°=硬编码；XYZ 导出 Z 全 0=假 3D。
4. **对照实验**：同一接口发"前端真实载荷"vs"后端期望载荷"，结果差异即契约错配（delete_atoms ids/atom_ids 对照 12→12 vs 12→11）。
5. **独立复算**：Provenance 的 SHA256 用本地 Get-FileHash 独立重算比对，不信任自报。
6. **进程级交叉验证**：对可疑外部引擎（Multiwfn）自行 spawn 同命令序列，读完整 stdout 确认到底执行了什么菜单路径。
7. **UI 断言≠功能真实**：标准 E2E 10 场景全过仍漏掉全部 RED——因为旧 E2E 只断言"元素存在/文本出现"，不断言"状态真实变化"。审计 E2E 必须断言前后差值（原子数、键级、坐标、z-index）。

## 三、严重产品缺陷模式归纳（供修复与回归）

- **模式 A 假完成**：handler 返回 completed 但无副作用（run_external、jobs else 分支）。回归测试：检查 workdir 产物/进程日志，而非 status 字段。
- **模式 B 静默降级**：失败回退模板/默认值且不标注（AI 模板、能级 -5.50/-3.50、inspect C/12.011）。回归测试：断言降级标记存在。
- **模式 C 契约错配**：前后端字段名不一致→no-op 或 400 且 ok=true/无 toast（ids/pos_2d/kind/api_key/hetero/center_2d）。回归测试：api_parity_contract.test.ts 应扩展为"载荷级"契约（当前仅路由集合级，故 12/12 全过仍漏报）。
- **模式 D 宣传缺项**：UI 目录硬编码 ID 后端目录不存在（pentacene/Y6/ITIC/C60）。回归测试：UI 目录 ID 集合 ⊆ 后端 /api/fragments 集合。

## 四、回滚与资产治理记录

- 旧 E2E 截图 12 张已备份 evidence/ui/prev_test_artifacts/（新运行覆盖前）。
- 审计未修改任何产品源码；服务端内存态变更（分子切换/测试 Key）均已恢复或记录；测试 Key 已清空（ai_api_key=""）。
- 新增资产全部在 docs/desktop/audit_20261119/ 与 desktop/scripts/audit-*.mjs（3 个），无 C 盘安装。
- molforge-server.exe PID 33584 保留运行（用户开应用会复用 18765）；如需停止：Stop-Process -Id 33584。