import React, { useMemo, useState } from "react";
import { Atom, Search, X } from "lucide-react";
import type { ElementInfo } from "../types/molforge";

interface Props {
  open: boolean;
  onClose: () => void;
  elements: ElementInfo[];
  activeElementZ: number;
  selectedAtomCount: number;
  onSelectElement: (z: number, replaceSelected?: boolean) => void;
}

export const PeriodicTableModal: React.FC<Props> = ({
  open,
  onClose,
  elements,
  activeElementZ,
  selectedAtomCount,
  onSelectElement,
}) => {
  const [query, setQuery] = useState("");
  const [hovered, setHovered] = useState<ElementInfo | null>(null);
  const [replaceSelected, setReplaceSelected] = useState(false);

  const byZ = useMemo(() => {
    const map = new Map<number, ElementInfo>();
    for (const el of elements) map.set(el.atomic_number, el);
    return map;
  }, [elements]);

  if (!open) return null;

  const q = query.trim().toLowerCase();
  const matches = (el: ElementInfo) =>
    !q ||
    el.symbol.toLowerCase().includes(q) ||
    el.name.toLowerCase().includes(q) ||
    el.name_cn.includes(q) ||
    el.category.toLowerCase().includes(q) ||
    String(el.atomic_number) === q;

  const currentInfo = hovered || byZ.get(activeElementZ) || elements[5];

  // Build 18-column grid slots for main table (periods 1..7, excluding 57..71 & 89..103)
  const mainCells: Array<{ row: number; col: number; el?: ElementInfo; placeholder?: string }> = [];
  for (const el of elements) {
    if ((el.atomic_number >= 57 && el.atomic_number <= 71) || (el.atomic_number >= 89 && el.atomic_number <= 103)) {
      continue;
    }
    mainCells.push({ row: el.period, col: el.group, el });
  }
  mainCells.push({ row: 6, col: 3, placeholder: "57–71" });
  mainCells.push({ row: 7, col: 3, placeholder: "89–103" });

  const renderTile = (el: ElementInfo) => {
    const isMatched = matches(el);
    const isActive = el.atomic_number === activeElementZ;
    return (
      <button
        key={el.atomic_number}
        onMouseEnter={() => setHovered(el)}
        onClick={() => {
          onSelectElement(el.atomic_number, replaceSelected && selectedAtomCount > 0);
          onClose();
        }}
        className="rounded-lg p-1 flex flex-col items-center justify-center cursor-pointer transition-transform hover:scale-105"
        style={{
          background: el.hex_color,
          color: el.text_color,
          opacity: isMatched ? 1 : 0.16,
          outline: isActive ? "2.5px solid #5eead4" : "1px solid rgba(255,255,255,0.16)",
          minHeight: 46,
        }}
        title={`${el.name_cn} (${el.name}) · Z=${el.atomic_number}`}
      >
        <span className="text-[9px] leading-none opacity-80 mono-num">{el.atomic_number}</span>
        <span className="text-xs font-bold leading-tight">{el.symbol}</span>
        <span className="text-[8px] leading-none opacity-80 truncate max-w-full">{el.name_cn}</span>
      </button>
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(3,7,12,0.78)", backdropFilter: "blur(8px)" }}
    >
      <div
        className="w-full max-w-6xl max-h-[92vh] rounded-3xl overflow-hidden flex flex-col"
        style={{
          background: "var(--md-sys-color-surface)",
          border: "1px solid var(--md-sys-color-outline-strong)",
          boxShadow: "var(--md-sys-shadow-floating)",
        }}
      >
        {/* Header */}
        <div
          className="px-5 py-3.5 flex items-center justify-between gap-4"
          style={{ borderBottom: "1px solid var(--md-sys-color-outline)" }}
        >
          <div className="flex items-center gap-2.5">
            <div
              className="w-8 h-8 rounded-xl flex items-center justify-center"
              style={{ background: "var(--md-sys-color-primary-container)", color: "var(--md-sys-color-primary)" }}
            >
              <Atom className="w-4.5 h-4.5" />
            </div>
            <div>
              <h2 className="text-sm font-semibold">完整 118 元素周期表选择器</h2>
              <p className="text-[11px]" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>
                复用 MolForge RDKit 完整化学参数（共价半径 / 范德华半径 / CPK 配色 / 电子构型）
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {selectedAtomCount > 0 && (
              <label className="flex items-center gap-1.5 text-xs cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={replaceSelected}
                  onChange={(e) => setReplaceSelected(e.target.checked)}
                  className="accent-[#5eead4]"
                />
                <span>同时替换已选中的 {selectedAtomCount} 个原子</span>
              </label>
            )}
            <div
              className="flex items-center gap-2 rounded-xl px-3 py-1.5 w-64"
              style={{ background: "var(--md-sys-color-surface-low)", border: "1px solid var(--md-sys-color-outline)" }}
            >
              <Search className="w-3.5 h-3.5" style={{ color: "var(--md-sys-color-on-surface-muted)" }} />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索符号/中文/序数 (如 Pt / 铂 / 78)"
                className="bg-transparent text-xs outline-none flex-1"
              />
            </div>
            <button onClick={onClose} className="p-2 rounded-xl hover:bg-white/5 cursor-pointer">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* 18-Column Grid */}
        <div className="p-4 overflow-auto flex-1 space-y-3">
          <div className="grid gap-1 min-w-[920px]" style={{ gridTemplateColumns: "repeat(18, minmax(0, 1fr))" }}>
            {mainCells.map((cell, i) => {
              if (cell.placeholder) {
                return (
                  <div
                    key={`ph_${i}`}
                    style={{ gridRow: cell.row, gridColumn: cell.col }}
                    className="rounded-lg flex items-center justify-center text-[10px] mono-num opacity-60 border border-dashed border-slate-600"
                  >
                    {cell.placeholder}
                  </div>
                );
              }
              if (!cell.el) return null;
              return (
                <div key={cell.el.atomic_number} style={{ gridRow: cell.row, gridColumn: cell.col }}>
                  {renderTile(cell.el)}
                </div>
              );
            })}
          </div>

          {/* Lanthanides & Actinides */}
          <div className="space-y-1 min-w-[920px] pt-1">
            <div className="grid gap-1 items-center" style={{ gridTemplateColumns: "repeat(18, minmax(0, 1fr))" }}>
              <div className="col-span-2 text-[11px] font-medium pl-1" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>
                镧系 (57–71)
              </div>
              {elements
                .filter((e) => e.atomic_number >= 57 && e.atomic_number <= 71)
                .map((el) => (
                  <div key={el.atomic_number}>{renderTile(el)}</div>
                ))}
            </div>
            <div className="grid gap-1 items-center" style={{ gridTemplateColumns: "repeat(18, minmax(0, 1fr))" }}>
              <div className="col-span-2 text-[11px] font-medium pl-1" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>
                锕系 (89–103)
              </div>
              {elements
                .filter((e) => e.atomic_number >= 89 && e.atomic_number <= 103)
                .map((el) => (
                  <div key={el.atomic_number}>{renderTile(el)}</div>
                ))}
            </div>
          </div>
        </div>

        {/* Bottom Element Telemetry Strip */}
        {currentInfo && (
          <div
            className="px-5 py-2.5 flex flex-wrap items-center justify-between gap-4 text-xs"
            style={{ background: "var(--md-sys-color-surface-low)", borderTop: "1px solid var(--md-sys-color-outline)" }}
          >
            <div className="flex items-center gap-3">
              <span
                className="w-8 h-8 rounded-lg flex items-center justify-center font-bold text-sm"
                style={{ background: currentInfo.hex_color, color: currentInfo.text_color }}
              >
                {currentInfo.symbol}
              </span>
              <div>
                <span className="font-semibold">
                  #{currentInfo.atomic_number} {currentInfo.name_cn} ({currentInfo.name})
                </span>
                <span className="ml-2 text-[11px]" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>
                  {currentInfo.category} · {currentInfo.block}区
                </span>
              </div>
            </div>
            <div className="mono-num text-[11px] flex flex-wrap gap-4" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>
              <span>原子量 {currentInfo.atomic_weight}</span>
              <span>电负性 {currentInfo.electronegativity ?? "N/A"}</span>
              <span>VdW {currentInfo.vdw_radius} Å</span>
              <span>共价 {currentInfo.covalent_radius} Å</span>
              <span>构型 {currentInfo.electron_config}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
