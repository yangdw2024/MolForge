import React, { useMemo, useRef, useState } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";
import type { Atom2DItem, Bond2DItem, EditTool, RingTemplateSpec } from "../types/molforge";

interface Props {
  atoms: Atom2DItem[];
  bonds: Bond2DItem[];
  truncated: boolean;
  totalAtoms: number;
  selectedIndices: number[];
  onSelectIndices: (indices: number[]) => void;
  darkTheme: boolean;
  activeTool: EditTool;
  activeElementZ: number;
  activeRing: RingTemplateSpec;
  onAddAtom: (params: { atomic_num: number; bond_to?: number; pos_2d?: [number, number] }) => void;
  onChangeElement: (atomId: number, atomicNum: number) => void;
  onAddBond: (atomA: number, atomB: number) => void;
  onCycleBond: (bondId: number) => void;
  onDeleteAtom: (atomId: number) => void;
  onDeleteBond: (bondId: number) => void;
  onAddRing: (params: { attach_to?: number; center_2d?: [number, number] }) => void;
  onMoveAtom: (atomId: number, pos2d: [number, number]) => void;
}

const TOOL_HINTS: Record<EditTool, string> = {
  select: "点击选原子 · 拖动原子移动 · Shift+点击多选",
  atom: "点击原子沿键生长 · 点击空白处新建独立原子 · 点已选原子可改元素",
  bond: "先后点击两原子建键 · 点击已有键循环切换单/双/三/芳香键",
  ring: "点击原子对接并环/外接环 · 点击空白处放置环模板",
  erase: "点击任意原子或化学键立即擦除（支持撤销）",
};

