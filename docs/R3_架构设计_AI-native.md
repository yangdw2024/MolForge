# R3 架构设计：AI-native 分子工作台

> 日期：2026-10-27
> 状态：替代 R2，作为后续开发的架构依据
> 核心定位：**不是 ChemDraw 替代品，而是一个让 LLM 当"化学眼睛"的分子工作台**

---

## 一、核心定位（先想清楚再写代码）

用户的痛点不是"没有好看的画图工具"，而是：

1. **ChemDraw 接不了 LLM API**——它只能画，不能"理解"分子
2. **计算化学工作流是割裂的**——Gaussian 输入、输出、cube、轨道分析散在不同软件里
3. **AI 应该是一等公民**——不是"加个聊天窗口"，而是 AI 能直接操作分子、读计算结果、建议下一步

所以 MolForge 的定位是：

> **一个以 Molecule 为核心对象、以 LLM 为操作主体、打通计算化学输入输出全链路的桌面工作台。**

人做决策（选哪个分子、跑什么计算），AI 做解释和操作（这个分子 HOMO 多少、这个 log 哪里错了、帮我写个 gjf），软件做渲染和持久化。

---

## 二、分层架构（每层独立可测，不跨层调用）

```
┌─────────────────────────────────────────────┐
│  ui/         PyQt6 界面层                    │
│  ├─ 主窗口、2D 视图、3D 视图、属性面板        │
│  ├─ AI 对话面板（聊天式，工具调用可视化）     │
│  └─ 文件操作（打开/导出，走 io/ 注册表）      │
├─────────────────────────────────────────────┤
│  ai/         LLM 操作层（一等公民）           │
│  ├─ tools.py     AI 可调用的工具集           │
│  ├─ context.py   AI 上下文（当前分子、工作目录）│
│  └─ llm_client.py  OpenAI 兼容客户端        │
├─────────────────────────────────────────────┤
│  render/    渲染层                          │
│  ├─ render2d.py  RDKit → SVG/PNG            │
│  ├─ render3d.py  PyVista → 球棍/轨道/表面    │
│  └─ colors.py    CPK 配色（从 data/elements/ 读）│
├─────────────────────────────────────────────┤
│  io/         格式读写层（插件化）             │
│  ├─ registry.py  格式注册表（扩展名 → handler）│
│  ├─ readers/     每种格式一个 reader         │
│  │   ├─ smi_reader.py                       │
│  │   ├─ mol_reader.py    (MOL/SDF)          │
│  │   ├─ gjf_reader.py    (Gaussian 输入)     │
│  │   ├─ glog_reader.py   (Gaussian log 输出)│
│  │   ├─ cube_reader.py   (cube 轨道)        │
│  │   └─ xyz_reader.py    (XYZ)             │
│  └─ writers/     每种格式一个 writer         │
│      ├─ gjf_writer.py    (Gaussian 输入)     │
│      ├─ svg_writer.py     (发表级图)         │
│      ├─ png_writer.py                       │
│      └─ orca_writer.py    (ORCA 输入，二期)  │
├─────────────────────────────────────────────┤
│  core/       核心数据模型（最底层）            │
│  ├─ molecule.py   Molecule 一等公民对象        │
│  ├─ conformer.py  3D 构象                    │
│  ├─ orbital.py    分子轨道（能量、占据、cube）│
│  └─ properties.py 性质计算                   │
└─────────────────────────────────────────────┘
```

**依赖方向严格单向**：ui → ai/render/io → core。core 不依赖任何上层。

---

## 三、核心数据模型：Molecule 是一等公民

所有层都围绕一个 `Molecule` 对象转。它不是简单包一层 RDKit Mol，而是一个完整的化学对象：

```python
@dataclass
class Molecule:
    # 身份
    id: str                    # UUID
    name: str | None           # 用户起的名字

    # 化学结构（2D 图）
    rdkit_mol: Chem.Mol        # 核心：原子、键、芳香性

    # 3D 构象
    conformers: list[Conformer]   # 可能有多个构象

    # 计算化学附加数据（不是所有分子都有）
    energy: float | None = None       # 单点能
    orbitals: list[Orbital] = None    # MO 能级（HOMO/LUMO/...）
    source_format: str = "smiles"      # 从什么格式读来的
    source_path: Path | None = None

    # 缓存
    properties: dict = field(default_factory=dict)
```

这样设计的好处：
- 读一个 Gaussian log，不只是得到结构，还得到能量、轨道、cube 数据，全在一个对象里
- AI 拿到这个对象，就能解释能量、画轨道、建议下一步
- 导出 gjf 时，直接从这个对象生成，不用重新解析

---

## 四、IO 插件化（加格式不改主流程）

```python
class FormatHandler(ABC):
    @property
    def name(self) -> str: ...
    @property
    def extensions(self) -> list[str]: ...   # ['.mol', '.sdf']
    @property
    def can_read(self) -> bool: ...
    @property
    def can_write(self) -> bool: ...
    def read(self, path: Path) -> Molecule: ...
    def write(self, mol: Molecule, path: Path): ...
```

