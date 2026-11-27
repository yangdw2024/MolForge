# MolForge Studio — 视觉与交互设计规范 (DESIGN_SYSTEM)

> 设计理念：**Scientific Precision × Modern Desktop × Premium Minimalism**
> 像高端质谱/量化工作站仪器一样严谨，像 Linear / VS Code 一样高速克制。

## 1. 双主题色彩体系

### 1.1 深色主题：Obsidian Laboratory（默认科研深空黑）
| Token | 色值 | 用途 |
| :--- | :--- | :--- |
| `--bg-primary` | `#0B1220` | 主窗口底色与视口衬底 |
| `--bg-secondary` | `#111B2B` | Navigation Rail、Inspector、Title Bar 与 Status Bar |
| `--bg-panel` | `#172336` | 工作区面板、卡片、弹窗表层 |
| `--bg-elevated` | `#1D2C44` | Hover 行、浮动工具条、菜单弹层 |
| `--border-subtle` | `#26364B` | 1px 精密分割线与控件描边 |
| `--border-strong` | `#364C69` | Focus / 激活控件边界 |
| `--text-primary` | `#F0F4F8` | 标题、数值指标、结构标签 |
| `--text-secondary` | `#9AAFC3` | 轴标签、单位、辅助元信息 |
| `--text-muted` | `#667C94` | 占位符、禁用状态 |
| `--accent-primary` | `#31B7A5` | 品牌主强调色（科研青绿） |
| `--accent-soft` | `rgba(49, 183, 165, 0.14)` | 激活态导航、选中行高亮 |
| `--semantic-info` | `#6BA9ED` | 信息提示与连接态 |
| `--semantic-warning` | `#E5AE60` | 未保存提醒 / 外部引擎待配置提示 |
| `--semantic-error` | `#E57878` | 错误状态与非法化学校验 |

### 1.2 浅色主题：Arctic Laboratory（独立优化极地白）
> 非简单反色；独立调校投影透明度、表格斑马线对比度与 2D/3D 画布明亮模式渲染底色。

| Token | 色值 | 用途 |
| :--- | :--- | :--- |
| `--bg-primary` | `#F5F7FA` | 主窗口工作台底色 |
| `--bg-secondary` | `#EDF2F6` | Title Bar、Navigation Rail、Status Bar |
| `--bg-panel` | `#FFFFFF` | 内容面板、数据表格、弹窗卡片 |
| `--bg-elevated` | `#E4ECF3` | Hover 态、工具按钮激活背景 |
| `--border-subtle` | `#DCE4EB` | 1px 清晰边框 |
| `--border-strong` | `#B8C7D6` | Focus / 分割把手高亮 |
| `--text-primary` | `#172433` | 主文本（高对比度 WCAG AA+） |
| `--text-secondary` | `#657587` | 副文本与说明 |
| `--text-muted` | `#8FA0B2` | 次要标注 |
| `--accent-primary` | `#087F79` | 浅色模式深化科研青绿（确保白底可读性） |
| `--accent-soft` | `rgba(8, 127, 121, 0.10)` | 激活态微底色 |
| `--semantic-info` | `#2563EB` | 信息态 |
| `--semantic-warning` | `#B45309` | 警告态 |
| `--semantic-error` | `#DC2626` | 错误态 |

### 1.3 色盲友好科研图表调色盘（Okabe-Ito 科研校准）
禁止仅依赖颜色区分系列，图表线条与散点须配合实/虚线样式、几何标记符号（圆、方、菱形、三角）及文本标注：
1. 主实验系列：`#31B7A5`（浅色 `#087F79`）— 实线 + 圆形点
2. 对照体系 1 (PM6)：`#56B4E9`（浅色 `#0284C7`）— 长虚线 + 方形点
3. 对照体系 2 (Y6)：`#E69F00`（浅色 `#D97706`）— 点划线 + 三角点
4. 对照体系 3 (ITIC)：`#CC79A7`（浅色 `#9333EA`）— 短点线 + 菱形点
5. 负/空状态提示：`#E57878`（浅色 `#DC2626`）

## 2. 排版、间距与圆角规范

- **中文正文字体**：`"Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", sans-serif`
- **英文界面字体**：`Arial, "Segoe UI", system-ui, sans-serif`
- **数值/SMILES/坐标等宽字体**：`"JetBrains Mono", "Cascadia Code", Consolas, monospace`，配合 `font-variant-numeric: tabular-nums`
- **间距步进**：严格以 **4px / 8px** 为基础单位（紧凑工具按钮 `28px`/`32px` 高，面板内边距 `12px`/`16px`）
- **圆角标准**：容器面板 `8px–12px`；控件/按钮 `6px–8px`；避免夸张的大胶囊圆角与过度留白
- **缩放与视口**：优先保证 `1920×1080` 高密度浏览，同时在 `1280×800` 及 Windows `100% / 125% / 150%` 系统缩放下不截断文字、不溢出横向滚动条

## 3. 克制微动效准则

- 页面与选项卡切换：`150ms–200ms cubic-bezier(0.22, 1, 0.36, 1)`
- 面板折叠与抽屉展开：`180ms–220ms ease-out`
- 按钮交互反馈：`100ms–140ms ease`
- 全面支持 `@media (prefers-reduced-motion: reduce)` 及软件内「减弱动画」开关；禁止持续背景闪烁与无意义旋转
