import React, { useEffect, useRef, useState } from "react";
import { useStudioStore } from "../../store/useStudioStore";
import { molApi } from "../../services/api";

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

export const MenuBar: React.FC = () => {
  const [activeMenu, setActiveMenu] = useState<string | null>(null);
  const barRef = useRef<HTMLDivElement | null>(null);

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
  const setCommandPaletteOpen = useStudioStore((s) => s.setCommandPaletteOpen);
  const setAiDrawerOpen = useStudioStore((s) => s.setAiDrawerOpen);
  const setInspectorOpen = useStudioStore((s) => s.setInspectorOpen);
  const inspectorOpen = useStudioStore((s) => s.inspectorOpen);
  const setSelectedIndices = useStudioStore((s) => s.setSelectedIndices);
  const atoms2d = useStudioStore((s) => s.atoms2d);

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

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (barRef.current && !barRef.current.contains(e.target as Node)) {
        setActiveMenu(null);
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setActiveMenu(null);
    };
    window.addEventListener("mousedown", onDocClick);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("mousedown", onDocClick);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  const menus: Record<string, MenuDef> = {
    file: {
      label: "文件(F)",
      items: [
        {
          id: "new_mol",
          label: "新建分子 (空工程)",
          shortcut: "Ctrl+N",
          action: () => void runTask("新建分子", () => molApi.loadPreset("methane")),
        },
        {
          id: "open",
          label: "打开分子文件...",
          shortcut: "Ctrl+O",
          action: () => void openStructureDialog(),
        },
        {
          id: "save",
          label: "保存项目 (.mforge)",
          shortcut: "Ctrl+S",
          action: () => void saveProject(false),
        },
        {
          id: "save_as",
          label: "另存为...",
          shortcut: "Ctrl+Shift+S",
          action: () => void saveProject(true),
        },
        { id: "div1", label: "", divider: true },
        {
          id: "export_xyz",
          label: "导出 XYZ 坐标 (.xyz)",
          action: () => void handleExport("xyz"),
        },
        {
          id: "export_mol",
          label: "导出 MDL Molfile (.mol)",
          action: () => void handleExport("mol"),
        },
        {
          id: "export_pdb",
          label: "导出 Protein Data Bank (.pdb)",
          action: () => void handleExport("pdb"),
        },
        {
          id: "export_gjf",
          label: "导出 Gaussian 输入 (.gjf)",
          action: () => void handleExport("gjf"),
        },
        { id: "div2", label: "", divider: true },
        {
          id: "exit",
          label: "退出 MolForge Studio",
          shortcut: "Alt+F4",
          action: () => window.close(),
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
          label: "3D 力场几何优化 (MMFF94 / UFF)",
          shortcut: "Ctrl+Shift+O",
          action: () => void runTask("3D 力场优化", () => molApi.clean3D()),
        },
        {
          id: "select_all",
          label: "全选原子",
          shortcut: "Ctrl+A",
          action: () => {
            if (atoms2d?.atoms) {
              setSelectedIndices(atoms2d.atoms.map((a) => a.index));
            }
          },
        },
        {
          id: "clear_selection",
          label: "清除选择",
          shortcut: "Esc",
          action: () => setSelectedIndices([]),
        },
        { id: "div2", label: "", divider: true },
        {
          id: "prefs",
          label: "首选项 / 设置 (Preferences)...",
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
          label: "插入 BDT 给体核心 (Benzo[1,2-b:4,5-b']dithiophene)",
          action: () =>
            void runTask("插入 BDT 核心", () =>
              molApi.insertFragment({ fragment_id: "bdt" })
            ),
        },
        { id: "div2", label: "", divider: true },
        {
          id: "attach_methyl",
          label: "接枝甲基 (-CH3)",
          action: () =>
            void runTask("接枝甲基", () =>
              molApi.insertFragment({ fragment_id: "methyl" })
            ),
        },
        {
          id: "attach_hydroxyl",
          label: "接枝羟基 (-OH)",
          action: () =>
            void runTask("接枝羟基", () =>
              molApi.insertFragment({ fragment_id: "hydroxyl" })
            ),
        },
        {
          id: "attach_carboxyl",
          label: "接枝羧基 (-COOH)",
          action: () =>
            void runTask("接枝羧基", () =>
              molApi.insertFragment({ fragment_id: "carboxyl" })
            ),
        },
      ],
    },
    structure: {
      label: "结构(S)",
      items: [
        {
          id: "coord_table",
          label: "笛卡尔坐标表 (Cartesian Coordinates)...",
          action: () => {
            const ev = new CustomEvent("open-hud-layer", { detail: { layer: "coordinates" } });
            window.dispatchEvent(ev);
          },
        },
        {
          id: "geom_measure",
          label: "空间几何测量 (键长 / 键角 / 二面角)",
          action: () => {
            setInspectorOpen(true);
            setAiDrawerOpen(false);
          },
        },
        { id: "div1", label: "", divider: true },
        {
          id: "center_mol",
          label: "分子居中 (Center to Origin)",
          action: () => triggerFitCamera(),
        },
      ],
    },
    calculate: {
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
    results: {
      label: "结果(R)",
      items: [
        {
          id: "orbital_ladder",
          label: "前线分子轨道能级阶梯 (HOMO/LUMO Ladder)...",
          action: () => {
            const ev = new CustomEvent("open-hud-layer", { detail: { layer: "orbitals" } });
            window.dispatchEvent(ev);
          },
        },
        {
          id: "analysis_catalog",
          label: "79 项科学分析全景浏览器 (Results Matrix)...",
          action: () => setRoute("analysis"),
        },
        {
          id: "hub_workflows",
          label: "MolForge Hub 科研工作流中心...",
          action: () => setRoute("hub"),
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
          shortcut: "F",
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
          label: "属性与几何测量 HUD",
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
          action: () => alert("MolForge Studio 8.1\n\nAI 原生科学工作台 · 零 Python 原生 Rust 内核 + WebGPU 渲染\n集成分子建模、高精度量化计算、OSC 有机光伏材料设计与自动化科研技能。"),
        },
      ],
    },
  };

  return (
    <div
      ref={barRef}
      data-testid="desktop-menubar"
      className="relative z-40 flex items-center h-7 px-2 border-b select-none text-[12px] font-sans"
      style={{
        backgroundColor: "var(--bg-secondary)",
        borderColor: "var(--border-subtle)",
        color: "var(--text-primary)",
      }}
    >
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
              className="px-2.5 py-1 rounded cursor-pointer transition-colors text-[11.5px] font-medium"
              style={{
                backgroundColor: isOpen ? "var(--bg-tertiary)" : "transparent",
                color: isOpen ? "var(--accent-primary)" : "var(--text-secondary)",
              }}
            >
              {menu.label}
            </button>

            {isOpen && (
              <div
                className="absolute top-full left-0 mt-0.5 min-w-[240px] py-1 rounded-lg border shadow-2xl backdrop-blur-2xl z-50 animate-in fade-in zoom-in-95 duration-100"
                style={{
                  backgroundColor: "color-mix(in srgb, var(--bg-secondary) 94%, transparent)",
                  borderColor: "var(--border-subtle)",
                  boxShadow: "0 14px 40px rgba(0, 0, 0, 0.45)",
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
                      className="w-full h-7 px-3 flex items-center justify-between text-left hover:bg-[var(--bg-tertiary)] cursor-pointer text-[12px] transition-colors"
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
                          className="mono-num text-[10.5px] ml-4 opacity-60"
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
  );
};
