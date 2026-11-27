import React, { useEffect, useRef } from "react";
import {
  Atom,
  Check,
  Compass,
  Eraser,
  Link2,
  Maximize2,
  Sparkles,
  Trash2,
} from "lucide-react";
import type { Atom2DItem, Bond2DItem } from "../../types/studio";

export interface ContextMenuTarget {
  type: "atom" | "bond" | "canvas";
  x: number;
  y: number;
  atom?: Atom2DItem;
  bond?: Bond2DItem;
}

interface CanvasContextMenuProps {
  target: ContextMenuTarget | null;
  onClose: () => void;
  onChangeElement?: (atomId: number, z: number) => void;
  onDeleteAtom?: (atomId: number) => void;
  onCycleBond?: (bondId: number) => void;
  onSetBondOrder?: (bondId: number, order: number) => void;
  onSetAtomCharge?: (atomId: number, charge: number) => void;
  onDeleteBond?: (bondId: number) => void;
  onClean3D?: () => void;
  onFitCamera?: () => void;
  onSelectAll?: () => void;
  onOpenPeriodicTable?: () => void;
}

const QUICK_Z_LIST = [
  { z: 6, sym: "C", color: "#94A3B8" },
  { z: 7, sym: "N", color: "#60A5FA" },
  { z: 8, sym: "O", color: "#F87171" },
  { z: 16, sym: "S", color: "#FACC15" },
  { z: 15, sym: "P", color: "#F59E0B" },
  { z: 9, sym: "F", color: "#4ADE80" },
  { z: 17, sym: "Cl", color: "#34D399" },
  { z: 35, sym: "Br", color: "#FB923C" },
  { z: 1, sym: "H", color: "#CBD5E1" },
];

