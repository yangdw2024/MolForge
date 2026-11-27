import React, { useMemo, useState } from "react";
import { Atom, Search, X } from "lucide-react";
import type { ElementInfo } from "../../types/studio";

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
        type="button"
        onMouseEnter={() => setHovered(el)}
        onClick={() => {
          onSelectElement(el.atomic_number, replaceSelected && selectedAtomCount > 0);
          onClose();
        }}
        className="w-full h-[46px] rounded-md px-0.5 flex flex-col items-center justify-center cursor-pointer transition-transform hover:scale-105"
        style={{
          backgroundColor: el.hex_color,
          color: el.text_color,
          opacity: isMatched ? 1 : 0.16,
          outline: isActive ? "2.5px solid var(--accent-primary)" : "1px solid rgba(15, 23, 42, 0.25)",
        }}
        title={`${el.name_cn} (${el.name}) · Z=${el.atomic_number}`}
      >
        <span className="text-[8.5px] leading-none opacity-80 mono-num">{el.atomic_number}</span>
        <span className="text-[12px] font-bold leading-tight">{el.symbol}</span>
        <span className="text-[8px] leading-none opacity-80 truncate max-w-full">{el.name_cn}</span>
      </button>
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(6, 12, 22, 0.72)" }}
      onClick={onClose}
    >
      <div
        data-testid="periodic-table-modal"
        className="w-full max-w-[1060px] max-h-[92vh] studio-surface overflow-hidden flex flex-col"
        style={{ boxShadow: "var(--shadow-modal)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-4 py-3 border-b flex flex-wrap items-center justify-between gap-3" style={{ borderColor: "var(--border-subtle)", backgroundColor: "var(--bg-secondary)" }}>
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ backgroundColor: "var(--accent-soft)", color: "var(--accent-primary)" }}>
              <Atom size={16} />
            </div>
            <div>
              <h2 className="text-[14px] font-semibold">完整 118 号元素周期表选择器</h2>
              <p className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
                复用 MolForge 标准 CPK 配色、Pauling 电负性与共价/Van der Waals 半径参数
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            {selectedAtomCount > 0 && (
              <label className="flex items-center gap-1.5 text-[11.5px] cursor-pointer px-2.5 py-1 rounded-md studio-inset">
                <input
                  type="checkbox"
                  checked={replaceSelected}
                  onChange={(e) => setReplaceSelected(e.target.checked)}
                />
                <span>替换已选原子 ({selectedAtomCount})</span>
              </label>
            )}

            <div className="relative">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: "var(--text-muted)" }} />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="检索 Pt / 铂 / 78 / 卤素..."
                className="studio-input pl-8 w-[210px]"
              />
            </div>

            <button type="button" onClick={onClose} className="studio-btn !w-8 !px-0" aria-label="关闭周期表">
              <X size={14} />
            </button>
          </div>
        </div>

        {/* 18-Column Grid */}
        <div className="p-4 studio-scroll space-y-2.5">
          <div className="grid gap-1" style={{ gridTemplateColumns: "repeat(18, minmax(0, 1fr))" }}>
            {mainCells.map((cell, i) => (
              <div
                key={i}
                style={{ gridColumn: cell.col, gridRow: cell.row }}
              >
                {cell.el ? (
                  renderTile(cell.el)
                ) : (
                  <div
                    className="w-full h-[46px] rounded-md flex items-center justify-center text-[9.5px] mono-num"
                    style={{
                      backgroundColor: "var(--bg-secondary)",
                      color: "var(--text-muted)",
                      border: "1px dashed var(--border-subtle)",
                    }}
                  >
                    {cell.placeholder}
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="grid gap-1 pt-2 border-t" style={{ gridTemplateColumns: "repeat(18, minmax(0, 1fr))", borderColor: "var(--border-subtle)" }}>
            <div className="col-span-3 flex items-center justify-end pr-2 text-[11px] font-medium" style={{ color: "var(--text-secondary)" }}>
              镧系 La–Lu
            </div>
            {elements
              .filter((e) => e.atomic_number >= 57 && e.atomic_number <= 71)
              .map((el) => (
                <div key={el.atomic_number}>{renderTile(el)}</div>
              ))}
          </div>

          <div className="grid gap-1" style={{ gridTemplateColumns: "repeat(18, minmax(0, 1fr))" }}>
            <div className="col-span-3 flex items-center justify-end pr-2 text-[11px] font-medium" style={{ color: "var(--text-secondary)" }}>
              锕系 Ac–Lr
            </div>
            {elements
              .filter((e) => e.atomic_number >= 89 && e.atomic_number <= 103)
              .map((el) => (
                <div key={el.atomic_number}>{renderTile(el)}</div>
              ))}
          </div>
        </div>

        {/* Telemetry Strip */}
        {currentInfo && (
          <div className="px-4 py-2.5 border-t flex flex-wrap items-center justify-between gap-3 text-[12px]" style={{ borderColor: "var(--border-subtle)", backgroundColor: "var(--bg-secondary)" }}>
            <div className="flex items-center gap-2.5">
              <span
                className="w-7 h-7 rounded-md font-bold flex items-center justify-center text-[13px]"
                style={{ backgroundColor: currentInfo.hex_color, color: currentInfo.text_color }}
              >
                {currentInfo.symbol}
              </span>
              <span className="font-semibold">
                #{currentInfo.atomic_number} {currentInfo.name_cn} ({currentInfo.name})
              </span>
              <span className="px-2 py-0.5 rounded text-[11px]" style={{ backgroundColor: "var(--bg-panel)", color: "var(--text-secondary)", border: "1px solid var(--border-subtle)" }}>
                {currentInfo.category} · {currentInfo.block} 区
              </span>
            </div>
            <div className="mono-num text-[11.5px] flex items-center gap-4" style={{ color: "var(--text-secondary)" }}>
              <span>质量 {currentInfo.atomic_weight}</span>
              <span>电负性 {currentInfo.electronegativity ?? "—"}</span>
              <span>VdW {currentInfo.vdw_radius} Å</span>
              <span>共价 {currentInfo.covalent_radius} Å</span>
              <span>{currentInfo.electron_config}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
