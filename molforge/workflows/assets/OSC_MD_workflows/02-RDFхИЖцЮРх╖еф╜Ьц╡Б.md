# 02 · RDF 径向分布函数分析工作流

> 数据目录：`RDF\`、`数据\RDF-yuan\`
> 软件：Python（原子组提取）+ GROMACS `gmx rdf` + Origin（成图）

---

## 一、目的

径向分布函数 g(r) 反映体系中某两类原子/分子组之间的空间分布相关性，用于表征：
- **D/A 界面接触距离**（第一近邻峰位置 r 与强度 g(r)）；
- **同组分自聚集**（A1-A1、A2-A2、D-D）；
- **片段级堆积模式**（给体 BDD/BDT 片段 ↔ 受体 IC/BTP 片段）。

---

## 二、两级分析结构

RDF 分"骨架级（backbone）"与"片段级（Fragment）"两层，对应两个子目录：

| 目录 | 级别 | 组定义 |
|------|------|--------|
| `RDF\backbone-md1~4\` | 骨架级 | 整条共轭骨架原子 |
| `RDF\Fragment-md1~4\` | 片段级 | 给体 BDD/BDT、受体 IC/BTP/TP 片段 |

另有 `数据\RDF-yuan\` 存放：
- `A2-A2\`：受体-受体 RDF（BTx-BTx、BTxBTP-BTxBTP、BTxIC-BTxIC，含 eC9 参比）；
- `平均RDF\`：按体系/DA1/DA2 的平均 RDF（含 RDF-D-D/D-A/A-A 四象限）；
- `拟合RDF\`：拟合后的 RDF 数据与 A1-A2 片段 RDF（A1IC-A2IC、A1IC-A2TP、A1TP-A2IC、A1TP-A2TP）。

---

## 三、工作流步骤

### 3.1 步骤1：Python 提取原子组索引

每个体系一个 `test-MDn` 目录，内含多个 `*.py` 脚本，每个脚本从 .gro 中提取指定分子的骨架/片段原子号，输出 `*.out` 索引文件：

**骨架级脚本**（`backbone-mdn\test-MDn\`）：

| 脚本 | 提取对象 | 输出 | 用于 RDF |
|------|----------|------|----------|
| `A11.py` | HDO(A1) 骨架原子（~68 个） | `A11.out` | A1-A1 |
| `A22.py` | BTn(A2) 骨架原子 | `A22.out` | A2-A2 |
| `DA1.py` | HDO(A1) 骨架原子（自 D.gro） | `DA1.out` | D-A1 |
| `DA2.py` | BTn(A2) 骨架原子（自 D.gro） | `DA2.out` | D-A2 |

**片段级脚本**（`Fragment-mdn\test1-MDn\`，含"脚本识别"修订版）：

| 脚本 | 提取对象 |
|------|----------|
| `D1.py`~`D4.py` | 给体 PM6 的 4 个重复单元片段 |
| `A1.py`~`A4.py` | 受体 HDO/BTn 的片段 |
| `IC1.py` / `IC2.py` | 受体 IC 单元（含 Cl） |
| `TP1.py` / `TP2.py` | 受体端基（TP = terminal part） |

**脚本逻辑**（以 A11.py 为例）：
```python
filename = open('1.gro')
filename2 = open('A11.out','w')
HDO = ['C14','C15','...','Cl1','Cl2','Cl3','Cl4', ...]   # 目标原子名列表
for line in filename.readlines():
    if num > 2:
        lineArr = line.strip().split()
        if lineArr in HDO:              # 命中目标原子名
            ...写入原子号（每15个换行）...
```

> 注意：脚本中变量名常沿用 `HDO` 但内容实际可能是 BTn 原子（如 DA2.py），
> 阅读脚本时必须看**原子名列表本身**而不是变量名，避免张冠李戴。

### 3.2 步骤2：gmx rdf 计算

```
gmx rdf -f {轨迹}.gro/.xtc -s {tpr} -n index.ndx -o {输出}.xvg -sel 组1 组2 ...
```

- 轨迹/结构：`1.gro` / `D.gro`（按需取不同帧）
- 索引：`indexB.ndx` / `index.ndx` / `all-index.ndx`（由 make_ndx 或手工生成）
- 输出：`*.xvg`（g(r) vs r）

> RDF 的"组"来自步骤1 的原子号文件；gmx rdf 支持 `-sel` 直接从原子号文件定义组，或先 `make_ndx` 写入 .ndx。

### 3.3 步骤3：平均与拟合

- 多帧/多块轨迹的 RDF 取平均 → `平均RDF\`；
- 对 g(r) 曲线做**拟合**（Origin 或脚本）得到峰位、峰高 → `拟合RDF\`（`fitting_data*.txt`、`RDF-*.xls`）；
- 常用指标：第一近邻峰位置 r₁（接触距离）、峰强度 g(r₁)、配位数（峰下面积分）。

### 3.4 步骤4：Origin 成图

- 各体系 RDF 用 Origin（`.opju`）叠加对比：同类型界面（如 DA1）跨体系一张图；
- 片段级常用"最强接触对"作结论：如 BDD-IC、BDT-BTP 等。

---

## 四、结果解读要点

1. **r₁ 越小、g(r₁) 越高** → 界面接触越紧密、越有序。
2. 骨架级 RDF 的短程峰（<0.2 nm）可能是**链段环绕导致的 COM 质心距**，不能直接当作硬球原子接触距离；化学接触需用**片段级 RDF** 或原子对 RDF 佐证。
3. 峰高 g(r) 受体系密度与组内粒子数影响，跨体系比较注意归一化口径。
4. 片段级 RDF 用于判断具体堆积模式：如"BDD-IC 接触主导"表明给体给电子单元与受体端基 IC 紧贴，利于电荷转移。

---

## 五、数据规模与产物

| 项目 | 数量 |
|------|------|
| .xvg（RDF 曲线） | ~288（骨架+片段） |
| .py（提取脚本） | ~116 |
| .xlsx（汇总） | ~32 |
| .opju（Origin） | ~25 |
| .tif（图） | ~30 |
| 总计 | ~442 MB |