export const CanvasContextMenu: React.FC<CanvasContextMenuProps> = ({
  target,
  onClose,
  onChangeElement,
  onDeleteAtom,
  onSetBondOrder,
  onSetAtomCharge,
  onDeleteBond,
  onClean3D,
  onFitCamera,
  onSelectAll,
  onOpenPeriodicTable,
}) => {
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    window.addEventListener("mousedown", handleClick);
    return () => window.removeEventListener("mousedown", handleClick);
  }, [onClose]);

  if (!target) return null;

  // Clamped position to keep inside viewport
  const posX = Math.min(window.innerWidth - 220, Math.max(10, target.x));
  const posY = Math.min(window.innerHeight - 280, Math.max(10, target.y));

  return (
    <div
      ref={menuRef}
      className="fixed z-50 min-w-[200px] py-1.5 rounded-xl border shadow-2xl backdrop-blur-2xl text-[12px] select-none animate-in fade-in zoom-in-95 duration-100"
      style={{
        left: posX,
        top: posY,
        backgroundColor: "color-mix(in srgb, var(--bg-secondary) 96%, transparent)",
        borderColor: "var(--border-subtle)",
        boxShadow: "0 18px 48px rgba(0, 0, 0, 0.5)",
        color: "var(--text-primary)",
      }}
    >
      {/* Atom Context */}
      {target.type === "atom" && target.atom && (
        <>
          <div className="px-3 py-1 text-[11px] font-semibold text-[var(--accent-primary)] flex items-center justify-between border-b border-[var(--border-subtle)] pb-1 mb-1">
            <span className="flex items-center gap-1.5">
              <Atom size={13} />
              <span>
                原子 #{target.atom.index} ({target.atom.symbol})
              </span>
            </span>
            <span className="mono-num text-[10px] opacity-70">Z={target.atom.atomic_num}</span>
          </div>

          <div className="px-2 py-1">
            <div className="text-[10.5px] text-[var(--text-muted)] mb-1 px-1">替换元素</div>
            <div className="grid grid-cols-5 gap-1">
              {QUICK_Z_LIST.map((q) => (
                <button
                  key={q.z}
                  type="button"
                  onClick={() => {
                    onChangeElement?.(target.atom!.atom_id, q.z);
                    onClose();
                  }}
                  className="h-6 rounded font-bold text-[11px] flex items-center justify-center hover:bg-[var(--bg-tertiary)] cursor-pointer transition-colors"
                  style={{
                    color: q.color,
                    border: target.atom!.atomic_num === q.z ? "1px solid var(--accent-primary)" : "1px solid transparent",
                  }}
                >
                  {q.sym}
                </button>
              ))}
            </div>
          </div>

          <div className="my-1 border-t border-[var(--border-subtle)]" />

          <div className="px-2 py-1">
            <div className="text-[10.5px] text-[var(--text-muted)] mb-1 px-1 flex items-center justify-between">
              <span>形式电荷</span>
              <span className="mono-num">
                当前 {target.atom.formal_charge > 0 ? `+${target.atom.formal_charge}` : target.atom.formal_charge}
              </span>
            </div>
            <div className="grid grid-cols-5 gap-1">
              {[-2, -1, 0, 1, 2].map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => {
                    onSetAtomCharge?.(target.atom!.atom_id, q);
                    onClose();
                  }}
                  className="h-6 rounded font-bold text-[11px] mono-num flex items-center justify-center hover:bg-[var(--bg-tertiary)] cursor-pointer transition-colors"
                  style={{
                    color: q === 0 ? "var(--text-secondary)" : q > 0 ? "#F87171" : "#60A5FA",
                    border:
                      target.atom!.formal_charge === q
                        ? "1px solid var(--accent-primary)"
                        : "1px solid transparent",
                  }}
                >
                  {q > 0 ? `+${q}` : q}
                </button>
              ))}
            </div>
          </div>

          <div className="my-1 border-t border-[var(--border-subtle)]" />

          {onOpenPeriodicTable && (
            <button
              type="button"
              onClick={() => {
                onOpenPeriodicTable();
                onClose();
              }}
              className="w-full h-7 px-3 flex items-center gap-2 hover:bg-[var(--bg-tertiary)] cursor-pointer text-left"
            >
              <Compass size={13} />
              <span>更多元素 (118 周期表)...</span>
            </button>
          )}

          <button
            type="button"
            onClick={() => {
              onClean3D?.();
              onClose();
            }}
            className="w-full h-7 px-3 flex items-center gap-2 hover:bg-[var(--bg-tertiary)] cursor-pointer text-left"
          >
            <Sparkles size={13} style={{ color: "var(--accent-primary)" }} />
            <span>局部/全分子 3D 力场优化</span>
          </button>

          <div className="my-1 border-t border-[var(--border-subtle)]" />

          <button
            type="button"
            onClick={() => {
              onDeleteAtom?.(target.atom!.atom_id);
              onClose();
            }}
            className="w-full h-7 px-3 flex items-center gap-2 hover:bg-[var(--semantic-error)] hover:text-white cursor-pointer text-left text-[var(--semantic-error)]"
          >
            <Trash2 size={13} />
            <span>删除此原子 (Del)</span>
          </button>
        </>
      )}

      {/* Bond Context */}
      {target.type === "bond" && target.bond && (
        <>
          <div className="px-3 py-1 text-[11px] font-semibold text-[var(--accent-primary)] flex items-center justify-between border-b border-[var(--border-subtle)] pb-1 mb-1">
            <span className="flex items-center gap-1.5">
              <Link2 size={13} />
              <span>化学键 #{target.bond.bond_id}</span>
            </span>
            <span className="mono-num text-[10px] opacity-70">
              {target.bond.i} ↔ {target.bond.j}
            </span>
          </div>

          <div className="px-1 py-0.5 space-y-0.5">
            {[
              { order: 1, label: "单键 (Single Bond, 1.0)" },
              { order: 2, label: "双键 (Double Bond, 2.0)" },
              { order: 3, label: "三键 (Triple Bond, 3.0)" },
              { order: 4, label: "芳香键 (Aromatic, 1.5)" },
            ].map((bo) => {
              const active = target.bond!.order === bo.order;
              return (
                <button
                  key={bo.order}
                  type="button"
                  onClick={() => {
                    onSetBondOrder?.(target.bond!.bond_id, bo.order);
                    onClose();
                  }}
                  className="w-full h-7 px-2.5 rounded-lg flex items-center justify-between hover:bg-[var(--bg-tertiary)] cursor-pointer text-left"
                >
                  <span>{bo.label}</span>
                  {active && <Check size={12} className="text-[var(--accent-primary)]" />}
                </button>
              );
            })}
          </div>

          <div className="my-1 border-t border-[var(--border-subtle)]" />

          <button
            type="button"
            onClick={() => {
              onDeleteBond?.(target.bond!.bond_id);
              onClose();
            }}
            className="w-full h-7 px-3 flex items-center gap-2 hover:bg-[var(--semantic-error)] hover:text-white cursor-pointer text-left text-[var(--semantic-error)]"
          >
            <Eraser size={13} />
            <span>删除化学键</span>
          </button>
        </>
      )}

      {/* Blank Canvas Context */}
      {target.type === "canvas" && (
        <>
          <div className="px-3 py-1 text-[11px] font-semibold text-[var(--text-secondary)] border-b border-[var(--border-subtle)] pb-1 mb-1">
            工作区操作 (Canvas Actions)
          </div>

          <button
            type="button"
            onClick={() => {
              onClean3D?.();
              onClose();
            }}
            className="w-full h-7 px-3 flex items-center gap-2 hover:bg-[var(--bg-tertiary)] cursor-pointer text-left"
          >
            <Sparkles size={13} style={{ color: "var(--accent-primary)" }} />
            <span>3D 力场几何优化 (Ctrl+Shift+K)</span>
          </button>

          <button
            type="button"
            onClick={() => {
              onFitCamera?.();
              onClose();
            }}
            className="w-full h-7 px-3 flex items-center gap-2 hover:bg-[var(--bg-tertiary)] cursor-pointer text-left"
          >
            <Maximize2 size={13} />
            <span>重设视角 / 居中适应 (F)</span>
          </button>

          <div className="my-1 border-t border-[var(--border-subtle)]" />

          <button
            type="button"
            onClick={() => {
              onSelectAll?.();
              onClose();
            }}
            className="w-full h-7 px-3 flex items-center gap-2 hover:bg-[var(--bg-tertiary)] cursor-pointer text-left"
          >
            <Check size={13} />
            <span>全选所有原子 (Ctrl+A)</span>
          </button>

          <button
            type="button"
            onClick={() => {
              onOpenPeriodicTable?.();
              onClose();
            }}
            className="w-full h-7 px-3 flex items-center gap-2 hover:bg-[var(--bg-tertiary)] cursor-pointer text-left"
          >
            <Compass size={13} />
            <span>打开 118 元素周期表...</span>
          </button>
        </>
      )}
    </div>
  );
};