export const Molecule2DCanvas: React.FC<Props> = ({
  atoms,
  bonds,
  truncated,
  totalAtoms,
  selectedIndices,
  onSelectIndices,
  darkTheme,
  activeTool,
  activeElementZ,
  activeRing,
  onAddAtom,
  onChangeElement,
  onAddBond,
  onCycleBond,
  onDeleteAtom,
  onDeleteBond,
  onAddRing,
  onMoveAtom,
}) => {
  const [zoom, setZoom] = useState(1.0);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [bondStartAtom, setBondStartAtom] = useState<number | null>(null);
  const [dragAtom, setDragAtom] = useState<{ atomId: number; index: number; x2: number; y2: number; moved: boolean } | null>(null);
  const [panning, setPanning] = useState<{ x: number; y: number } | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const bounds = useMemo(() => {
    if (!atoms.length) return { cx: 0, cy: 0, span: 10 };
    let minX = Infinity,
      maxX = -Infinity,
      minY = Infinity,
      maxY = -Infinity;
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
        style={{ background: "var(--md-sys-color-surface-low)" }}
      >
        <div
          className="w-12 h-12 rounded-2xl flex items-center justify-center mb-3"
          style={{ background: "rgba(251, 146, 60, 0.14)", color: "#fb923c" }}
        >
          <AlertTriangle className="w-6 h-6" />
        </div>
        <h3 className="text-sm font-semibold">超大体系 2D 矢量画布已自动保护熔断</h3>
        <p className="text-xs mt-1.5 max-w-xs" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>
          当前分子共含 <span className="mono-num font-semibold">{totalAtoms.toLocaleString()}</span> 个原子，已聚焦右侧
          WebGPU 3D 视口渲染。
        </p>
      </div>
    );
  }

  const half = (bounds.span * 0.5) / zoom;
  const vbLeft = bounds.cx - pan.x - half;
  const vbTop = bounds.cy - pan.y - half;
  const vb = `${vbLeft} ${vbTop} ${half * 2} ${half * 2}`;
  const bondStroke = darkTheme ? "#cbd5e1" : "#1e293b";
  const paperBg = darkTheme ? "#0b1119" : "#ffffff";

  const clientToWorld = (clientX: number, clientY: number): [number, number] => {
    const svg = svgRef.current;
    if (!svg) return [0, 0];
    const rect = svg.getBoundingClientRect();
    const minDim = Math.min(rect.width, rect.height) || 1;
    const scale = (half * 2) / minDim;
    const ox = rect.left + (rect.width - minDim) * 0.5;
    const oy = rect.top + (rect.height - minDim) * 0.5;
    return [vbLeft + (clientX - ox) * scale, vbTop + (clientY - oy) * scale];
  };

  return (
    <div className="relative w-full h-full select-none overflow-hidden" style={{ background: paperBg }}>
      <div className="absolute top-3 left-3 z-10 flex items-center gap-2 pointer-events-none">
        <span
          className="text-[11px] px-2.5 py-1 rounded-full font-medium"
          style={{
            background: darkTheme ? "rgba(18, 28, 40, 0.88)" : "rgba(241, 245, 249, 0.94)",
            border: "1px solid var(--md-sys-color-outline)",
            color: "var(--md-sys-color-on-surface-muted)",
          }}
        >
          2D 矢量编辑器 · {TOOL_HINTS[activeTool]}
        </span>
        <button
          onClick={() => {
            setZoom(1);
            setPan({ x: 0, y: 0 });
          }}
          className="p-1.5 rounded-lg cursor-pointer pointer-events-auto"
          style={{
            background: darkTheme ? "rgba(18, 28, 40, 0.88)" : "rgba(241, 245, 249, 0.94)",
            border: "1px solid var(--md-sys-color-outline)",
          }}
          title="居中适配 2D 画布"
        >
          <RotateCcw className="w-3.5 h-3.5" />
        </button>
      </div>

      <svg
        ref={svgRef}
        viewBox={vb}
        className={`w-full h-full ${activeTool === "select" ? "cursor-default" : "cursor-crosshair"}`}
        onWheel={(e) => {
          const factor = e.deltaY < 0 ? 1.12 : 0.89;
          setZoom((z) => Math.max(0.25, Math.min(8, z * factor)));
        }}
        onMouseDown={(e) => {
          if (e.button === 1 || e.button === 2 || e.altKey) {
            setPanning({ x: e.clientX, y: e.clientY });
          }
        }}
        onMouseMove={(e) => {
          if (panning) {
            const scale = (half * 2) / Math.max(1, e.currentTarget.clientHeight);
            setPan((p) => ({ x: p.x + (e.clientX - panning.x) * scale, y: p.y + (e.clientY - panning.y) * scale }));
            setPanning({ x: e.clientX, y: e.clientY });
          } else if (dragAtom) {
            const [wx, wy] = clientToWorld(e.clientX, e.clientY);
            setDragAtom((d) => (d ? { ...d, x2: wx, y2: wy, moved: true } : null));
          }
        }}
        onMouseUp={() => {
          setPanning(null);
          if (dragAtom) {
            if (dragAtom.moved) {
              onMoveAtom(dragAtom.atomId, [dragAtom.x2, dragAtom.y2]);
            }
            setDragAtom(null);
          }
        }}
        onClick={(e) => {
          if (e.button !== 0 || dragAtom?.moved) return;
          const [wx, wy] = clientToWorld(e.clientX, e.clientY);
          if (activeTool === "atom") {
            onAddAtom({ atomic_num: activeElementZ, pos_2d: [wx, wy] });
          } else if (activeTool === "ring") {
            onAddRing({ center_2d: [wx, wy] });
          } else if (activeTool === "select" && !e.shiftKey) {
            onSelectIndices([]);
          }
          setBondStartAtom(null);
        }}
        onContextMenu={(e) => e.preventDefault()}
      >
        {/* Bonds */}
        {bonds.map((b) => {
          const rawA1 = atoms[b.i];
          const rawA2 = atoms[b.j];
          if (!rawA1 || !rawA2) return null;
          const a1 = dragAtom && dragAtom.index === rawA1.index ? { ...rawA1, x2: dragAtom.x2, y2: dragAtom.y2 } : rawA1;
          const a2 = dragAtom && dragAtom.index === rawA2.index ? { ...rawA2, x2: dragAtom.x2, y2: dragAtom.y2 } : rawA2;
          const dx = a2.x2 - a1.x2;
          const dy = a2.y2 - a1.y2;
          const len = Math.hypot(dx, dy) || 1;
          const nx = -dy / len;
          const ny = dx / len;
          const sw = Math.max(0.035, bounds.span * 0.0045);

          const handleBondClick = (e: React.MouseEvent) => {
            e.stopPropagation();
            if (activeTool === "erase") {
              onDeleteBond(b.bond_id);
            } else if (activeTool === "bond") {
              onCycleBond(b.bond_id);
            }
          };

          return (
            <g key={b.bond_id} className="cursor-pointer" onClick={handleBondClick}>
              {/* Invisible thick hit target */}
              <line x1={a1.x2} y1={a1.y2} x2={a2.x2} y2={a2.y2} stroke="transparent" strokeWidth={sw * 5} />
              {b.order === 2 || b.aromatic ? (
                <>
                  <line
                    x1={a1.x2 + nx * bounds.span * 0.011}
                    y1={a1.y2 + ny * bounds.span * 0.011}
                    x2={a2.x2 + nx * bounds.span * 0.011}
                    y2={a2.y2 + ny * bounds.span * 0.011}
                    stroke={bondStroke}
                    strokeWidth={sw}
                    strokeLinecap="round"
                  />
                  <line
                    x1={a1.x2 - nx * bounds.span * 0.011}
                    y1={a1.y2 - ny * bounds.span * 0.011}
                    x2={a2.x2 - nx * bounds.span * 0.011}
                    y2={a2.y2 - ny * bounds.span * 0.011}
                    stroke={bondStroke}
                    strokeWidth={sw}
                    strokeDasharray={b.aromatic ? `${sw * 2.4} ${sw * 2.2}` : undefined}
                    strokeLinecap="round"
                  />
                </>
              ) : b.order === 3 ? (
                <>
                  <line x1={a1.x2} y1={a1.y2} x2={a2.x2} y2={a2.y2} stroke={bondStroke} strokeWidth={sw} strokeLinecap="round" />
                  <line
                    x1={a1.x2 + nx * bounds.span * 0.016}
                    y1={a1.y2 + ny * bounds.span * 0.016}
                    x2={a2.x2 + nx * bounds.span * 0.016}
                    y2={a2.y2 + ny * bounds.span * 0.016}
                    stroke={bondStroke}
                    strokeWidth={sw * 0.9}
                    strokeLinecap="round"
                  />
                  <line
                    x1={a1.x2 - nx * bounds.span * 0.016}
                    y1={a1.y2 - ny * bounds.span * 0.016}
                    x2={a2.x2 - nx * bounds.span * 0.016}
                    y2={a2.y2 - ny * bounds.span * 0.016}
                    stroke={bondStroke}
                    strokeWidth={sw * 0.9}
                    strokeLinecap="round"
                  />
                </>
              ) : (
                <line x1={a1.x2} y1={a1.y2} x2={a2.x2} y2={a2.y2} stroke={bondStroke} strokeWidth={sw} strokeLinecap="round" />
              )}
            </g>
          );
        })}

        {/* Atoms */}
        {atoms.map((raw) => {
          const a = dragAtom && dragAtom.index === raw.index ? { ...raw, x2: dragAtom.x2, y2: dragAtom.y2 } : raw;
          const isSelected = selectedIndices.includes(a.index) || bondStartAtom === a.atom_id;
          const isCarbon = a.symbol === "C";
          const fontSize = Math.max(0.24, bounds.span * 0.036);
          const haloR = fontSize * 0.78;
          const col = `rgb(${a.color[0]},${a.color[1]},${a.color[2]})`;
          return (
            <g
              key={a.atom_id}
              className="cursor-pointer"
              onMouseDown={(e) => {
                if (e.button === 0 && activeTool === "select") {
                  e.stopPropagation();
                  setDragAtom({ atomId: a.atom_id, index: a.index, x2: a.x2, y2: a.y2, moved: false });
                }
              }}
              onClick={(e) => {
                e.stopPropagation();
                if (activeTool === "erase") {
                  onDeleteAtom(a.atom_id);
                  return;
                }
                if (activeTool === "atom") {
                  if (selectedIndices.includes(a.index) && a.atomic_num !== activeElementZ) {
                    onChangeElement(a.atom_id, activeElementZ);
                  } else {
                    onAddAtom({ atomic_num: activeElementZ, bond_to: a.atom_id });
                  }
                  return;
                }
                if (activeTool === "bond") {
                  if (bondStartAtom === null) {
                    setBondStartAtom(a.atom_id);
                  } else if (bondStartAtom === a.atom_id) {
                    setBondStartAtom(null);
                  } else {
                    onAddBond(bondStartAtom, a.atom_id);
                    setBondStartAtom(null);
                  }
                  return;
                }
                if (activeTool === "ring") {
                  onAddRing({ attach_to: a.atom_id });
                  return;
                }
                if (e.shiftKey) {
                  onSelectIndices(
                    isSelected ? selectedIndices.filter((x) => x !== a.index) : [...selectedIndices.slice(-2), a.index]
                  );
                } else {
                  onSelectIndices([a.index]);
                }
              }}
            >
              <circle cx={a.x2} cy={a.y2} r={haloR * 1.25} fill="transparent" />
              {isSelected && (
                <circle
                  cx={a.x2}
                  cy={a.y2}
                  r={haloR * 1.15}
                  fill="rgba(94, 234, 212, 0.24)"
                  stroke="#5eead4"
                  strokeWidth={haloR * 0.14}
                />
              )}
              {(!isCarbon || isSelected) && <circle cx={a.x2} cy={a.y2} r={haloR * 0.85} fill={paperBg} />}
              {(!isCarbon || isSelected) && (
                <text
                  x={a.x2}
                  y={a.y2}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontSize={fontSize}
                  fontWeight={700}
                  fontFamily="Inter, system-ui, sans-serif"
                  fill={isSelected ? "#5eead4" : col}
                >
                  {a.symbol}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {activeTool === "ring" && (
        <div
          className="absolute bottom-3 left-3 px-2.5 py-1 rounded-full text-[11px] mono-num"
          style={{
            background: "var(--md-sys-color-primary-container)",
            color: "var(--md-sys-color-primary)",
            border: "1px solid var(--md-sys-color-outline-strong)",
          }}
        >
          当前环模板: {activeRing.label}
        </div>
      )}
    </div>
  );
};
