import React, { useState } from "react";
import {
  ChevronRight,
  Compass,
  Eraser,
  Hexagon,
  Link2,
  MousePointer2,
  Puzzle,
  Sparkles,
} from "lucide-react";
import type { EditTool, ElementInfo, FragmentInfo, RingTemplateSpec } from "../../types/studio";

interface ChemicalToolRailProps {
  activeTool: EditTool;
  setActiveTool: (tool: EditTool) => void;
  activeElementZ: number;
  setActiveElementZ: (z: number) => void;
  activeRing: RingTemplateSpec;
  setActiveRing: (ring: RingTemplateSpec) => void;
  activeFragmentId: string;
  setActiveFragmentId: (id: string) => void;
  elements: ElementInfo[];
  fragments: FragmentInfo[];
  ringTemplates: RingTemplateSpec[];
  onOpenPeriodicTable: () => void;
  onClean3D: () => void;
  isCleaning?: boolean;
}

const QUICK_ELEMENTS = [
  { z: 6, sym: "C", color: "#94A3B8", name: "碳" },
  { z: 7, sym: "N", color: "#60A5FA", name: "氮" },
  { z: 8, sym: "O", color: "#F87171", name: "氧" },
  { z: 16, sym: "S", color: "#FACC15", name: "硫" },
  { z: 15, sym: "P", color: "#F59E0B", name: "磷" },
  { z: 9, sym: "F", color: "#4ADE80", name: "氟" },
  { z: 17, sym: "Cl", color: "#34D399", name: "氯" },
  { z: 35, sym: "Br", color: "#FB923C", name: "溴" },
  { z: 53, sym: "I", color: "#C084FC", name: "碘" },
  { z: 5, sym: "B", color: "#F472B6", name: "硼" },
  { z: 1, sym: "H", color: "#CBD5E1", name: "氢" },
];

