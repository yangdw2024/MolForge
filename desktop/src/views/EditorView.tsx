import React, { useMemo, useRef, useState, useEffect } from "react";
import {
  BarChart3,
  Bot,
  ChevronDown,
  ChevronUp,
  Cpu,
  Hash,
  Layers,
  PanelRight,
  Puzzle,
  Ruler,
  Sparkles,
  Table,
} from "lucide-react";
import { molApi } from "../services/api";
import { DEFAULT_RING_TEMPLATES, useStudioStore } from "../store/useStudioStore";
import { Molecule2DCanvas } from "../components/editor/Molecule2DCanvas";
import { Viewport3D } from "../components/editor/Viewport3D";
import { PeriodicTableModal } from "../components/editor/PeriodicTableModal";
import { ChemicalToolRail } from "../components/editor/ChemicalToolRail";
import { FragmentsLayer } from "../components/layers/FragmentsLayer";
import { CoordinatesTableModal } from "../components/layers/CoordinatesTableModal";
import { CalculationSetupModal } from "../components/layers/CalculationSetupModal";
import { OrbitalLadderModal } from "../components/layers/OrbitalLadderModal";
import { AiCopilotLayer } from "../components/layers/AiCopilotLayer";

export const EditorView: React.FC = () => {
  const theme = useStudioStore((s) => s.theme);
  const summary = useStudioStore((s) => s.summary);
  const binary = useStudioStore((s) => s.binary);
  const atoms2d = useStudioStore((s) => s.atoms2d);
  const elements = useStudioStore((s) => s.elements);
  const fragments = useStudioStore((s) => s.fragments);

  const layoutMode = useStudioStore((s) => s.layoutMode);
  const setLayoutMode = useStudioStore((s) => s.setLayoutMode);
  const splitRatio = useStudioStore((s) => s.splitRatio);
  const setSplitRatio = useStudioStore((s) => s.setSplitRatio);

  const inspectorOpen = useStudioStore((s) => s.inspectorOpen);
  const setInspectorOpen = useStudioStore((s) => s.setInspectorOpen);
  const setAiDrawerOpen = useStudioStore((s) => s.setAiDrawerOpen);

  const selectedIndices = useStudioStore((s) => s.selectedIndices);
  const setSelectedIndices = useStudioStore((s) => s.setSelectedIndices);
  const activeTool = useStudioStore((s) => s.activeTool);
  const setActiveTool = useStudioStore((s) => s.setActiveTool);
  const activeElementZ = useStudioStore((s) => s.activeElementZ);
  const setActiveElementZ = useStudioStore((s) => s.setActiveElementZ);
  const activeRing = useStudioStore((s) => s.activeRing);
  const setActiveRing = useStudioStore((s) => s.setActiveRing);
  const activeFragmentId = useStudioStore((s) => s.activeFragmentId);
  const setActiveFragmentId = useStudioStore((s) => s.setActiveFragmentId);

  const reprMode = useStudioStore((s) => s.reprMode);
  const setReprMode = useStudioStore((s) => s.setReprMode);
  const atomScale = useStudioStore((s) => s.atomScale);
  const setAtomScale = useStudioStore((s) => s.setAtomScale);
  const bondScale = useStudioStore((s) => s.bondScale);
  const setBondScale = useStudioStore((s) => s.setBondScale);
  const showHydrogens = useStudioStore((s) => s.showHydrogens);
  const setShowHydrogens = useStudioStore((s) => s.setShowHydrogens);
  const showCell = useStudioStore((s) => s.showCell);
  const setShowCell = useStudioStore((s) => s.setShowCell);
  const showAxes = useStudioStore((s) => s.showAxes);
  const setShowAxes = useStudioStore((s) => s.setShowAxes);
  const showAtomIds = useStudioStore((s) => s.showAtomIds);
  const setShowAtomIds = useStudioStore((s) => s.setShowAtomIds);
  const fitNonce = useStudioStore((s) => s.fitNonce);
  const triggerFitCamera = useStudioStore((s) => s.triggerFitCamera);

  const periodicModalOpen = useStudioStore((s) => s.periodicModalOpen);
  const setPeriodicModalOpen = useStudioStore((s) => s.setPeriodicModalOpen);
  const openFilePath = useStudioStore((s) => s.openFilePath);
  const runTask = useStudioStore((s) => s.runTask);

  const [smilesInput, setSmilesInput] = useState("");
  const [toolLayerOpen, setToolLayerOpen] = useState(true);
  const [isCleaning, setIsCleaning] = useState(false);

  // Floating scientific HUD layer states
  const [fragmentsOpen, setFragmentsOpen] = useState(false);
  const [coordinatesOpen, setCoordinatesOpen] = useState(false);
  const [calculationOpen, setCalculationOpen] = useState(false);
  const [orbitalsOpen, setOrbitalsOpen] = useState(false);
  const [aiCopilotOpen, setAiCopilotOpen] = useState(false);
  const [topBarCollapsed, setTopBarCollapsed] = useState(false);

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (!detail) return;
      if (detail.layer === "fragments") setFragmentsOpen(true);
      else if (detail.layer === "coordinates") setCoordinatesOpen(true);
      else if (detail.layer === "calculation") setCalculationOpen(true);
      else if (detail.layer === "orbitals") setOrbitalsOpen(true);
      else if (detail.layer === "ai_copilot") setAiCopilotOpen(true);
    };
    window.addEventListener("open-hud-layer", handler);
    return () => window.removeEventListener("open-hud-layer", handler);
  }, []);

  const handleClean3D = async () => {
    setIsCleaning(true);
    try {
      await runTask("3D 力场几何优化", () => molApi.clean3D());
    } finally {
      setIsCleaning(false);
    }
  };

  // Spatial geometry measurement — 真实 3D 坐标（/api/atoms 的 x/y/z），非 2D 示意布局
  const measurementResult = useMemo(() => {
    if (!atoms2d?.atoms || selectedIndices.length < 2) return null;
    const pts = selectedIndices.map((i) => atoms2d.atoms[i]).filter(Boolean);
    const p3 = (a: (typeof pts)[number]) => [a.x, a.y, a.z] as [number, number, number];
    const sub = (u: number[], v: number[]) => [u[0] - v[0], u[1] - v[1], u[2] - v[2]];
    const dot = (u: number[], v: number[]) => u[0] * v[0] + u[1] * v[1] + u[2] * v[2];
    const cross = (u: number[], v: number[]) => [
      u[1] * v[2] - u[2] * v[1],
      u[2] * v[0] - u[0] * v[2],
      u[0] * v[1] - u[1] * v[0],
    ];
    const norm = (u: number[]) => Math.sqrt(dot(u, u));
    if (pts.length === 2) {
      const a = pts[0];
      const b = pts[1];
      const dist = norm(sub(p3(a), p3(b)));
      return {
        type: "distance",
        label: `距离 (${a.symbol}#${a.index}-${b.symbol}#${b.index})`,
        value: `${dist.toFixed(3)} Å`,
      };
    }
    if (pts.length === 3) {
      const a = pts[0];
      const b = pts[1];
      const c = pts[2];
      const v1 = sub(p3(a), p3(b));
      const v2 = sub(p3(c), p3(b));
      const m1 = norm(v1);
      const m2 = norm(v2);
      if (m1 > 0.001 && m2 > 0.001) {
        const cosTheta = Math.max(-1, Math.min(1, dot(v1, v2) / (m1 * m2)));
        const angleDeg = (Math.acos(cosTheta) * 180) / Math.PI;
        return {
          type: "angle",
          label: `键角 (${a.symbol}#${a.index}-${b.symbol}#${b.index}-${c.symbol}#${c.index})`,
          value: `${angleDeg.toFixed(1)}°`,
        };
      }
    }
    if (pts.length >= 4) {
      // 二面角：b1=b-a, b2=c-b, b3=d-c；n1=b1×b2, n2=b2×b3；符号由 (n1×n2)·b2 定
      const [a, b, c, d] = pts;
      const b1 = sub(p3(b), p3(a));
      const b2 = sub(p3(c), p3(b));
      const b3 = sub(p3(d), p3(c));
      const n1 = cross(b1, b2);
      const n2 = cross(b2, b3);
      const m1 = norm(n1);
      const m2 = norm(n2);
      const mb2 = norm(b2);
      if (m1 > 1e-6 && m2 > 1e-6 && mb2 > 1e-6) {
        const cosPhi = Math.max(-1, Math.min(1, dot(n1, n2) / (m1 * m2)));
        let phi = (Math.acos(cosPhi) * 180) / Math.PI;
        const sign = dot(cross(n1, n2), b2) < 0 ? -1 : 1;
        phi *= sign;
        const coplanar = Math.abs(Math.abs(phi) - 180) < 0.5 || Math.abs(phi) < 0.5;
        return {
          type: "dihedral",
          label: `二面角 (${a.symbol}#${a.index}-${b.symbol}#${b.index}-${c.symbol}#${c.index}-${d.symbol}#${d.index})`,
          value: `${phi.toFixed(2)}°${coplanar ? " (共平面)" : ""}`,
        };
      }
      return {
        type: "dihedral",
        label: `二面角 (${a.symbol}#${a.index}-${b.symbol}#${b.index}-${c.symbol}#${c.index}-${d.symbol}#${d.index})`,
        value: "共线原子，二面角无定义",
      };
    }
    return null;
  }, [atoms2d, selectedIndices]);

  const containerRef = useRef<HTMLDivElement | null>(null);

  return (
    <div
      data-testid="view-editor"
      ref={containerRef}
      className="relative h-full w-full overflow-hidden"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        const file = e.dataTransfer.files?.[0] as (File & { path?: string }) | undefined;
        if (file?.path) void openFilePath(file.path);
      }}
    >
      {/* 100% Full-Bleed 2D + 3D Split Canvas */}
      <div className="h-full w-full flex min-w-0 min-h-0">
        {layoutMode !== "3d" && (
          <div
            style={{ width: layoutMode === "split" ? `${splitRatio * 100}%` : "100%" }}
            className="h-full min-w-0"
          >
            <Molecule2DCanvas
              atoms={atoms2d?.atoms ?? []}
              bonds={atoms2d?.bonds ?? []}
              truncated={Boolean(atoms2d?.truncated)}
              totalAtoms={summary?.num_atoms ?? 0}
              selectedIndices={selectedIndices}
              onSelectIndices={setSelectedIndices}
              darkTheme={theme === "obsidian"}
              showAtomIds={showAtomIds}
              activeTool={activeTool}
              activeElementZ={activeElementZ}
              activeRing={activeRing}
              onAddAtom={(params) => void runTask("添加原子", () => molApi.addAtom(params))}
              onChangeElement={(aid, z) => void runTask("修改元素", () => molApi.changeElement(aid, z))}
              onAddBond={(a, b) => void runTask("新建化学键", () => molApi.addBond(a, b, 1))}
              onCycleBond={(bid) => void runTask("切换键级", () => molApi.cycleBondOrder(bid))}
              onSetBondOrder={(bid, order) => void runTask("设置键级", () => molApi.setBondOrder(bid, order))}
              onSetAtomCharge={(aid, q) => void runTask("设置原子电荷", () => molApi.setAtomCharge(aid, q))}
              onDeleteAtom={(aid) => void runTask("删除原子", () => molApi.deleteAtoms([aid]))}
              onDeleteBond={(bid) => void runTask("删除化学键", () => molApi.deleteBond(bid))}
              onAddRing={(params) =>
                void runTask("插入环系", () =>
                  molApi.addRing({
                    size: activeRing.size,
                    aromatic: activeRing.aromatic,
                    hetero: activeRing.hetero,
                    ...params,
                  })
                )
              }
              onInsertFragment={(anchorAtomId) =>
                void runTask("接枝 3D 片段", () =>
                  molApi.insertFragment({
                    fragment_id: activeFragmentId,
                    anchor_atom_id: anchorAtomId,
                    attach_to_existing: anchorAtomId !== undefined,
                  })
                )
              }
              onMoveAtom={(aid, p2) => void runTask("移动原子", () => molApi.moveAtom(aid, p2))}
              onClean3D={() => void handleClean3D()}
              onFitCamera={triggerFitCamera}
              onOpenPeriodicTable={() => setPeriodicModalOpen(true)}
            />
          </div>
        )}

        {layoutMode === "split" && (
          <div
            role="separator"
            aria-orientation="vertical"
            className="w-1 shrink-0 cursor-col-resize hover:bg-[var(--accent-primary)] transition-colors"
            style={{ backgroundColor: "var(--border-subtle)" }}
            onDoubleClick={() => setSplitRatio(0.45)}
            onMouseDown={() => {
              const onMove = (ev: MouseEvent) => {
                const rect = containerRef.current?.getBoundingClientRect();
                if (!rect) return;
                setSplitRatio((ev.clientX - rect.left) / Math.max(1, rect.width));
              };
              const onUp = () => {
                window.removeEventListener("mousemove", onMove);
                window.removeEventListener("mouseup", onUp);
              };
              window.addEventListener("mousemove", onMove);
              window.addEventListener("mouseup", onUp);
            }}
          />
        )}

        {layoutMode !== "2d" && (
          <div className="flex-1 h-full min-w-0">
            <Viewport3D
              data={binary}
              reprMode={reprMode}
              onChangeRepr={setReprMode}
              atomScale={atomScale}
              onChangeAtomScale={setAtomScale}
              bondScale={bondScale}
              onChangeBondScale={setBondScale}
              showHydrogens={showHydrogens}
              onToggleHydrogens={() => setShowHydrogens(!showHydrogens)}
              showCell={showCell}
              onToggleCell={() => setShowCell(!showCell)}
              showAxes={showAxes}
              onToggleAxes={() => setShowAxes(!showAxes)}
              darkTheme={theme === "obsidian"}
              selectedIndices={selectedIndices}
              onSelectIndices={setSelectedIndices}
              fitNonce={fitNonce}
              onFitCamera={triggerFitCamera}
            />
          </div>
        )}
      </div>

      {/* Unified Top Viewport Action Strip */}
      {topBarCollapsed ? (
        <div className="absolute top-2 left-3 z-20 pointer-events-auto">
          <button
            type="button"
            onClick={() => setTopBarCollapsed(false)}
            className="studio-btn !h-7 !px-3 rounded-full border backdrop-blur-xl flex items-center gap-1.5 text-[11px] font-medium shadow-lg"
            style={{
              backgroundColor: "color-mix(in srgb, var(--bg-secondary) 85%, transparent)",
              borderColor: "var(--border-subtle)",
              color: "var(--accent-primary)",
            }}
            title="展开工作区控制栏"
          >
            <span>展开控制栏</span>
            <ChevronDown size={12} />
          </button>
        </div>
      ) : (
        <div className="absolute top-2 left-2.5 right-2.5 z-20 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
          {/* Left Action Cluster: SMILES + Clean 3D + #ID + Measurement */}
          <div
            className="pointer-events-auto flex items-center gap-1.5 px-2 py-1 rounded-xl border backdrop-blur-2xl"
            style={{
              backgroundColor: "color-mix(in srgb, var(--bg-secondary) 88%, transparent)",
              borderColor: "var(--border-subtle)",
              boxShadow: "0 12px 32px rgba(0, 0, 0, 0.35)",
            }}
          >
            <form
              className="flex items-center gap-1"
              onSubmit={(e) => {
                e.preventDefault();
                const s = smilesInput.trim();
                if (!s) return;
                void runTask(`生成 ${s}`, () => molApi.buildSmiles(s, s));
                setSmilesInput("");
              }}
            >
              <input
                type="text"
                value={smilesInput}
                onChange={(e) => setSmilesInput(e.target.value)}
                placeholder="输入 SMILES 生成分子..."
                className="studio-input w-[135px] xl:w-[170px] mono-num !h-6.5 text-[11px]"
              />
              <button type="submit" className="studio-btn studio-btn-primary !h-6.5 !px-2.5 text-[11px]">
                生成
              </button>
            </form>

            <div className="h-4 border-r border-[var(--border-subtle)] mx-0.5" />

            <button
              type="button"
              onClick={() => void handleClean3D()}
              disabled={isCleaning}
              className="studio-btn !h-6.5 !px-2 text-[11px]"
              title="RDKit / 纯 Rust 3D 力场几何优化 (Ctrl+Shift+K)"
            >
              <Sparkles size={12} style={{ color: "var(--accent-primary)" }} className={isCleaning ? "animate-spin" : ""} />
              <span>3D 优化</span>
            </button>

            <button
              type="button"
              onClick={() => setShowAtomIds(!showAtomIds)}
              className="studio-btn !h-6.5 !px-2 text-[11px]"
              style={showAtomIds ? { borderColor: "var(--accent-primary)", color: "var(--accent-primary)" } : undefined}
              title="显隐原子序号 (#ID)"
            >
              <Hash size={11.5} />
              <span>#ID</span>
            </button>

            {measurementResult && (
              <div
                className="mono-num text-[11px] font-semibold px-2 py-0.5 rounded-lg border flex items-center gap-1.5"
                style={{
                  backgroundColor: "var(--accent-soft)",
                  borderColor: "var(--accent-primary)",
                  color: "var(--accent-primary)",
                }}
              >
                <Ruler size={12} />
                <span>
                  {measurementResult.label}: <strong>{measurementResult.value}</strong>
                </span>
              </div>
            )}
          </div>

          {/* Right HUD Tray Cluster: Viewport Mode + Scientific HUD Layers */}
          <div
            className="pointer-events-auto flex items-center gap-1 px-2 py-1 rounded-xl border backdrop-blur-2xl"
            style={{
              backgroundColor: "color-mix(in srgb, var(--bg-secondary) 88%, transparent)",
              borderColor: "var(--border-subtle)",
              boxShadow: "0 12px 32px rgba(0, 0, 0, 0.35)",
            }}
          >
            {/* Viewport Mode Switcher */}
            <div
              className="flex items-center p-0.5 rounded-lg"
              style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border-subtle)" }}
            >
              {(
                [
                  { id: "2d", label: "2D 画布" },
                  { id: "split", label: "2D+3D" },
                  { id: "3d", label: "3D 视口" },
                ] as const
              ).map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => setLayoutMode(opt.id)}
                  className="h-5.5 px-2 rounded-md text-[11px] font-medium cursor-pointer transition-colors"
                  style={{
                    backgroundColor: layoutMode === opt.id ? "var(--accent-primary)" : "transparent",
                    color: layoutMode === opt.id ? "var(--accent-contrast)" : "var(--text-secondary)",
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>

            <div className="h-4 border-r border-[var(--border-subtle)] mx-0.5" />

            {/* Scientific HUD Layer Triggers */}
            <button
              type="button"
              onClick={() => setToolLayerOpen((v) => !v)}
              className="studio-btn !h-6.5 !px-2 text-[11px]"
              style={toolLayerOpen ? { borderColor: "var(--accent-primary)", color: "var(--accent-primary)" } : undefined}
              title="显隐左侧化学工具栈"
            >
              <Layers size={11.5} />
              <span>工具</span>
            </button>

            <button
              type="button"
              onClick={() => setFragmentsOpen((v) => !v)}
              className="studio-btn !h-6.5 !px-2 text-[11px]"
              style={fragmentsOpen ? { borderColor: "var(--accent-primary)", color: "var(--accent-primary)" } : undefined}
              title="OSC 砌块与片段库 HUD"
            >
              <Puzzle size={11.5} style={{ color: "var(--accent-primary)" }} />
              <span>砌块库</span>
            </button>

            <button
              type="button"
              onClick={() => setCoordinatesOpen((v) => !v)}
              className="studio-btn !h-6.5 !px-2 text-[11px]"
              style={coordinatesOpen ? { borderColor: "var(--accent-primary)", color: "var(--accent-primary)" } : undefined}
              title="笛卡尔空间坐标表 HUD"
            >
              <Table size={11.5} />
              <span>坐标</span>
            </button>

            <button
              type="button"
              onClick={() => setCalculationOpen((v) => !v)}
              className="studio-btn !h-6.5 !px-2 text-[11px]"
              style={calculationOpen ? { borderColor: "var(--accent-primary)", color: "var(--accent-primary)" } : undefined}
              title="量子化学计算设置 HUD"
            >
              <Cpu size={11.5} />
              <span>计算</span>
            </button>

            <button
              type="button"
              onClick={() => setOrbitalsOpen((v) => !v)}
              className="studio-btn !h-6.5 !px-2 text-[11px]"
              style={orbitalsOpen ? { borderColor: "var(--accent-primary)", color: "var(--accent-primary)" } : undefined}
              title="前线轨道能级阶梯 HUD"
            >
              <BarChart3 size={11.5} />
              <span>能级</span>
            </button>

            <button
              type="button"
              onClick={() => setAiCopilotOpen((v) => !v)}
              className="studio-btn !h-6.5 !px-2 text-[11px]"
              style={aiCopilotOpen ? { borderColor: "var(--accent-primary)", color: "var(--accent-primary)" } : undefined}
              title="AI 科学计算副驾驶 HUD (DeepSeek)"
            >
              <Bot size={12} style={{ color: "var(--accent-primary)" }} />
              <span>AI</span>
            </button>

            <button
              type="button"
              onClick={() => {
                setAiDrawerOpen(false);
                setInspectorOpen(!inspectorOpen);
              }}
              className="studio-btn !h-6.5 !px-2 text-[11px]"
              style={inspectorOpen ? { borderColor: "var(--accent-primary)", color: "var(--accent-primary)" } : undefined}
              title="显隐右侧属性检查器"
            >
              <PanelRight size={11.5} />
              <span>属性</span>
            </button>

            <button
              type="button"
              onClick={() => setTopBarCollapsed(true)}
              className="studio-btn !h-6.5 !px-1.5"
              title="折叠顶部控制栏"
            >
              <ChevronUp size={11.5} />
            </button>
          </div>
        </div>
      )}

      {/* Sleek Left Chemical Tool Rail with Popover Drawers */}
      {toolLayerOpen && (
        <ChemicalToolRail
          activeTool={activeTool}
          setActiveTool={setActiveTool}
          activeElementZ={activeElementZ}
          setActiveElementZ={setActiveElementZ}
          activeRing={activeRing}
          setActiveRing={setActiveRing}
          activeFragmentId={activeFragmentId}
          setActiveFragmentId={setActiveFragmentId}
          elements={elements}
          fragments={fragments}
          ringTemplates={DEFAULT_RING_TEMPLATES}
          onOpenPeriodicTable={() => setPeriodicModalOpen(true)}
          onClean3D={() => void handleClean3D()}
          isCleaning={isCleaning}
        />
      )}

      <PeriodicTableModal
        open={periodicModalOpen}
        onClose={() => setPeriodicModalOpen(false)}
        elements={elements}
        activeElementZ={activeElementZ}
        selectedAtomCount={selectedIndices.length}
        onSelectElement={(z, replaceSelected) => {
          setActiveElementZ(z);
          if (replaceSelected && selectedIndices.length > 0 && atoms2d) {
            const aid = atoms2d.atoms[selectedIndices[0]]?.atom_id;
            if (typeof aid === "number") {
              void runTask("替换选中原子元素", () => molApi.changeElement(aid, z));
              return;
            }
          }
          setActiveTool("atom");
        }}
      />

      {/* Floating Scientific HUD Layers */}
      <FragmentsLayer isOpen={fragmentsOpen} onClose={() => setFragmentsOpen(false)} />
      <CoordinatesTableModal isOpen={coordinatesOpen} onClose={() => setCoordinatesOpen(false)} />
      <CalculationSetupModal isOpen={calculationOpen} onClose={() => setCalculationOpen(false)} />
      <OrbitalLadderModal isOpen={orbitalsOpen} onClose={() => setOrbitalsOpen(false)} />
      <AiCopilotLayer isOpen={aiCopilotOpen} onClose={() => setAiCopilotOpen(false)} />
    </div>
  );
};
