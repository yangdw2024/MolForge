import React, { useEffect, useRef, useState } from "react";
import {
  Command,
  Minus,
  Moon,
  PanelRight,
  Redo2,
  Save,
  Square,
  Sun,
  Undo2,
  X,
} from "lucide-react";
import { useStudioStore } from "../../store/useStudioStore";
import { molApi } from "../../services/api";

export const MolForgeLogoMark: React.FC<{ size?: number }> = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <polygon
      points="12,2.5 20.2,7.25 20.2,16.75 12,21.5 3.8,16.75 3.8,7.25"
      stroke="var(--accent-primary)"
      strokeWidth="1.9"
      fill="var(--accent-soft)"
    />
    <polygon
      points="12,6.2 16.9,9.05 16.9,14.95 12,17.8 7.1,14.95 7.1,9.05"
      stroke="var(--accent-primary)"
      strokeWidth="1.2"
      strokeDasharray="2.5 2"
      opacity="0.8"
    />
    <circle cx="12" cy="12" r="2.2" fill="var(--accent-primary)" />
  </svg>
);

interface MenuItem {
  id: string;
  label: string;
  shortcut?: string;
  divider?: boolean;
  action?: () => void;
  checked?: boolean;
}

interface MenuDef {
  label: string;
  items: MenuItem[];
}

