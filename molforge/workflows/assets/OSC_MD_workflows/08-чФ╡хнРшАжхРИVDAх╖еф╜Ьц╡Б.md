# 08 · 电子耦合 V_DA 计算工作流（Q-Chem GMH）

> 数据目录：`VDA\`（md1-vda ~ md4-vda）
> 软件：Q-Chem 5.4
> 方法：omegaB97XD / 6-31G**, CIS 激发态 + GMH（广义 Mulliken-Hush）电子转移耦合
> 输入：D-A 分子对构型（ply-{分子}-{帧}-{配对}.inp）

---

## 一、目的

计算给体-受体（D-A）分子对间的电子转移耦合矩阵元 V_DA，作为 Marcus 速率（见 09 文档）的核心输入。V_DA 反映 D/A 间电子云重叠程度，直接决定电荷转移快慢。

---

## 二、Q-Chem 输入关键参数

```text
$molecule
  ...坐标（D + A 两个片段）
$end

$rem
   EXCHANGE         wB97XD
   BASIS            6-31G**
   CIS_N_ROOTS      3              # 3 个单重激发态
   CIS_SINGLETS     true
   CIS_TRIPLETS     false
   STS_GMH          true           # 开启 GMH 电子转移耦合计算
   STS_ACCEPTOR     1-85           # 受体片段原子编号
   STS_DONOR        86-231         # 给体片段原子编号
   MEM_STATIC       3000
   SOLVENT_METHOD   SMD            # 隐式溶剂
$end

$smx
   SOLVENT Trichloromethane        # 三氯甲烷
$end
```

### GMH 方法原理

广义 Mulliken-Hush（GMH）通过 diabatic 态变换，从绝热激发态的跃迁偶极矩 μ12 与态间能量差 ΔE12 计算电子转移耦合：

```
V_DA = |μ12 · ΔE12| / sqrt(Δμ12^2 + 4μ12^2)
```

- ΔE12：态间能量差
- μ12：跃迁偶极矩
- Δμ12：态间偶极矩差

---

## 三、工作流步骤

1. 选构型：从 MD 平衡轨迹按 D-A 接触对提取二聚体构型（残基编号对，如 43-255）
2. 拆片段：在输入中指定受体片段（STS_ACCEPTOR）与给体片段（STS_DONOR）原子区间
3. Q-Chem 计算：CIS 单点 + GMH，SMD=氯仿
4. 提取 V_DA：从输出中读取 GMH 电子耦合值（输出含激发能、振子强度、跃迁偶极矩、GMH 耦合）

---

## 四、输出内容（.out）

| 项目 | 说明 |
|------|------|
| CIS 激发能 | 第 1~3 激发态能量（eV） |
| 振子强度 / 跃迁偶极矩 | 态间跃迁性质 |
| GMH ELECTRONIC-COUPLING | V_DA 耦合矩阵元 |
| 态偶极矩 | 基态/激发态偶极矩 |

---

## 五、数据规模

| 项目 | 数量 |
|------|------|
| .inp 输入 | ~3（模板，其余复用） |
| .out 输出 | ~132 |
| 覆盖 | BTn + HDO 分子对，md1~md4 |
| 总计 | ~13 MB |

---

## 六、要点与坑

1. 片段原子区间必须与构型对应：不同受体（BTn/HDO）原子数不同，需按实际结构划分 D/A 片段
2. V_DA 强烈依赖 D/A 相对几何：应从 MD 统计的代表性接触构型取多个分子对求平均/分布
3. GMH 适用于中性 D-A 对的电荷分离态耦合；若做电荷复合需对应态选择
4. 隐式溶剂（三氯甲烷）与 MD 体系（氯仿）保持一致的口径
5. V_DA 与二面角-质心距、RDF 结果联动：接触距离越小、平面越平行则 V_DA 越大
