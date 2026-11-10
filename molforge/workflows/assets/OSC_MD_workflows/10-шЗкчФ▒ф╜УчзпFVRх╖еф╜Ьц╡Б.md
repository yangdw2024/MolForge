# 10 · 自由体积 FVR 工作流

> 数据目录：`FVR\24-now-new\`、`数据\最后1ns的自由体积\`
> 软件：GROMACS `gmx freevolume` + 自定义格点法（.cub 输出）+ VMD/VESTA/Origin

---

## 一、目的

计算活性层中未被分子原子范德华表面占据的**自由体积**及其三维分布：
- 自由体积分数（FFV）→ 链段迁移能力；
- 自由体积空间分布 → 局部堆积密度差异；
- 关联相分离形貌与器件稳定性。

---

## 二、两种计算路线

### 2.1 路线A：GROMACS gmx freevolume（时间序列）

```
gmx_mpi freevolume -f ply-md3.part0004.xtc -s ply-md3.tpr -o freevolume.xvg \
                   -b 69000 -e 70000 -radius 0
```

- `-b/-e`：取末段（如最后 1 ns）平衡窗口；
- `-radius 0`：探针半径为 0；
- 输出 `freevolume0~4.xvg`：自由体积随时间变化（`数据\最后1ns的自由体积\`）。

### 2.2 路线B：三维格点法（.cub 体数据）

- 在三维网格上逐点判断是否落在任意原子的范德华半径内，标记"自由/占据"；
- 输出 Gaussian Cube 格式 `0free_smooth.cub` ~ `4free_smooth.cub`（每体系 ~834 MB，网格极密）；
- `smooth`：对格点做高斯平滑消除网格锯齿；
- 用 VMD / ChimeraX / Multiwfn 可视化等值面，或 Origin（`FVR.opju`）汇总。

---

## 三、目录与产物

`FVR\24-now-new\`：

| 文件 | 内容 |
|------|------|
| `0free_smooth.cub`~`4free_smooth.cub` | 5 体系自由体积格点（834 MB 每个） |
| `0free_smooth.tif`~`4free_smooth.tif` | 可视化切片图 |
| `FVR.opju` | Origin 汇总图 |

---

## 四、解读要点

1. **FFV 大** → 链段自由度高、分子重排容易，但也可能意味着堆积松散、电荷传输路径少；
2. 自由体积分布与相分离相关：给/受体富集区与界面空洞分布影响激子扩散与载流子迁移；
3. 与 RDF / 二面角-质心距联动：堆积越有序（RDF 峰越尖），自由体积通常越小；
4. 跨体系比较注意使用同一探针半径与格点参数。

---

## 五、数据规模

| 项目 | 数量 | 大小 |
|------|------|------|
| .cub | 5 | ~4.2 GB |
| .tif | 5 | ~10 MB |
| .opju | 1 | ~0.3 MB |
| 总计 | ~11 | ~4.18 GB |