export const ChemicalToolRail: React.FC<ChemicalToolRailProps> = ({
  activeTool,
  setActiveTool,
  activeElementZ,
  setActiveElementZ,
  activeRing,
  setActiveRing,
  activeFragmentId,
  setActiveFragmentId,
  elements,
  fragments,
  ringTemplates,
  onOpenPeriodicTable,
  onClean3D,
  isCleaning = false,
}) => {
  const [openDrawer, setOpenDrawer] = useState<"atom" | "ring" | "fragment" | null>(null);

  const activeEl = elements.find((e) => e.atomic_number === activeElementZ) || {
    symbol: "C",
    name_cn: "碳",
    hex_color: "#94A3B8",
  };

  const handleToolClick = (tool: EditTool) => {
    setActiveTool(tool);
    if (tool === "atom") setOpenDrawer((prev) => (prev === "atom" ? null : "atom"));
    else if (tool === "ring") setOpenDrawer((prev) => (prev === "ring" ? null : "ring"));
    else if (tool === "fragment") setOpenDrawer((prev) => (prev === "fragment" ? null : "fragment"));
    else setOpenDrawer(null);
  };

  return (
    <aside
      data-testid="chemical-tool-rail"
      className="absolute top-12 left-2.5 z-30 flex flex-col items-center py-2 px-1 rounded-2xl border backdrop-blur-2xl select-none"
      style={{
        backgroundColor: "color-mix(in srgb, var(--bg-secondary) 88%, transparent)",
        borderColor: "var(--border-subtle)",
        boxShadow: "0 14px 40px rgba(0, 0, 0, 0.4)",
        width: 44,
      }}
    >
      <div className="flex flex-col gap-1 w-full items-center">
        {/* 1. Select / Pick (V) */}
        <button
          type="button"
          onClick={() => handleToolClick("select")}
          className="w-9 h-9 rounded-xl flex items-center justify-center cursor-pointer transition-colors relative"
          style={{
            backgroundColor: activeTool === "select" ? "var(--accent-soft)" : "transparent",
            color: activeTool === "select" ? "var(--accent-primary)" : "var(--text-secondary)",
          }}
          title="选择与拖拽 (V) — 单击选择原子/键，Shift 多选，框选"
        >
          <MousePointer2 size={16} />
        </button>

        {/* 2. Atom / Element (A) */}
        <div className="relative">
          <button
            type="button"
            onClick={() => handleToolClick("atom")}
            className="w-9 h-9 rounded-xl flex flex-col items-center justify-center cursor-pointer transition-colors relative"
            style={{
              backgroundColor: activeTool === "atom" ? "var(--accent-soft)" : "transparent",
              color: activeTool === "atom" ? "var(--accent-primary)" : "var(--text-secondary)",
            }}
            title={`原子工具 (A) — 当前元素: #${activeElementZ} ${activeEl.symbol} (${activeEl.name_cn})，点击展开元素库`}
          >
            <span
              data-testid="active-element-badge"
              className="font-bold text-[13px] leading-none"
              style={{
                color: activeTool === "atom" ? "var(--accent-primary)" : activeEl.hex_color,
                filter: "drop-shadow(0 1px 1px rgba(0,0,0,0.25))",
              }}
            >
              {activeEl.symbol}
            </span>
            <span className="mono-num text-[8px] opacity-70 mt-0.5">#{activeElementZ}</span>
          </button>

          {/* Atom Flyout Drawer */}
          {openDrawer === "atom" && (
            <div
              className="absolute left-11 top-0 z-50 w-56 p-2 rounded-2xl border shadow-2xl backdrop-blur-2xl animate-in fade-in zoom-in-95 duration-100"
              style={{
                backgroundColor: "color-mix(in srgb, var(--bg-secondary) 96%, transparent)",
                borderColor: "var(--border-subtle)",
                boxShadow: "0 18px 48px rgba(0,0,0,0.5)",
              }}
            >
              <div className="text-[11px] font-semibold text-[var(--text-muted)] mb-1.5 px-1 flex items-center justify-between">
                <span>常用元素速选</span>
                <span className="mono-num text-[10px] text-[var(--accent-primary)] font-bold">
                  #{activeElementZ} {activeEl.symbol}
                </span>
              </div>
              <div className="grid grid-cols-4 gap-1">
                {QUICK_ELEMENTS.map((el) => {
                  const isCurrent = activeElementZ === el.z;
                  return (
                    <button
                      key={el.z}
                      type="button"
                      onClick={() => {
                        setActiveElementZ(el.z);
                        setActiveTool("atom");
                        setOpenDrawer(null);
                      }}
                      className="h-8 rounded-lg flex flex-col items-center justify-center cursor-pointer transition-colors"
                      style={{
                        backgroundColor: isCurrent ? "var(--accent-soft)" : "var(--bg-primary)",
                        border: `1px solid ${isCurrent ? "var(--accent-primary)" : "var(--border-subtle)"}`,
                      }}
                      title={`${el.name} (Z=${el.z})`}
                    >
                      <span className="font-bold text-[12px] leading-none" style={{ color: el.color }}>
                        {el.sym}
                      </span>
                      <span className="mono-num text-[8.5px] text-[var(--text-muted)] mt-0.5">{el.z}</span>
                    </button>
                  );
                })}
              </div>

              <div className="my-1.5 border-t border-[var(--border-subtle)]" />

              <button
                type="button"
                onClick={() => {
                  onOpenPeriodicTable();
                  setOpenDrawer(null);
                }}
                className="studio-btn w-full !h-7 !text-[11px] flex items-center justify-center gap-1.5"
              >
                <Compass size={12} style={{ color: "var(--accent-primary)" }} />
                <span>完整 118 元素周期表...</span>
              </button>
            </div>
          )}
        </div>

        {/* 2b. 118 Periodic Table Quick Button */}
        <button
          type="button"
          data-testid="open-pt-modal-btn"
          onClick={() => {
            setOpenDrawer(null);
            onOpenPeriodicTable();
          }}
          className="w-9 h-9 rounded-xl flex items-center justify-center cursor-pointer transition-colors hover:bg-[var(--bg-tertiary)]"
          style={{ color: "var(--text-secondary)" }}
          title="完整 118 元素周期表 (Periodic Table)"
        >
          <Compass size={16} />
        </button>

        {/* 3. Bond (B) */}
        <button
          type="button"
          onClick={() => handleToolClick("bond")}
          className="w-9 h-9 rounded-xl flex items-center justify-center cursor-pointer transition-colors"
          style={{
            backgroundColor: activeTool === "bond" ? "var(--accent-soft)" : "transparent",
            color: activeTool === "bond" ? "var(--accent-primary)" : "var(--text-secondary)",
          }}
          title="建键工具 (B) — 先后点击两原子建键，或点击已有键切换键级"
        >
          <Link2 size={16} />
        </button>

        {/* 4. Ring Templates (R) */}
        <div className="relative">
          <button
            type="button"
            onClick={() => handleToolClick("ring")}
            className="w-9 h-9 rounded-xl flex items-center justify-center cursor-pointer transition-colors"
            style={{
              backgroundColor: activeTool === "ring" ? "var(--accent-soft)" : "transparent",
              color: activeTool === "ring" ? "var(--accent-primary)" : "var(--text-secondary)",
            }}
            title={`环系模板 (R) — 当前: ${activeRing.label}，点击展开环库`}
          >
            <Hexagon size={16} />
          </button>

          {/* Ring Flyout Drawer */}
          {openDrawer === "ring" && (
            <div
              className="absolute left-11 top-0 z-50 w-52 p-2 rounded-2xl border shadow-2xl backdrop-blur-2xl animate-in fade-in zoom-in-95 duration-100"
              style={{
                backgroundColor: "color-mix(in srgb, var(--bg-secondary) 96%, transparent)",
                borderColor: "var(--border-subtle)",
                boxShadow: "0 18px 48px rgba(0,0,0,0.5)",
              }}
            >
              <div className="text-[11px] font-semibold text-[var(--text-muted)] mb-1.5 px-1">常用环系模板</div>
              <div className="space-y-1">
                {ringTemplates.map((r) => {
                  const isCur = activeRing.id === r.id;
                  return (
                    <button
                      key={r.id}
                      type="button"
                      onClick={() => {
                        setActiveRing(r);
                        setActiveTool("ring");
                        setOpenDrawer(null);
                      }}
                      className="w-full h-7 px-2 rounded-lg text-left text-[11.5px] flex items-center justify-between cursor-pointer transition-colors"
                      style={{
                        backgroundColor: isCur ? "var(--accent-soft)" : "transparent",
                        color: isCur ? "var(--accent-primary)" : "var(--text-primary)",
                      }}
                    >
                      <span className="truncate">{r.label}</span>
                      {isCur && <ChevronRight size={12} />}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* 5. Fragments & OSC Blocks (F) */}
        <div className="relative">
          <button
            type="button"
            onClick={() => handleToolClick("fragment")}
            className="w-9 h-9 rounded-xl flex items-center justify-center cursor-pointer transition-colors"
            style={{
              backgroundColor: activeTool === "fragment" ? "var(--accent-soft)" : "transparent",
              color: activeTool === "fragment" ? "var(--accent-primary)" : "var(--text-secondary)",
            }}
            title="化学片段与 OSC 砌块 (F) — 点击原子接枝，点击展开砌块库"
          >
            <Puzzle size={16} />
          </button>

          {/* Fragment Flyout Drawer */}
          {openDrawer === "fragment" && (
            <div
              className="absolute left-11 top-0 z-50 w-64 p-2 rounded-2xl border shadow-2xl backdrop-blur-2xl animate-in fade-in zoom-in-95 duration-100"
              style={{
                backgroundColor: "color-mix(in srgb, var(--bg-secondary) 96%, transparent)",
                borderColor: "var(--border-subtle)",
                boxShadow: "0 18px 48px rgba(0,0,0,0.5)",
              }}
            >
              <div className="text-[11px] font-semibold text-[var(--text-muted)] mb-1.5 px-1 flex items-center justify-between">
                <span>3D 片段与 OSC 砌块</span>
                <span className="mono-num text-[10px] text-[var(--accent-primary)] font-semibold">
                  共 {fragments.length} 个
                </span>
              </div>
              <div className="space-y-0.5 max-h-60 overflow-y-auto studio-scroll pr-1">
                {fragments.map((frag) => {
                  const isCur = activeFragmentId === frag.id;
                  return (
                    <button
                      key={frag.id}
                      type="button"
                      onClick={() => {
                        setActiveFragmentId(frag.id);
                        setActiveTool("fragment");
                        setOpenDrawer(null);
                      }}
                      className="w-full h-7 px-2 rounded-lg text-left text-[11px] flex items-center justify-between cursor-pointer transition-colors"
                      style={{
                        backgroundColor: isCur ? "var(--accent-soft)" : "transparent",
                        color: isCur ? "var(--accent-primary)" : "var(--text-primary)",
                      }}
                    >
                      <span className="truncate">{frag.name_cn}</span>
                      <span className="mono-num text-[9.5px] opacity-60">{frag.num_atoms}a</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        <div className="w-5 my-1 border-t border-[var(--border-subtle)]" />

        {/* 6. Clean 3D (C) */}
        <button
          type="button"
          onClick={onClean3D}
          disabled={isCleaning}
          className="w-9 h-9 rounded-xl flex items-center justify-center cursor-pointer transition-colors"
          style={{
            color: "var(--accent-primary)",
          }}
          title="3D 力场优化 (Clean 3D) — RDKit / 纯 Rust 构象能量弛豫"
        >
          <Sparkles size={16} className={isCleaning ? "animate-spin" : ""} />
        </button>

        {/* 7. Erase (E) */}
        <button
          type="button"
          onClick={() => handleToolClick("erase")}
          className="w-9 h-9 rounded-xl flex items-center justify-center cursor-pointer transition-colors"
          style={{
            backgroundColor: activeTool === "erase" ? "var(--semantic-error-soft)" : "transparent",
            color: activeTool === "erase" ? "var(--semantic-error)" : "var(--text-secondary)",
          }}
          title="橡皮擦 (E) — 点击原子或化学键删除"
        >
          <Eraser size={16} />
        </button>
      </div>
    </aside>
  );
};