export const StudioHeader: React.FC = () => {
  const summary = useStudioStore((s) => s.summary);
  const isDirty = useStudioStore((s) => s.isDirty);
  const projectPath = useStudioStore((s) => s.projectPath);
  const theme = useStudioStore((s) => s.theme);
  const inspectorOpen = useStudioStore((s) => s.inspectorOpen);
  const toggleTheme = useStudioStore((s) => s.toggleTheme);
  const setInspectorOpen = useStudioStore((s) => s.setInspectorOpen);
  const setCommandPaletteOpen = useStudioStore((s) => s.setCommandPaletteOpen);
  const saveProject = useStudioStore((s) => s.saveProject);
  const openStructureDialog = useStudioStore((s) => s.openStructureDialog);
  const runTask = useStudioStore((s) => s.runTask);
  const setLayoutMode = useStudioStore((s) => s.setLayoutMode);
  const layoutMode = useStudioStore((s) => s.layoutMode);
  const triggerFitCamera = useStudioStore((s) => s.triggerFitCamera);
  const setReprMode = useStudioStore((s) => s.setReprMode);
  const reprMode = useStudioStore((s) => s.reprMode);
  const showHydrogens = useStudioStore((s) => s.showHydrogens);
  const setShowHydrogens = useStudioStore((s) => s.setShowHydrogens);
  const showAtomIds = useStudioStore((s) => s.showAtomIds);
  const setShowAtomIds = useStudioStore((s) => s.setShowAtomIds);
  const showAxes = useStudioStore((s) => s.showAxes);
  const setShowAxes = useStudioStore((s) => s.setShowAxes);
  const showNavRail = useStudioStore((s) => s.showNavRail);
  const setShowNavRail = useStudioStore((s) => s.setShowNavRail);
  const setPeriodicModalOpen = useStudioStore((s) => s.setPeriodicModalOpen);
  const setRoute = useStudioStore((s) => s.setRoute);
  const setAiDrawerOpen = useStudioStore((s) => s.setAiDrawerOpen);
  const setSelectedIndices = useStudioStore((s) => s.setSelectedIndices);
  const atoms2d = useStudioStore((s) => s.atoms2d);

  const [maximized, setMaximized] = useState(false);
  const [activeMenu, setActiveMenu] = useState<string | null>(null);
  const headerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const api = window.molforgeDesktop;
    if (!api) return;
    void api.windowControls.isMaximized().then(setMaximized);
    return api.onEvent("window:maximized-changed", (val) => {
      setMaximized(Boolean(val));
    });
  }, []);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (headerRef.current && !headerRef.current.contains(e.target as Node)) {
        setActiveMenu(null);
      }
    };
    window.addEventListener("mousedown", onDocClick);
    return () => window.removeEventListener("mousedown", onDocClick);
  }, []);

  const handleExport = async (format: "pdb" | "xyz" | "mol" | "gjf") => {
    const res = await molApi.exportFile(format);
    if (res.ok && res.content) {
      const blob = new Blob([res.content], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = res.filename;
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  const fileLabel = projectPath
    ? projectPath.split(/[\\/]/).pop()
    : summary?.name || "未命名工程";

  const menus: Record<string, MenuDef> = {
    file: {
      label: "文件(F)",
      items: [
        {
          id: "open_file",
          label: "打开结构文件 (PDB, XYZ, MOL, GJF, CIF)...",
          shortcut: "Ctrl+O",
          action: () => void openStructureDialog(),
        },
        {
          id: "save_proj",
          label: "保存工程 (.mforge)",
          shortcut: "Ctrl+S",
          action: () => void saveProject(false),
        },
        {
          id: "save_as",
          label: "另存工程为...",
          shortcut: "Ctrl+Shift+S",
          action: () => void saveProject(true),
        },
        { id: "div1", label: "", divider: true },
        {
          id: "exp_pdb",
          label: "导出为 PDB 标准格式...",
          action: () => void handleExport("pdb"),
        },
        {
          id: "exp_xyz",
          label: "导出为 XYZ 坐标格式...",
          action: () => void handleExport("xyz"),
        },
        {
          id: "exp_mol",
          label: "导出为 MDL MOL V2000...",
          action: () => void handleExport("mol"),
        },
        {
          id: "exp_gjf",
          label: "导出为 Gaussian .gjf 输入文件...",
          action: () => void handleExport("gjf"),
        },
        { id: "div2", label: "", divider: true },
        {
          id: "new_clean",
          label: "清空当前工作台 (新建)",
          action: () => void runTask("清空工作台", () => molApi.buildSmiles("C", "Methane")),
        },
      ],
    },
    edit: {
      label: "编辑(E)",
      items: [
        {
          id: "undo",
          label: "撤销 (Undo)",
          shortcut: "Ctrl+Z",
          action: () => void runTask("撤销", () => molApi.undo()),
        },
        {
          id: "redo",
          label: "重做 (Redo)",
          shortcut: "Ctrl+Y",
          action: () => void runTask("重做", () => molApi.redo()),
        },
        { id: "div1", label: "", divider: true },
        {
          id: "clean_3d",
          label: "3D 力场几何优化 (Force-Field Clean)",
          shortcut: "Ctrl+Shift+K",
          action: () => void runTask("3D 力场优化", () => molApi.clean3D()),
        },
        {
          id: "select_all",
          label: "全选原子 (Select All)",
          shortcut: "Ctrl+A",
          action: () => {
            if (atoms2d) setSelectedIndices(atoms2d.atoms.map((_, i) => i));
          },
        },
        {
          id: "deselect_all",
          label: "取消选择 (Deselect)",
          shortcut: "Esc",
          action: () => setSelectedIndices([]),
        },
        { id: "div2", label: "", divider: true },
        {
          id: "prefs",
          label: "偏好设置 (Preferences)...",
          shortcut: "Ctrl+,",
          action: () => setRoute("settings"),
        },
      ],
    },
    build: {
      label: "构建(B)",
      items: [
        {
          id: "periodic_table",
          label: "完整 118 元素周期表...",
          action: () => setPeriodicModalOpen(true),
        },
        {
          id: "osc_library",
          label: "OSC 砌块与片段库 (Y6 / ITIC / BDT)...",
          action: () => {
            const ev = new CustomEvent("open-hud-layer", { detail: { layer: "fragments" } });
            window.dispatchEvent(ev);
          },
        },
        { id: "div1", label: "", divider: true },
        {
          id: "add_benzene",
          label: "插入苯环 (Benzene, 6-Ar)",
          action: () =>
            void runTask("插入苯环", () =>
              molApi.addRing({ size: 6, aromatic: true })
            ),
        },
        {
          id: "add_thiophene",
          label: "插入噻吩环 (Thiophene, 5-S)",
          action: () =>
            void runTask("插入噻吩环", () =>
              molApi.addRing({ size: 5, aromatic: true, hetero: { 0: 16 } })
            ),
        },
        {
          id: "add_carbazole",
          label: "插入咔唑核心 (Carbazole)",
          action: () =>
            void runTask("插入咔唑核心", () =>
              molApi.insertFragment({ fragment_id: "carbazole" })
            ),
        },
        {
          id: "add_bdt",
          label: "插入 BDT 给体核心",
          action: () =>
            void runTask("插入 BDT 给体", () =>
              molApi.insertFragment({ fragment_id: "bdt" })
            ),
        },
        {
          id: "add_fluorene",
          label: "插入芴单元 (Fluorene)",
          action: () =>
            void runTask("插入芴单元", () =>
              molApi.insertFragment({ fragment_id: "fluorene" })
            ),
        },
      ],
    },
    structure: {
      label: "结构(S)",
      items: [
        {
          id: "coords_table",
          label: "查看与编辑笛卡尔坐标表 (Cartesian Table)...",
          action: () => {
            const ev = new CustomEvent("open-hud-layer", { detail: { layer: "coordinates" } });
            window.dispatchEvent(ev);
          },
        },
        {
          id: "auto_clean",
          label: "构象力场能量弛豫 (RDKit / Builtin)",
          shortcut: "Ctrl+Shift+K",
          action: () => void runTask("3D 构象优化", () => molApi.clean3D()),
        },
        { id: "div1", label: "", divider: true },
        {
          id: "add_hydrogens",
          label: "3D 力场重排坐标 (Clean 3D)",
          action: () => void runTask("3D 力场重排", () => molApi.clean3D()),
        },
      ],
    },
    calc: {
      label: "计算(C)",
      items: [
        {
          id: "calc_setup",
          label: "量子化学计算设置 (Gaussian / ORCA / xTB / CalChem)...",
          action: () => {
            const ev = new CustomEvent("open-hud-layer", { detail: { layer: "calculation" } });
            window.dispatchEvent(ev);
          },
        },
        { id: "div1", label: "", divider: true },
        {
          id: "run_tb",
          label: "实时紧束缚 (Tight-Binding pi-MO 求解)",
          action: () =>
            void runTask("紧束缚求解", async () => {
              const res = await molApi.computeTB();
              const ev = new CustomEvent("open-hud-layer", { detail: { layer: "orbitals", data: res } });
              window.dispatchEvent(ev);
            }),
        },
        {
          id: "run_calchem",
          label: "CalChem 纯 Rust 从头算 (HF / DFT B3LYP)...",
          action: () =>
            void runTask("CalChem 从头算", () =>
              molApi.runCalchem({ method: "B3LYP", basis: "STO-3G", mode: "sp" })
            ),
        },
        {
          id: "run_xtb",
          label: "GFN2-xTB 半经验几何优化...",
          action: () =>
            void runTask("xTB 优化", () =>
              molApi.runXtb({ gfn_level: 2, apply_geometry: true })
            ),
        },
        {
          id: "gromacs_md",
          label: "GROMACS 分子动力学设置 (.mdp 生成)...",
          action: () => setRoute("jobs"),
        },
      ],
    },
    analysis: {
      label: "分析(A)",
      items: [
        {
          id: "orbitals_ladder",
          label: "前线分子轨道能级梯 (HOMO / LUMO Gap)...",
          action: () => {
            const ev = new CustomEvent("open-hud-layer", { detail: { layer: "orbitals" } });
            window.dispatchEvent(ev);
          },
        },
        {
          id: "multiwfn_center",
          label: "Multiwfn 波函数分析面板...",
          action: () => setRoute("analysis"),
        },
        {
          id: "all_analysis",
          label: "全部 79 项分析方法目录...",
          action: () => setRoute("analysis"),
        },
      ],
    },
    results: {
      label: "结果(R)",
      items: [
        {
          id: "jobs_status",
          label: "后台任务与计算队列...",
          action: () => setRoute("jobs"),
        },
        {
          id: "reports_export",
          label: "导出计算报表与数据归档...",
          action: () => setRoute("reports"),
        },
      ],
    },
    view: {
      label: "视图(V)",
      items: [
        {
          id: "toggle_nav",
          label: "显隐侧边主导航栏",
          shortcut: "Ctrl+B",
          checked: showNavRail,
          action: () => setShowNavRail(!showNavRail),
        },
        { id: "div0", label: "", divider: true },
        {
          id: "view_split",
          label: "2D + 3D 联动分屏",
          checked: layoutMode === "split",
          action: () => setLayoutMode("split"),
        },
        {
          id: "view_3d",
          label: "仅 3D 视口 (100% 空间)",
          checked: layoutMode === "3d",
          action: () => setLayoutMode("3d"),
        },
        {
          id: "view_2d",
          label: "仅 2D 画布 (100% 空间)",
          checked: layoutMode === "2d",
          action: () => setLayoutMode("2d"),
        },
        { id: "div1", label: "", divider: true },
        {
          id: "fit_cam",
          label: "重置视角 / 居中适应",
          shortcut: "Shift+F",
          action: () => triggerFitCamera(),
        },
        {
          id: "repr_ball",
          label: "球棍模型 (Ball & Stick)",
          checked: reprMode === "ball_stick",
          action: () => setReprMode("ball_stick"),
        },
        {
          id: "repr_cpk",
          label: "CPK 空间填充模型 (Spacefill)",
          checked: reprMode === "cpk",
          action: () => setReprMode("cpk"),
        },
        {
          id: "repr_wire",
          label: "线框模型 (Wireframe)",
          checked: reprMode === "wireframe",
          action: () => setReprMode("wireframe"),
        },
        { id: "div2", label: "", divider: true },
        {
          id: "toggle_h",
          label: "显示显式氢 (Hydrogens)",
          shortcut: "H",
          checked: showHydrogens,
          action: () => setShowHydrogens(!showHydrogens),
        },
        {
          id: "toggle_ids",
          label: "显示原子序号 (#ID)",
          checked: showAtomIds,
          action: () => setShowAtomIds(!showAtomIds),
        },
        {
          id: "toggle_axes",
          label: "显示空间坐标轴 (XYZ)",
          checked: showAxes,
          action: () => setShowAxes(!showAxes),
        },
      ],
    },
    layers: {
      label: "图层(L)",
      items: [
        {
          id: "layer_inspector",
          label: "属性与几何测量面板",
          checked: inspectorOpen,
          action: () => {
            setAiDrawerOpen(false);
            setInspectorOpen(!inspectorOpen);
          },
        },
        {
          id: "layer_copilot",
          label: "AI 科研副驾驶 HUD",
          action: () => {
            const ev = new CustomEvent("open-hud-layer", { detail: { layer: "ai_copilot" } });
            window.dispatchEvent(ev);
          },
        },
        {
          id: "layer_fragments",
          label: "砌块与片段库 HUD",
          action: () => {
            const ev = new CustomEvent("open-hud-layer", { detail: { layer: "fragments" } });
            window.dispatchEvent(ev);
          },
        },
        {
          id: "layer_coordinates",
          label: "笛卡尔坐标表 HUD",
          action: () => {
            const ev = new CustomEvent("open-hud-layer", { detail: { layer: "coordinates" } });
            window.dispatchEvent(ev);
          },
        },
        {
          id: "layer_calc",
          label: "量化计算设置 HUD",
          action: () => {
            const ev = new CustomEvent("open-hud-layer", { detail: { layer: "calculation" } });
            window.dispatchEvent(ev);
          },
        },
        {
          id: "layer_orbitals",
          label: "轨道能级阶梯 HUD",
          action: () => {
            const ev = new CustomEvent("open-hud-layer", { detail: { layer: "orbitals" } });
            window.dispatchEvent(ev);
          },
        },
      ],
    },
    help: {
      label: "帮助(H)",
      items: [
        {
          id: "cmd_palette",
          label: "全局命令搜索与快捷键 (Command Palette)...",
          shortcut: "Ctrl+K",
          action: () => setCommandPaletteOpen(true),
        },
        {
          id: "hub_open",
          label: "打开 MolForge Hub 技能与扩展市场...",
          action: () => setRoute("hub"),
        },
        { id: "div1", label: "", divider: true },
        {
          id: "about",
          label: "关于 MolForge Studio 8.1...",
          action: () => {
            window.alert(
              "MolForge Studio 8.1.0\nAI 原生计算化学工作台 (AI-Native Scientific Workbench)\nWebGPU 60FPS 渲染 · Rust 核心 · Multiwfn / Gaussian / ORCA / xTB 原生适配"
            );
          },
        },
      ],
    },
  };

  const handleMinimize = () => window.molforgeDesktop?.windowControls.minimize();
  const handleToggleMaximize = () => window.molforgeDesktop?.windowControls.toggleMaximize();
  const handleClose = () => window.molforgeDesktop?.windowControls.close();

  return (
    <header
      ref={headerRef}
      data-testid="title-bar"
      className="app-drag h-[38px] shrink-0 px-2 flex items-center justify-between border-b select-none z-40 relative backdrop-blur-xl"
      style={{
        backgroundColor: "var(--bg-secondary)",
        borderColor: "var(--border-subtle)",
      }}
    >
      {/* Left: Brand + 10 Menus */}
      <div className="flex items-center gap-1 min-w-0">
        <div className="flex items-center gap-2 shrink-0 pr-2 mr-1 border-r border-[var(--border-subtle)]">
          <MolForgeLogoMark size={17} />
          <span className="font-semibold text-[12.5px] tracking-tight hidden sm:inline" style={{ color: "var(--text-primary)" }}>
            MolForge
          </span>
        </div>

        {/* 10 Dropdown Menus */}
        <div className="app-no-drag flex items-center">
          {Object.entries(menus).map(([key, menu]) => {
            const isOpen = activeMenu === key;
            return (
              <div key={key} className="relative">
                <button
                  type="button"
                  onClick={() => setActiveMenu(isOpen ? null : key)}
                  onMouseEnter={() => {
                    if (activeMenu !== null) setActiveMenu(key);
                  }}
                  className="px-2 py-1 rounded cursor-pointer transition-colors text-[11px] font-medium"
                  style={{
                    backgroundColor: isOpen ? "var(--bg-tertiary)" : "transparent",
                    color: isOpen ? "var(--accent-primary)" : "var(--text-secondary)",
                  }}
                >
                  {menu.label}
                </button>

                {isOpen && (
                  <div
                    className="absolute top-full left-0 mt-0.5 min-w-[240px] py-1 rounded-xl border shadow-2xl backdrop-blur-2xl z-50 animate-in fade-in zoom-in-95 duration-100"
                    style={{
                      backgroundColor: "color-mix(in srgb, var(--bg-secondary) 95%, transparent)",
                      borderColor: "var(--border-subtle)",
                      boxShadow: "0 18px 48px rgba(0, 0, 0, 0.45)",
                    }}
                  >
                    {menu.items.map((item) => {
                      if (item.divider) {
                        return (
                          <div
                            key={item.id}
                            className="my-1 border-t"
                            style={{ borderColor: "var(--border-subtle)" }}
                          />
                        );
                      }
                      return (
                        <button
                          key={item.id}
                          type="button"
                          onClick={() => {
                            setActiveMenu(null);
                            item.action?.();
                          }}
                          className="w-full h-7 px-3 flex items-center justify-between text-left hover:bg-[var(--bg-tertiary)] cursor-pointer text-[11.5px] transition-colors"
                          style={{ color: "var(--text-primary)" }}
                        >
                          <div className="flex items-center gap-2">
                            {item.checked !== undefined ? (
                              <span className="w-3 text-center text-[10px] text-[var(--accent-primary)] font-bold">
                                {item.checked ? "✓" : ""}
                              </span>
                            ) : null}
                            <span>{item.label}</span>
                          </div>
                          {item.shortcut && (
                            <span
                              className="mono-num text-[10px] ml-4 opacity-60"
                              style={{ color: "var(--text-muted)" }}
                            >
                              {item.shortcut}
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Center: Active Molecule & Global Command Palette */}
      <div className="app-no-drag flex items-center gap-2 mx-2 flex-1 max-w-[420px] justify-center min-w-0">
        <div
          className="hidden xl:flex items-center gap-1.5 px-2 py-0.5 rounded-lg border text-[11px] truncate shrink-0"
          style={{ backgroundColor: "var(--bg-panel)", borderColor: "var(--border-subtle)" }}
        >
          <span className="font-medium truncate max-w-[110px]" style={{ color: "var(--text-primary)" }} title={fileLabel}>
            {fileLabel}
          </span>
          {summary?.formula && (
            <span className="mono-num font-semibold text-[10px] px-1 rounded" style={{ backgroundColor: "var(--accent-soft)", color: "var(--accent-primary)" }}>
              {summary.formula}
            </span>
          )}
          <span
            className="w-1.5 h-1.5 rounded-full inline-block shrink-0"
            style={{ backgroundColor: isDirty ? "var(--semantic-warning)" : "var(--accent-primary)" }}
            title={isDirty ? "有未保存更改 (Ctrl+S)" : "已同步"}
          />
        </div>

        <button
          type="button"
          data-testid="command-palette-trigger"
          onClick={() => setCommandPaletteOpen(true)}
          className="w-full h-7 px-2.5 rounded-lg flex items-center justify-between text-[11.5px] cursor-pointer transition-colors"
          style={{
            backgroundColor: "var(--bg-input)",
            border: "1px solid var(--border-subtle)",
            color: "var(--text-secondary)",
          }}
        >
          <span className="flex items-center gap-1.5 truncate">
            <Command size={12} style={{ color: "var(--accent-primary)" }} />
            <span className="truncate">检索分子、分析、命令...</span>
          </span>
          <kbd className="mono-num text-[9.5px] px-1 py-0.2 rounded" style={{ backgroundColor: "var(--bg-panel)", border: "1px solid var(--border-subtle)", color: "var(--text-muted)" }}>
            Ctrl+K
          </kbd>
        </button>
      </div>

      {/* Right: Quick Tools, Theme & Native Window Controls */}
      <div className="app-no-drag flex items-center gap-1 shrink-0">
        <div className="hidden lg:flex items-center gap-0.5 mr-1 pr-1 border-r border-[var(--border-subtle)]">
          <button
            type="button"
            className="studio-btn !h-7 !px-1.5"
            disabled={!summary?.can_undo}
            onClick={() => void runTask("撤销", () => molApi.undo())}
            title="撤销 (Ctrl+Z)"
          >
            <Undo2 size={12.5} />
          </button>
          <button
            type="button"
            className="studio-btn !h-7 !px-1.5"
            disabled={!summary?.can_redo}
            onClick={() => void runTask("重做", () => molApi.redo())}
            title="重做 (Ctrl+Y)"
          >
            <Redo2 size={12.5} />
          </button>
          <button
            type="button"
            className="studio-btn !h-7 !px-2"
            onClick={() => void saveProject(false)}
            title="保存 .mforge 工程 (Ctrl+S)"
          >
            <Save size={12.5} />
            <span className="hidden 2xl:inline text-[11px]">保存</span>
          </button>
        </div>

        <button
          type="button"
          data-testid="theme-toggle-btn"
          className="studio-btn !h-7 !px-2"
          onClick={toggleTheme}
          title={theme === "obsidian" ? "切换至 Arctic 浅色" : "切换至 Obsidian 深色"}
        >
          {theme === "obsidian" ? <Sun size={12.5} /> : <Moon size={12.5} />}
          <span className="hidden xl:inline text-[11px]">
            {theme === "obsidian" ? "浅色" : "深色"}
          </span>
        </button>

        <button
          type="button"
          className="studio-btn !h-7 !px-2"
          onClick={() => setInspectorOpen(!inspectorOpen)}
          title="显隐属性检查器 (Alt+I)"
          style={inspectorOpen ? { borderColor: "var(--accent-primary)", color: "var(--accent-primary)" } : undefined}
        >
          <PanelRight size={12.5} />
        </button>

        {/* Window Controls */}
        <div className="flex items-center ml-1">
          <button
            type="button"
            onClick={handleMinimize}
            className="w-7 h-7 flex items-center justify-center hover:bg-black/5 dark:hover:bg-white/10 rounded cursor-pointer transition-colors"
            style={{ color: "var(--text-secondary)" }}
            title="最小化"
          >
            <Minus size={12} />
          </button>
          <button
            type="button"
            onClick={handleToggleMaximize}
            className="w-7 h-7 flex items-center justify-center hover:bg-black/5 dark:hover:bg-white/10 rounded cursor-pointer transition-colors"
            style={{ color: "var(--text-secondary)" }}
            title={maximized ? "还原" : "最大化"}
          >
            <Square size={10} />
          </button>
          <button
            type="button"
            onClick={handleClose}
            className="w-7 h-7 flex items-center justify-center hover:bg-[var(--semantic-error)] hover:text-white rounded cursor-pointer transition-colors"
            style={{ color: "var(--text-secondary)" }}
            title="关闭窗口"
          >
            <X size={12} />
          </button>
        </div>
      </div>
    </header>
  );
};