注册机制：
```python
# 每个 reader/writer 自己注册
@register
class MolReader(FormatHandler): ...
@register
class GjfWriter(FormatHandler): ...

# UI 打开文件对话框时，从注册表列出所有支持的扩展名
# 加新格式 = 写一个新类，不动主窗口代码
```

**一期要实现的格式**：

| 方向 | 格式 | 用途 |
|---|---|---|
| 读 | SMILES | 最常用输入 |
| 读 | MOL/SDF | 化学结构交换 |
| 读 | XYZ | 通用 3D 坐标 |
| 读 | Gaussian gjf | 读已有计算输入 |
| 读 | Gaussian log | 读计算结果（能量/HOMO/LUMO/正常终止） |
| 读 | cube | 读轨道密度 |
| 写 | Gaussian gjf | 提交计算（接你 gaussian-dsh-plugin） |
| 写 | SVG/PNG | 发表级图 |
| 写 | MOL/SDF | 结构交换 |

二期再补 ORCA、VASP、LAMMPS、PDB、CIF 等。

---

## 五、AI 工具集（LLM 是操作者）

AI 不是一个"聊天窗口"，而是通过一组工具直接操作 Molecule：

```python
class AIContext:
    """AI 操作分子的上下文。"""

    def __init__(self, mol: Molecule, workdir: Path):
        self.mol = mol
        self.workdir = workdir

    # ---- 这些是 AI 可以调用的工具（function calling）----

    def compute_properties(self) -> dict:
        """计算并返回分子性质（MW、LogP、TPSA、HBA/HBD...）。"""

    def generate_conformer(self, seed: int = 42) -> Molecule:
        """生成 3D 构象（ETKDG + MMFF 优化）。"""

    def submit_gaussian(self, route: str, method: str, basis: str) -> str:
        """
        提交 Gaussian 计算。
        route 例：'opt freq'，method 例：'b3lyp'，basis 例：'6-31g(d,p)'。
        返回 job_id。实际通过 gaussian-dsh-plugin 的后端 API 提交。
        """

    def read_gaussian_log(self, path: Path) -> dict:
        """
        读 Gaussian log 文件，解析：
        - 正常/错误终止
        - 最终能量
        - HOMO/LUMO 能级
        - 偶极矩
        - SCF 迭代次数
        """

    def draw_orbital(self, index: int):
        """在 3D 视图画指定轨道（需要 cube 文件）。"""

    def suggest_next_step(self) -> list[str]:
        """
        根据当前分子状态，建议下一步计算。
        例：刚读了一个 log，建议"接下来做频率分析"或"换个更大基组"。
        """
```

LLM 通过 OpenAI function calling 调用这些方法。界面上的 AI 对话面板显示：
- 用户："这个阿司匹林的 HOMO 是多少？"
- AI：（调用 `compute_properties`）→ "阿司匹林的 HOMO 是 -8.2 eV..."
- 用户："帮我跑一个 B3LYP/6-31G(d) 单点能"
- AI：（调用 `submit_gaussian(route='sp', method='b3lyp', basis='6-31g(d)')`）→ "已提交，job_id=xxx"

这和你 gaussian-dsh-plugin 的工具注册是同一个思路，只是搬到了桌面应用里。

---

## 六、代码质量红线

1. **每个文件不超过 300 行**。超过就拆。
2. **不写巨型 main_window.py**。界面拆成 widget：2D 视图、3D 视图、属性面板、AI 面板、文件栏。
3. **不硬编码路径、版本号、配色**。读 `config/` 和 `data/elements/`。
4. **每个 reader/writer 独立可测**：给一个测试文件，能单独跑通 read/write，不依赖 UI。
5. **core/ 不 import PyQt6**。数据模型是纯 Python，UI 只是它的视图。
6. **不跨层调用**：ui 不直接读文件（走 io/），io 不直接调 LLM（走 ai/）。

---

## 七、一期实现清单（按优先级）

1. core/molecule.py + conformer.py + orbital.py 数据模型
2. io/registry.py 注册机制
3. io/readers/：smi、mol、gjf、glog、cube（先把 Gaussian log 解析做扎实，这是你最常用的）
4. io/writers/：gjf、svg、png
5. ai/tools.py AIContext 骨架（先实现 compute_properties、read_gaussian_log 两个，接 LLM 放后面）
6. ui/ 重构：主窗口拆成 widget，加 AI 对话面板（先占位，接 LLM 放二期）

跑通一个 demo：读一个真实 Gaussian log → 解析能量/HOMO/LUMO → 在界面显示 → AI 能解释"这个分子能量收敛了，HOMO -8.2 eV，建议下一步做频率分析"。

---

## 八、和 R2 的区别

| 维度 | R2（上一版） | R3（本版） |
|---|---|---|
| 核心对象 | RDKit Mol 包一层 | Molecule 完整数据模型（含能量/轨道/cube） |
| AI 地位 | "二期再说" | 一等公民，工具集是核心 |
| 格式支持 | "一期先做 SMILES" | 插件化注册表，先做 Gaussian 全链路 |
| 代码组织 | 一个 main_window.py | 分层，每层独立可测 |
| 目标 | 好看的分子查看器 | AI 驱动的计算化学工作台 |
