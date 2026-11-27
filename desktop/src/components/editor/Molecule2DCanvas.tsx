import React, { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";
import type { Atom2DItem, Bond2DItem, EditTool, RingTemplateSpec } from "../../types/studio";
import { CanvasContextMenu, type ContextMenuTarget } from "./CanvasContextMenu";

interface Props {
  atoms: Atom2DItem[];
  bonds: Bond2DItem[];
  truncated: boolean;
  totalAtoms: number;
  selectedIndices: number[];
  onSelectIndices: (indices: number[]) => void;
  darkTheme: boolean;
  showAtomIds: boolean;
  activeTool: EditTool;
  activeElementZ: number;
  activeRing: RingTemplateSpec;
  onAddAtom: (params: { atomic_num: number; bond_to?: number; pos_2d?: [number, number] }) => void;
  onChangeElement: (atomId: number, atomicNum: number) => void;
  onAddBond: (atomA: number, atomB: number) => void;
  onCycleBond: (bondId: number) => void;
  onSetBondOrder?: (bondId: number, order: number) => void;
  onSetAtomCharge?: (atomId: number, charge: number) => void;
  onDeleteAtom: (atomId: number) => void;
  onDeleteBond: (bondId: number) => void;
  onAddRing: (params: { attach_to?: number; center_2d?: [number, number] }) => void;
  onInsertFragment: (anchorAtomId?: number) => void;
  onMoveAtom: (atomId: number, pos2d: [number, number]) => void;
  onClean3D?: () => void;
  onFitCamera?: () => void;
  onOpenPeriodicTable?: () => void;
}

const TOOL_HINTS: Record<EditTool, string> = {
  select: "点击选择原子 · 拖动调整位置 · Shift+点击多选",
  atom: "点击原子沿键生长 · 点击空白新建原子 · 点击已选原子替换元素",
  bond: "先后点击两原子建键 · 点击已有键切换单/双/三/芳香键",
  ring: "点击原子并环对接 · 点击空白处放置当前环模板",
  fragment: "点击目标原子接枝当前 3D 化学片段 · 点击空白独立插入",
  erase: "点击任意原子或化学键擦除（完整支持撤销）",
};

export const Molecule2DCanvas: React.FC<Props> = ({
  atoms,
  bonds,
  truncated,
  totalAtoms,
  selectedIndices,
  onSelectIndices,
  darkTheme,
  showAtomIds,
  activeTool,
  activeElementZ,
  activeRing,
  onAddAtom,
  onChangeElement,
  onAddBond,
  onCycleBond,
  onSetBondOrder,
  onSetAtomCharge,
  onDeleteAtom,
  onDeleteBond,
  onAddRing,
  onInsertFragment,
  onMoveAtom,
  onClean3D,
  onFitCamera,
  onOpenPeriodicTable,
}) => {
  const [zoom, setZoom] = useState(1.0);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [bondStartAtom, setBondStartAtom] = useState<number | null>(null);
  const [dragAtom, setDragAtom] = useState<{
    atomId: number;
    index: number;
    x2: number;
    y2: number;
    moved: boolean;
  } | null>(null);
  const [panning, setPanning] = useState<{ x: number; y: number } | null>(null);
  const [contextMenuTarget, setContextMenuTarget] = useState<ContextMenuTarget | null>(null);
  const [hoveredAtom, setHoveredAtom] = useState<Atom2DItem | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  // ChemDraw-grade hotkeys on hovering atom (e.g. press C, N, O, S, F, P, H)
  // 悬停原子时元素字母键一律换元素（任何工具下；字母键不是任何工具的点击动作），
  // 命中时 stopImmediatePropagation，避免与全局工具键 b(建键)/f(片段)/H(显式氢) 双重映射。
  // 监听器只注册一次（子组件 effect 先于 App），用 ref 读最新状态保证顺序稳定。
  const hoverRef = useRef<number | null>(null);
  const toolRef = useRef<EditTool>(activeTool);
  const changeElRef = useRef(onChangeElement);
  const atomsRef = useRef(atoms);
  hoverRef.current = hoveredAtom ? hoveredAtom.atom_id : null;
  toolRef.current = activeTool;
  changeElRef.current = onChangeElement;
  atomsRef.current = atoms;
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      // 悬停只记 atom_id，执行时从最新原子表解析：外部同步刷新后旧对象不会误改他原子
      const hovId = hoverRef.current;
      const hov = hovId === null ? null : atomsRef.current.find((a) => a.atom_id === hovId) || null;
      const tool = toolRef.current;
      if (!hov) {
        console.debug("[HK] skip", e.key, tool, hovId);
        return;
      }
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) return;
      const k = e.key.toLowerCase();
      const map: Record<string, number> = {
        c: 6, n: 7, o: 8, s: 16, f: 9, p: 15, h: 1, b: 5,
      };
      if (map[k]) {
        console.debug("[HK] hit", k, tool, hov.atom_id);
        e.preventDefault();
        e.stopImmediatePropagation();
        changeElRef.current(hov.atom_id, map[k]);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const bounds = useMemo(() => {
    if (!atoms.length) return { cx: 0, cy: 0, span: 10 };
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    for (const a of atoms) {
      if (a.x2 < minX) minX = a.x2;
      if (a.x2 > maxX) maxX = a.x2;
      if (a.y2 < minY) minY = a.y2;
      if (a.y2 > maxY) maxY = a.y2;
    }
    const span = Math.max(4.5, Math.max(maxX - minX, maxY - minY) * 1.48);
    return { cx: 0.5 * (minX + maxX), cy: 0.5 * (minY + maxY), span };
  }, [atoms]);

  if (truncated) {
    return (
      <div
        className="h-full flex flex-col items-center justify-center p-6 text-center"
        style={{ backgroundColor: "var(--bg-primary)" }}
      >
        <div
          className="w-11 h-11 rounded-xl flex items-center justify-center mb-3"
          style={{ backgroundColor: "var(--semantic-warning-soft)", color: "var(--semantic-warning)" }}
        >
          <AlertTriangle size={20} />
        </div>
        <div className="text-[13px] font-semibold">超大体系 2D 矢量画布已自动熔断保护</div>
        <p className="text-[12px] mt-1 max-w-xs" style={{ color: "var(--text-secondary)" }}>
          当前分子包含 <span className="mono-num font-semibold">{totalAtoms.toLocaleString()}</span> 个原子，请使用右侧 WebGPU 3D 视口浏览。
        </p>
      </div>
    );
  }

  const w = 520;
  const h = 520;
  const pxScale = (Math.min(w, h) / bounds.span) * zoom;
  const toScreen = (x: number, y: number) => ({
    sx: w * 0.5 + pan.x + (x - bounds.cx) * pxScale,
    sy: h * 0.5 + pan.y - (y - bounds.cy) * pxScale,
  });
  const toMol = (clientX: number, clientY: number): [number, number] => {
    const svg = svgRef.current;
    if (!svg) return [0, 0];
    const rect = svg.getBoundingClientRect();
    const vx = ((clientX - rect.left) / Math.max(1, rect.width)) * w;
    const vy = ((clientY - rect.top) / Math.max(1, rect.height)) * h;
    return [
      bounds.cx + (vx - w * 0.5 - pan.x) / pxScale,
      bounds.cy - (vy - h * 0.5 - pan.y) / pxScale,
    ];
  };

  const bondStroke = darkTheme ? "#CBD8E6" : "#1E293B";
  const bg = darkTheme ? "#0B1220" : "#FAFBFD";
  const labelPillBg = darkTheme ? "#0B1220" : "#FAFBFD";

  return (
    <div
      className="relative h-full w-full select-none overflow-hidden"
      style={{
        backgroundColor: bg,
        backgroundImage: "radial-gradient(var(--grid-dot) 1px, transparent 1px)",
        backgroundSize: "18px 18px",
      }}
    >
      {/* Hint & Fit (Bottom bar to avoid colliding with top viewport strip & left tool rail) */}
      <div className="absolute bottom-2.5 left-14 right-2.5 z-10 flex items-center justify-between gap-2 pointer-events-none">
        <div
          className="px-2.5 py-1 rounded-md text-[11px] pointer-events-auto truncate"
          style={{
            backgroundColor: "var(--bg-secondary)",
            color: "var(--text-secondary)",
            border: "1px solid var(--border-subtle)",
          }}
        >
          {activeTool === "ring" ? `${activeRing.label} · ${TOOL_HINTS.ring}` : TOOL_HINTS[activeTool]}
        </div>
        <button
          type="button"
          onClick={() => {
            setZoom(1.0);
            setPan({ x: 0, y: 0 });
          }}
          className="studio-btn !h-7 !px-2 pointer-events-auto shrink-0"
          title="居中适应二维画布"
        >
          <RotateCcw size={12} />
          <span>居中</span>
        </button>
      </div>

      <svg
        ref={svgRef}
        data-testid="canvas-2d"
        viewBox={`0 0 ${w} ${h}`}
        className={`w-full h-full ${activeTool === "select" ? "cursor-default" : "cursor-crosshair"}`}
        onWheel={(e) => {
          e.preventDefault();
          const f = Math.exp(-e.deltaY * 0.0011);
          setZoom((z) => Math.max(0.25, Math.min(8, z * f)));
        }}
        onMouseDown={(e) => {
          if (e.button === 1 || e.button === 2 || (e.button === 0 && e.altKey)) {
            setPanning({ x: e.clientX, y: e.clientY });
          } else if (e.button === 0 && e.target === svgRef.current) {
            setBondStartAtom(null);
            const pt = toMol(e.clientX, e.clientY);
            if (activeTool === "atom") onAddAtom({ atomic_num: activeElementZ, pos_2d: pt });
            else if (activeTool === "ring") onAddRing({ center_2d: pt });
            else if (activeTool === "fragment") onInsertFragment(undefined);
            else if (activeTool === "select") onSelectIndices([]);
          }
        }}
        onMouseMove={(e) => {
          if (dragAtom) {
            const pt = toMol(e.clientX, e.clientY);
            setDragAtom({ ...dragAtom, x2: pt[0], y2: pt[1], moved: true });
          } else if (panning) {
            const dx = e.clientX - panning.x;
            const dy = e.clientY - panning.y;
            setPanning({ x: e.clientX, y: e.clientY });
            setPan((p) => ({ x: p.x + dx, y: p.y + dy }));
          }
        }}
        onMouseUp={() => {
          if (dragAtom?.moved) {
            onMoveAtom(dragAtom.atomId, [dragAtom.x2, dragAtom.y2]);
          }
          setDragAtom(null);
          setPanning(null);
        }}
        onContextMenu={(e) => {
          e.preventDefault();
          setContextMenuTarget({ type: "canvas", x: e.clientX, y: e.clientY });
        }}
      >
        {bonds.map((b) => {
          const a = atoms[b.i];
          const c = atoms[b.j];
          if (!a || !c) return null;
          const ax = dragAtom && dragAtom.index === a.index ? dragAtom.x2 : a.x2;
          const ay = dragAtom && dragAtom.index === a.index ? dragAtom.y2 : a.y2;
          const cx = dragAtom && dragAtom.index === c.index ? dragAtom.x2 : c.x2;
          const cy = dragAtom && dragAtom.index === c.index ? dragAtom.y2 : c.y2;
          const p1 = toScreen(ax, ay);
          const p2 = toScreen(cx, cy);
          const dx = p2.sx - p1.sx;
          const dy = p2.sy - p1.sy;
          const len = Math.hypot(dx, dy) || 1;
          const nx = (-dy / len) * 3.4;
          const ny = (dx / len) * 3.4;

          const onBondClick = (ev: React.MouseEvent) => {
            ev.stopPropagation();
            if (activeTool === "erase") onDeleteBond(b.bond_id);
            else if (activeTool === "bond" || activeTool === "select") onCycleBond(b.bond_id);
          };

          return (
            <g
              key={b.bond_id}
              onClick={onBondClick}
              onContextMenu={(ev) => {
                ev.preventDefault();
                ev.stopPropagation();
                setContextMenuTarget({ type: "bond", bond: b, x: ev.clientX, y: ev.clientY });
              }}
              className="cursor-pointer"
            >
              <line x1={p1.sx} y1={p1.sy} x2={p2.sx} y2={p2.sy} stroke="transparent" strokeWidth={12} />
              {b.order === 2 ? (
                <>
                  <line x1={p1.sx + nx * 0.6} y1={p1.sy + ny * 0.6} x2={p2.sx + nx * 0.6} y2={p2.sy + ny * 0.6} stroke={bondStroke} strokeWidth={1.7} strokeLinecap="round" />
                  <line x1={p1.sx - nx * 0.6} y1={p1.sy - ny * 0.6} x2={p2.sx - nx * 0.6} y2={p2.sy - ny * 0.6} stroke={bondStroke} strokeWidth={1.7} strokeLinecap="round" />
                </>
              ) : b.order === 3 ? (
                <>
                  <line x1={p1.sx} y1={p1.sy} x2={p2.sx} y2={p2.sy} stroke={bondStroke} strokeWidth={1.6} />
                  <line x1={p1.sx + nx * 1.15} y1={p1.sy + ny * 1.15} x2={p2.sx + nx * 1.15} y2={p2.sy + ny * 1.15} stroke={bondStroke} strokeWidth={1.25} />
                  <line x1={p1.sx - nx * 1.15} y1={p1.sy - ny * 1.15} x2={p2.sx - nx * 1.15} y2={p2.sy - ny * 1.15} stroke={bondStroke} strokeWidth={1.25} />
                </>
              ) : b.aromatic || b.order === 4 ? (
                <>
                  <line x1={p1.sx} y1={p1.sy} x2={p2.sx} y2={p2.sy} stroke={bondStroke} strokeWidth={1.75} strokeLinecap="round" />
                  <line x1={p1.sx + nx * 0.8} y1={p1.sy + ny * 0.8} x2={p2.sx + nx * 0.8} y2={p2.sy + ny * 0.8} stroke={bondStroke} strokeWidth={1.15} strokeDasharray="3.5 3" />
                </>
              ) : (
                <line x1={p1.sx} y1={p1.sy} x2={p2.sx} y2={p2.sy} stroke={bondStroke} strokeWidth={1.85} strokeLinecap="round" />
              )}
            </g>
          );
        })}

        {atoms.map((a) => {
          const ax = dragAtom && dragAtom.index === a.index ? dragAtom.x2 : a.x2;
          const ay = dragAtom && dragAtom.index === a.index ? dragAtom.y2 : a.y2;
          const { sx, sy } = toScreen(ax, ay);
          const isSelected = selectedIndices.includes(a.index);
          const isBondSrc = bondStartAtom === a.atom_id;
          const showLabel = a.symbol !== "C" || isSelected || a.formal_charge !== 0;
          let textColor = `rgb(${a.color[0]},${a.color[1]},${a.color[2]})`;
          if (a.symbol === "C") {
            textColor = darkTheme ? "#E2E8F0" : "#0F172A";
          } else if (!darkTheme) {
            if (a.symbol === "H") textColor = "#475569";
            else if (a.symbol === "S") textColor = "#B45309";
            else if (a.symbol === "F" || a.symbol === "Cl") textColor = "#047857";
          }

          return (
            <g
              key={a.atom_id}
              transform={`translate(${sx},${sy})`}
              className="cursor-pointer"
              onMouseEnter={() => setHoveredAtom(a)}
              onMouseLeave={() => setHoveredAtom(null)}
              onContextMenu={(ev) => {
                ev.preventDefault();
                ev.stopPropagation();
                setContextMenuTarget({ type: "atom", atom: a, x: ev.clientX, y: ev.clientY });
              }}
              onMouseDown={(ev) => {
                ev.stopPropagation();
                if (activeTool === "select" && ev.button === 0) {
                  setDragAtom({ atomId: a.atom_id, index: a.index, x2: a.x2, y2: a.y2, moved: false });
                }
              }}
              onClick={(ev) => {
                ev.stopPropagation();
                if (activeTool === "erase") {
                  onDeleteAtom(a.atom_id);
                  return;
                }
                if (activeTool === "atom") {
                  if (isSelected) onChangeElement(a.atom_id, activeElementZ);
                  else onAddAtom({ atomic_num: activeElementZ, bond_to: a.atom_id });
                  return;
                }
                if (activeTool === "bond") {
                  if (bondStartAtom === null) setBondStartAtom(a.atom_id);
                  else if (bondStartAtom === a.atom_id) setBondStartAtom(null);
                  else {
                    onAddBond(bondStartAtom, a.atom_id);
                    setBondStartAtom(null);
                  }
                  return;
                }
                if (activeTool === "ring") {
                  onAddRing({ attach_to: a.atom_id });
                  return;
                }
                if (activeTool === "fragment") {
                  onInsertFragment(a.atom_id);
                  return;
                }
                if (ev.shiftKey) {
                  onSelectIndices(
                    isSelected ? selectedIndices.filter((x) => x !== a.index) : [...selectedIndices, a.index]
                  );
                } else {
                  onSelectIndices([a.index]);
                }
              }}
            >
              {(isSelected || isBondSrc) && (
                <circle
                  r={12.5}
                  fill={isBondSrc ? "rgba(107,169,237,0.22)" : "rgba(49,183,165,0.22)"}
                  stroke={isBondSrc ? "#6BA9ED" : "#31B7A5"}
                  strokeWidth={1.6}
                />
              )}
              <circle r={10} fill="transparent" />
              {showLabel && (
                <>
                  <circle r={7.5} fill={labelPillBg} />
                  <text
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontSize={a.symbol === "H" ? 10 : 12}
                    fontWeight={700}
                    fill={textColor}
                    fontFamily="Arial, sans-serif"
                  >
                    {a.symbol}
                    {a.formal_charge !== 0
                      ? a.formal_charge > 0
                        ? `+${a.formal_charge > 1 ? a.formal_charge : ""}`
                        : `${a.formal_charge < -1 ? a.formal_charge : "-"}`
                      : ""}
                  </text>
                </>
              )}
              {showAtomIds && (
                <text
                  x={8}
                  y={-7}
                  fontSize={8.5}
                  fill="var(--accent-primary)"
                  className="mono-num"
                >
                  {a.display_id}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      <CanvasContextMenu
        target={contextMenuTarget}
        onClose={() => setContextMenuTarget(null)}
        onChangeElement={onChangeElement}
        onDeleteAtom={onDeleteAtom}
        onSetBondOrder={onSetBondOrder}
        onSetAtomCharge={onSetAtomCharge}
        onDeleteBond={onDeleteBond}
        onClean3D={onClean3D}
        onFitCamera={onFitCamera}
        onSelectAll={() => onSelectIndices(atoms.map((_, i) => i))}
        onOpenPeriodicTable={onOpenPeriodicTable}
      />
    </div>
  );
};
