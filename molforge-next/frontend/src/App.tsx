import React, { useCallback, useEffect, useState } from "react";
import {
  Activity,
  Atom,
  CircleDot,
  Download,
  Eraser,
  FlaskConical,
  FolderOpen,
  Hexagon,
  Layers,
  Link2,
  ListTree,
  Moon,
  MousePointer,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Redo2,
  Search,
  Sparkles,
  Sun,
  Undo2,
  Wand2,
} from "lucide-react";
import { A2UICopilotPanel } from "./components/A2UICopilotPanel";
import { AnalysisScienceModal } from "./components/AnalysisScienceModal";
import { EnergyLadderModal } from "./components/EnergyLadderModal";
import { Molecule2DCanvas } from "./components/Molecule2DCanvas";
import { PeriodicTableModal } from "./components/PeriodicTableModal";
import { Viewport3D } from "./components/Viewport3D";
import type { EngineTelemetry } from "./engine/WebGPUMolEngine";
import { molApi } from "./services/api";
import type {
  Atom2DItem,
  BinaryMoleculeData,
  Bond2DItem,
  ChatMessage,
  DocumentSummary,
  EditTool,
  ElementInfo,
  RepresentationMode,
  RingTemplateSpec,
  ViewLayoutMode,
} from "./types/molforge";

const ELEMENTS_PALETTE: Array<{ z: number; sym: string; color: string }> = [
  { z: 6, sym: "C", color: "#859cb3" },
  { z: 7, sym: "N", color: "#529ef9" },
  { z: 8, sym: "O", color: "#f55c61" },
  { z: 16, sym: "S", color: "#f5d147" },
  { z: 9, sym: "F", color: "#5ce094" },
  { z: 17, sym: "Cl", color: "#4dd685" },
  { z: 35, sym: "Br", color: "#ad4738" },
  { z: 15, sym: "P", color: "#fa9e42" },
  { z: 5, sym: "B", color: "#f5ad80" },
  { z: 1, sym: "H", color: "#f2f7fc" },
];

const RING_TEMPLATES: RingTemplateSpec[] = [
  { id: "benzene", label: "苯环 (C₆ 芳香)", size: 6, aromatic: true },
  { id: "cyclohexane", label: "环己烷 (C₆ 饱和)", size: 6, aromatic: false },
  { id: "cyclopentadiene", label: "五元共轭环 (C₅)", size: 5, aromatic: true },
  { id: "thiophene", label: "噻吩环 (SC₄)", size: 5, aromatic: true, hetero: { 0: 16 } },
];

export const App: React.FC = () => {
  const [summary, setSummary] = useState<DocumentSummary | null>(null);
  const [binaryMol, setBinaryMol] = useState<BinaryMoleculeData | null>(null);
  const [atoms2d, setAtoms2d] = useState<Atom2DItem[]>([]);
  const [bonds2d, setBonds2d] = useState<Bond2DItem[]>([]);
  const [truncated2d, setTruncated2d] = useState(false);

  const [selectedIndices, setSelectedIndices] = useState<number[]>([]);
  const [reprMode, setReprMode] = useState<RepresentationMode>("ball_stick");
  const [layoutMode, setLayoutMode] = useState<ViewLayoutMode>("split");
  const [darkTheme, setDarkTheme] = useState(true);
  const [leftTab, setLeftTab] = useState<"build" | "presets" | "hierarchy">("build");
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);

  const [activeTool, setActiveTool] = useState<EditTool>("select");
  const [activeElementZ, setActiveElementZ] = useState<number>(6);
  const [activeRing, setActiveRing] = useState<RingTemplateSpec>(RING_TEMPLATES[0]);
  const [allElements, setAllElements] = useState<ElementInfo[]>([]);

  const [qcModalOpen, setQcModalOpen] = useState(false);
  const [analysisModalOpen, setAnalysisModalOpen] = useState(false);
  const [ptableModalOpen, setPtableModalOpen] = useState(false);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [openModal, setOpenModal] = useState(false);

  const [smilesInput, setSmilesInput] = useState("");
  const [filePathInput, setFilePathInput] = useState("E:\\YDW\\test_wsl\\ydw-PM6-ClFFCl.pdb");
  const [busyMsg, setBusyMsg] = useState<string | null>(null);
  const [telemetry, setTelemetry] = useState<EngineTelemetry>({
    backend: "WebGPU",
    gpuName: "Detecting GPU...",
    fps: 60,
    uploadMs: 0,
    drawMs: 0,
  });

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "欢迎使用 **MolForge Next**。左侧可切换分子绘图工具、预设材料库与结构树；支持 2D 交互画键/加环并实时同步 WebGPU 3D 视口。",
    },
  ]);
  const [aiLoading, setAiLoading] = useState(false);

  const refreshScene = useCallback(async () => {
    const [doc, bin, a2] = await Promise.all([
      molApi.getDocument(),
      molApi.getBinaryMolecule(),
      molApi.getAtoms2D(),
    ]);
    setSummary(doc);
    setBinaryMol(bin);
    setAtoms2d(a2.atoms);
    setBonds2d(a2.bonds);
    setTruncated2d(a2.truncated);
    setSelectedIndices([]);
    if (doc.num_atoms > 1500) {
      setLayoutMode("3d");
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const connectWithRetry = async () => {
      for (let attempt = 0; attempt < 25 && !cancelled; attempt++) {
        try {
          await refreshScene();
          void molApi.getElements().then((r) => setAllElements(r.elements)).catch(() => {});
          if (!cancelled) setBusyMsg(null);
          return;
        } catch {
          if (!cancelled && attempt >= 1) {
            setBusyMsg("正在连接 MolForge 化学计算引擎 (127.0.0.1:18765)...");
          }
          await new Promise((r) => setTimeout(r, 400));
        }
      }
      if (!cancelled) {
        setBusyMsg("未检测到本地化学引擎 (127.0.0.1:18765)，请通过 Launch_MolForge_Next.bat 启动。");
      }
    };
    void connectWithRetry();
    return () => {
      cancelled = true;
    };
  }, [refreshScene]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", darkTheme ? "dark" : "light");
  }, [darkTheme]);

  const runTask = async (label: string, fn: () => Promise<void>) => {
    setBusyMsg(label);
    try {
      await fn();
      await refreshScene();
      setBusyMsg(null);
    } catch (e) {
      setBusyMsg(`操作失败: ${e instanceof Error ? e.message : String(e)}`);
      setTimeout(() => setBusyMsg(null), 4000);
    }
  };

  const handleBuildSmiles = (e: React.FormEvent) => {
    e.preventDefault();
    const s = smilesInput.trim();
    if (!s) return;
    void runTask(`构建 SMILES: ${s}...`, async () => {
      await molApi.buildSmiles(s, s);
      setSmilesInput("");
    });
  };

  const handleNativeOpen = async () => {
    setBusyMsg("等待文件选择...");
    try {
      const res = await molApi.openFileDialog();
      if (res.cancelled) {
        setBusyMsg(null);
        return;
      }
      await refreshScene();
      setBusyMsg(null);
    } catch {
      setBusyMsg(null);
      setOpenModal(true);
    }
  };

  const handleExport = async (fmt: "pdb" | "xyz" | "mol" | "gjf" | "rest") => {
    setExportMenuOpen(false);
    try {
      const res = await molApi.exportFile(fmt);
      const blob = new Blob([res.content], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = res.filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setBusyMsg(`导出失败: ${String(e)}`);
      setTimeout(() => setBusyMsg(null), 3500);
    }
  };

  const handleSendPrompt = async (prompt: string) => {
    const userMsg: ChatMessage = { id: `u_${Date.now()}`, role: "user", content: prompt };
    setMessages((prev) => [...prev, userMsg]);
    setAiLoading(true);
    try {
      const res = await molApi.aiChat(prompt);
      setMessages((prev) => [
        ...prev,
        {
          id: `a_${Date.now()}`,
          role: "assistant",
          content: res.reply,
          a2uiBlocks: res.a2ui_blocks,
        },
      ]);
      if (summary?.revision !== res.document.revision) {
        await refreshScene();
      }
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { id: `e_${Date.now()}`, role: "assistant", content: `执行失败: ${String(e)}` },
      ]);
    } finally {
      setAiLoading(false);
    }
  };

  const handleA2UIAction = (action: string) => {
    if (action === "run_tb" || action === "open_qc_modal" || action === "open_qc_gjf") {
      setQcModalOpen(true);
    } else if (action === "clean_3d") {
      void runTask("正在优化 3D 几何构象...", async () => {
        await molApi.clean3D();
      });
    }
  };

  const handleDeleteSelected = () => {
    if (!selectedIndices.length) return;
    if (truncated2d) {
      void runTask("删除选中原子...", async () => {
        await molApi.deleteIndices(selectedIndices);
      });
      return;
    }
    const ids = selectedIndices
      .map((i) => atoms2d[i]?.atom_id)
      .filter((id): id is number => typeof id === "number");
    if (!ids.length) return;
    void runTask("删除选中原子...", async () => {
      await molApi.deleteAtoms(ids);
    });
  };

  return (
    <div className="w-screen h-screen flex flex-col overflow-hidden">
      {/* Slim Non-Wrapping Top Command Bar (48px) */}
      <header
        className="h-12 shrink-0 px-3 flex items-center justify-between gap-2.5"
        style={{
          background: "var(--md-sys-color-surface)",
          borderBottom: "1px solid var(--md-sys-color-outline)",
        }}
      >
        <div className="flex items-center gap-2 shrink-0">
          <div className="w-7 h-7 rounded-xl flex items-center justify-center shrink-0" style={{ background: "var(--md-sys-color-primary-container)" }}>
            <svg viewBox="0 0 24 24" className="w-4 h-4">
              <polygon points="12,2.5 20,7.2 20,16.8 12,21.5 4,16.8 4,7.2" fill="none" stroke="#5eead4" strokeWidth="1.8" />
              <circle cx="12" cy="12" r="2.6" fill="#5eead4" />
              <circle cx="12" cy="3" r="1.7" fill="#60a5fa" />
              <circle cx="19.5" cy="16.5" r="1.7" fill="#fb923c" />
            </svg>
          </div>
          <span className="text-sm font-semibold tracking-tight whitespace-nowrap">MolForge</span>
          <span
            className="text-[10px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap shrink-0"
            style={{ background: "var(--md-sys-color-primary-container)", color: "var(--md-sys-color-primary)" }}
          >
            NEXT
          </span>

          <div className="flex items-center gap-1 ml-1 shrink-0">
            <button
              onClick={() => void runTask("撤销...", async () => { await molApi.undo(); })}
              disabled={!summary?.can_undo}
              className="p-1.5 rounded-lg disabled:opacity-30 hover:bg-white/5 cursor-pointer"
              title="撤销"
            >
              <Undo2 className="w-4 h-4" />
            </button>
            <button
              onClick={() => void runTask("重做...", async () => { await molApi.redo(); })}
              disabled={!summary?.can_redo}
              className="p-1.5 rounded-lg disabled:opacity-30 hover:bg-white/5 cursor-pointer"
              title="重做"
            >
              <Redo2 className="w-4 h-4" />
            </button>
            <button
              onClick={() => void runTask("3D 力场几何整理...", async () => { await molApi.clean3D(); })}
              className="px-2 py-1 rounded-lg text-xs flex items-center gap-1 hover:bg-white/5 cursor-pointer whitespace-nowrap shrink-0"
              style={{ border: "1px solid var(--md-sys-color-outline)" }}
            >
              <Wand2 className="w-3.5 h-3.5" style={{ color: "var(--md-sys-color-primary)" }} />
              <span>3D优化</span>
            </button>
          </div>
        </div>

        {/* Center Generous SMILES Omnibar */}
        <form onSubmit={handleBuildSmiles} className="flex-1 max-w-md min-w-[200px]">
          <div
            className="flex items-center gap-2 rounded-full px-3 py-1"
            style={{ background: "var(--md-sys-color-surface-low)", border: "1px solid var(--md-sys-color-outline)" }}
          >
            <Search className="w-3.5 h-3.5 shrink-0" style={{ color: "var(--md-sys-color-on-surface-muted)" }} />
            <input
              value={smilesInput}
              onChange={(e) => setSmilesInput(e.target.value)}
              placeholder="输入 SMILES 生成分子 (如 c1ccccc1)..."
              className="flex-1 min-w-0 bg-transparent text-xs outline-none mono-num"
            />
            <button
              type="submit"
              className="text-[11px] font-medium px-2.5 py-0.5 rounded-full cursor-pointer whitespace-nowrap shrink-0"
              style={{ background: "var(--md-sys-color-primary)", color: "var(--md-sys-color-on-primary)" }}
            >
              生成
            </button>
          </div>
        </form>

        {/* Right Controls & GPU Telemetry */}
        <div className="flex items-center gap-1.5 shrink-0 relative">
          <div
            className="flex items-center p-0.5 rounded-xl text-[11px] shrink-0"
            style={{ background: "var(--md-sys-color-surface-low)", border: "1px solid var(--md-sys-color-outline)" }}
          >
            {(
              [
                ["3d", "3D"],
                ["split", "2D+3D"],
                ["2d", "2D"],
              ] as const
            ).map(([k, lbl]) => (
              <button
                key={k}
                onClick={() => setLayoutMode(k)}
                className="px-2 py-1 rounded-lg font-medium cursor-pointer whitespace-nowrap shrink-0"
                style={{
                  background: layoutMode === k ? "var(--md-sys-color-primary-container)" : "transparent",
                  color: layoutMode === k ? "var(--md-sys-color-primary)" : "var(--md-sys-color-on-surface-muted)",
                }}
              >
                {lbl}
              </button>
            ))}
          </div>

          <button
            onClick={() => void handleNativeOpen()}
            onContextMenu={(e) => {
              e.preventDefault();
              setOpenModal(true);
            }}
            title="点击打开系统文件选择器（右键可输入路径）"
            className="px-2.5 py-1 rounded-xl text-xs font-medium flex items-center gap-1 cursor-pointer whitespace-nowrap shrink-0"
            style={{ background: "var(--md-sys-color-surface-low)", border: "1px solid var(--md-sys-color-outline)" }}
          >
            <FolderOpen className="w-3.5 h-3.5" style={{ color: "var(--md-sys-color-secondary)" }} />
            <span>打开</span>
          </button>

          <div className="relative shrink-0">
            <button
              onClick={() => setExportMenuOpen((v) => !v)}
              className="px-2 py-1 rounded-xl text-xs font-medium flex items-center gap-1 cursor-pointer whitespace-nowrap shrink-0"
              style={{ background: "var(--md-sys-color-surface-low)", border: "1px solid var(--md-sys-color-outline)" }}
            >
              <Download className="w-3.5 h-3.5" />
              <span>导出</span>
            </button>
            {exportMenuOpen && (
              <div
                className="absolute right-0 top-9 w-36 rounded-2xl p-1.5 z-50 glass-pill flex flex-col gap-0.5 text-xs"
                style={{ border: "1px solid var(--md-sys-color-outline-strong)" }}
              >
                {(
                  [
                    ["pdb", "导出 .PDB"],
                    ["xyz", "导出 .XYZ"],
                    ["mol", "导出 .MOL"],
                    ["gjf", "导出 Gaussian .gjf"],
                    ["rest", "导出 REST ctrl.in"],
                  ] as const
                ).map(([fmt, label]) => (
                  <button
                    key={fmt}
                    onClick={() => void handleExport(fmt)}
                    className="text-left px-2.5 py-1.5 rounded-xl hover:bg-white/10 cursor-pointer"
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            onClick={() => setAnalysisModalOpen(true)}
            className="px-2 py-1 rounded-xl text-xs font-medium flex items-center gap-1 cursor-pointer whitespace-nowrap shrink-0"
            style={{ background: "var(--md-sys-color-surface-low)", border: "1px solid var(--md-sys-color-outline)" }}
            title="查看 MolForge 79 项科研分析平台"
          >
            <Activity className="w-3.5 h-3.5" style={{ color: "var(--md-sys-color-tertiary)" }} />
            <span>科研</span>
          </button>

          <button
            onClick={() => setQcModalOpen(true)}
            className="px-2.5 py-1 rounded-xl text-xs font-medium flex items-center gap-1 cursor-pointer whitespace-nowrap shrink-0"
            style={{ background: "var(--md-sys-color-primary-container)", color: "var(--md-sys-color-primary)" }}
          >
            <FlaskConical className="w-3.5 h-3.5" />
            <span>量化</span>
          </button>

          <div
            className="hidden xl:flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] mono-num whitespace-nowrap shrink-0"
            style={{ background: "var(--md-sys-color-surface-low)", border: "1px solid var(--md-sys-color-outline)" }}
            title={`上传 ${telemetry.uploadMs} ms · 绘制 ${telemetry.drawMs} ms`}
          >
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shrink-0" />
            <span>{telemetry.backend}</span>
            <span style={{ color: "var(--md-sys-color-on-surface-muted)" }}>·</span>
            <span style={{ color: "var(--md-sys-color-primary)" }}>{telemetry.fps} FPS</span>
          </div>

          <button
            onClick={() => setDarkTheme((d) => !d)}
            className="p-1.5 rounded-lg hover:bg-white/5 cursor-pointer shrink-0"
            title="切换深色观测台 / 学术纯白纸面"
          >
            {darkTheme ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>
        </div>
      </header>

      {/* Main Studio Body */}
      <div className="flex-1 flex min-h-0 relative">
        {/* Left Navigation Rail (52px) */}
        <nav
          className="w-13 shrink-0 flex flex-col items-center py-3 gap-2"
          style={{ background: "var(--md-sys-color-surface)", borderRight: "1px solid var(--md-sys-color-outline)" }}
        >
          {[
            { id: "build" as const, icon: CircleDot, label: "绘图与建模工具" },
            { id: "presets" as const, icon: Layers, label: "分子预设与 32万体系" },
            { id: "hierarchy" as const, icon: ListTree, label: "原子结构树" },
          ].map((item) => {
            const Icon = item.icon;
            const active = leftOpen && leftTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => {
                  if (leftOpen && leftTab === item.id) {
                    setLeftOpen(false);
                  } else {
                    setLeftTab(item.id);
                    setLeftOpen(true);
                  }
                }}
                title={item.label}
                className="w-9 h-9 rounded-xl flex items-center justify-center cursor-pointer"
                style={{
                  background: active ? "var(--md-sys-color-primary-container)" : "transparent",
                  color: active ? "var(--md-sys-color-primary)" : "var(--md-sys-color-on-surface-muted)",
                }}
              >
                <Icon className="w-4 h-4" />
              </button>
            );
          })}
          <div className="flex-1" />
          <button
            onClick={() => setLeftOpen((v) => !v)}
            className="w-9 h-9 rounded-xl flex items-center justify-center hover:bg-white/5 cursor-pointer"
            title="展开/折叠左侧栏"
          >
            {leftOpen ? <PanelLeftClose className="w-4 h-4" /> : <PanelLeftOpen className="w-4 h-4" />}
          </button>
          <button
            onClick={() => setRightOpen((v) => !v)}
            className="w-9 h-9 rounded-xl flex items-center justify-center hover:bg-white/5 cursor-pointer"
            title="展开/折叠右侧栏"
          >
            {rightOpen ? <PanelRightClose className="w-4 h-4" /> : <PanelRightOpen className="w-4 h-4" />}
          </button>
        </nav>

        {/* Left Expressive Drawer */}
        {leftOpen && (
          <aside
            className="w-60 shrink-0 h-full flex flex-col overflow-hidden"
            style={{ background: "var(--md-sys-color-surface-low)", borderRight: "1px solid var(--md-sys-color-outline)" }}
          >
            {leftTab === "build" ? (
              <div className="flex-1 overflow-y-auto p-3 space-y-4">
                <div>
                  <div className="text-[11px] font-semibold tracking-wider mb-2" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>
                    交互建模工具
                  </div>
                  <div className="grid grid-cols-2 gap-1.5">
                    {(
                      [
                        { id: "select", label: "选择 (V)", icon: MousePointer },
                        { id: "atom", label: "原子 (A)", icon: CircleDot },
                        { id: "bond", label: "建键 (B)", icon: Link2 },
                        { id: "ring", label: "加环 (R)", icon: Hexagon },
                        { id: "erase", label: "擦除 (E)", icon: Eraser },
                      ] as const
                    ).map((tool) => {
                      const Icon = tool.icon;
                      const active = activeTool === tool.id;
                      return (
                        <button
                          key={tool.id}
                          onClick={() => setActiveTool(tool.id)}
                          className="px-2.5 py-2 rounded-xl text-xs font-medium flex items-center gap-1.5 cursor-pointer"
                          style={{
                            background: active ? "var(--md-sys-color-primary-container)" : "rgba(255,255,255,0.03)",
                            color: active ? "var(--md-sys-color-primary)" : "var(--md-sys-color-on-surface)",
                            border: `1px solid ${active ? "var(--md-sys-color-outline-strong)" : "var(--md-sys-color-outline)"}`,
                          }}
                        >
                          <Icon className="w-3.5 h-3.5" />
                          <span>{tool.label}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[11px] font-semibold tracking-wider" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>
                      活动元素
                    </span>
                    <span className="text-[11px] mono-num font-semibold" style={{ color: "var(--md-sys-color-primary)" }}>
                      {allElements.find((e) => e.atomic_number === activeElementZ)
                        ? `#${activeElementZ} ${allElements.find((e) => e.atomic_number === activeElementZ)!.symbol} (${allElements.find((e) => e.atomic_number === activeElementZ)!.name_cn})`
                        : `Z=${activeElementZ}`}
                    </span>
                  </div>
                  <div className="grid grid-cols-5 gap-1.5">
                    {ELEMENTS_PALETTE.map((el) => {
                      const active = activeElementZ === el.z;
                      return (
                        <button
                          key={el.z}
                          onClick={() => {
                            setActiveElementZ(el.z);
                            if (activeTool === "select" || activeTool === "erase") {
                              setActiveTool("atom");
                            }
                          }}
                          className="py-1.5 rounded-xl text-xs font-bold mono-num cursor-pointer"
                          style={{
                            background: active ? "var(--md-sys-color-primary-container)" : "rgba(255,255,255,0.03)",
                            color: active ? "var(--md-sys-color-primary)" : el.color,
                            border: `1px solid ${active ? "var(--md-sys-color-outline-strong)" : "var(--md-sys-color-outline)"}`,
                          }}
                        >
                          {el.sym}
                        </button>
                      );
                    })}
                  </div>
                  <button
                    onClick={() => setPtableModalOpen(true)}
                    className="w-full mt-2 py-1.5 px-2.5 rounded-xl text-xs font-medium cursor-pointer flex items-center justify-center gap-1.5"
                    style={{
                      background: "rgba(255,255,255,0.04)",
                      border: "1px solid var(--md-sys-color-outline)",
                      color: "var(--md-sys-color-primary)",
                    }}
                  >
                    <Atom className="w-3.5 h-3.5" />
                    完整 118 元素周期表...
                  </button>
                </div>

                <div>
                  <div className="text-[11px] font-semibold tracking-wider mb-2" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>
                    常用环模板 (点选后点击画布)
                  </div>
                  <div className="space-y-1.5">
                    {RING_TEMPLATES.map((rt) => {
                      const active = activeTool === "ring" && activeRing.id === rt.id;
                      return (
                        <button
                          key={rt.id}
                          onClick={() => {
                            setActiveRing(rt);
                            setActiveTool("ring");
                          }}
                          className="w-full text-left px-3 py-2 rounded-xl text-xs cursor-pointer"
                          style={{
                            background: active ? "var(--md-sys-color-primary-container)" : "rgba(255,255,255,0.03)",
                            color: active ? "var(--md-sys-color-primary)" : "var(--md-sys-color-on-surface)",
                            border: `1px solid ${active ? "var(--md-sys-color-outline-strong)" : "var(--md-sys-color-outline)"}`,
                          }}
                        >
                          {rt.label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="pt-2" style={{ borderTop: "1px solid var(--md-sys-color-outline)" }}>
                  <button
                    onClick={() =>
                      void runTask("加载 321,554 原子 PM6-ClFFCl 体系...", async () => {
                        await molApi.openFile("E:\\YDW\\test_wsl\\ydw-PM6-ClFFCl.pdb");
                      })
                    }
                    className="w-full rounded-2xl p-2.5 text-left cursor-pointer"
                    style={{ background: "var(--md-sys-color-primary-container)", border: "1px solid var(--md-sys-color-outline-strong)" }}
                  >
                    <div className="text-xs font-semibold flex items-center gap-1.5" style={{ color: "var(--md-sys-color-primary)" }}>
                      <Sparkles className="w-3.5 h-3.5" />
                      32万原子 WebGPU 压测
                    </div>
                    <div className="text-[10px] mt-0.5" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>
                      加载 ydw-PM6-ClFFCl.pdb 与周期盒
                    </div>
                  </button>
                </div>
              </div>
            ) : leftTab === "presets" ? (
              <div className="flex-1 overflow-y-auto p-3 space-y-2">
                <div className="text-[11px] font-semibold tracking-wider px-1" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>
                  分子原型与 OSC 材料库
                </div>
                {(summary?.presets || []).map((p) => (
                  <button
                    key={p.id}
                    onClick={() => void runTask(`加载 ${p.name}...`, async () => { await molApi.loadPreset(p.id); })}
                    className="w-full text-left rounded-2xl p-2.5 cursor-pointer hover:bg-white/5"
                    style={{ background: "rgba(255,255,255,0.03)", border: "1px solid var(--md-sys-color-outline)" }}
                  >
                    <div className="text-xs font-medium">{p.label}</div>
                    <div className="text-[10px] mt-1 flex items-center justify-between" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>
                      <span>{p.category}</span>
                      <span className="mono-num truncate max-w-[105px]">{p.smiles}</span>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto p-3">
                <div className="text-[11px] font-semibold tracking-wider mb-2" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>
                  原子拓扑序列 ({atoms2d.length})
                </div>
                {truncated2d ? (
                  <div className="text-xs p-3 rounded-xl" style={{ color: "var(--md-sys-color-on-surface-muted)", background: "rgba(0,0,0,0.2)" }}>
                    大体系 ({summary?.num_atoms.toLocaleString()} 原子) 已隐藏逐原子文本列表以维持渲染性能。
                  </div>
                ) : (
                  <div className="space-y-1">
                    {atoms2d.map((a) => {
                      const sel = selectedIndices.includes(a.index);
                      return (
                        <button
                          key={a.atom_id}
                          onClick={() => setSelectedIndices([a.index])}
                          className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-xl text-xs cursor-pointer"
                          style={{
                            background: sel ? "var(--md-sys-color-primary-container)" : "transparent",
                            color: sel ? "var(--md-sys-color-primary)" : "var(--md-sys-color-on-surface)",
                          }}
                        >
                          <span className="flex items-center gap-2 font-medium">
                            <Atom className="w-3 h-3" />
                            #{a.display_id} {a.symbol}
                          </span>
                          <span className="mono-num text-[10px]" style={{ color: "var(--md-sys-color-on-surface-muted)" }}>
                            {a.x.toFixed(2)}, {a.y.toFixed(2)}, {a.z.toFixed(2)}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </aside>
        )}

        {/* Center Dual / WebGPU Stage */}
        <main className="flex-1 flex min-w-0 min-h-0 relative">
          {(layoutMode === "split" || layoutMode === "2d") && (
            <div
              className={layoutMode === "split" ? "w-[42%] h-full" : "w-full h-full"}
              style={{ borderRight: layoutMode === "split" ? "1px solid var(--md-sys-color-outline)" : "none" }}
            >
              <Molecule2DCanvas
                atoms={atoms2d}
                bonds={bonds2d}
                truncated={truncated2d}
                totalAtoms={summary?.num_atoms || 0}
                selectedIndices={selectedIndices}
                onSelectIndices={setSelectedIndices}
                darkTheme={darkTheme}
                activeTool={activeTool}
                activeElementZ={activeElementZ}
                activeRing={activeRing}
                onAddAtom={(params) => void runTask("添加原子...", async () => { await molApi.addAtom(params); })}
                onChangeElement={(aid, z) => void runTask("更改元素...", async () => { await molApi.changeElement(aid, z); })}
                onAddBond={(a, b) => void runTask("添加化学键...", async () => { await molApi.addBond(a, b, 1); })}
                onCycleBond={(bid) => void runTask("切换键级...", async () => { await molApi.cycleBondOrder(bid); })}
                onDeleteAtom={(aid) => void runTask("删除原子...", async () => { await molApi.deleteAtoms([aid]); })}
                onDeleteBond={(bid) => void runTask("删除化学键...", async () => { await molApi.deleteBond(bid); })}
                onAddRing={(params) =>
                  void runTask(`添加${activeRing.label}...`, async () => {
                    await molApi.addRing({
                      size: activeRing.size,
                      aromatic: activeRing.aromatic,
                      hetero: activeRing.hetero,
                      ...params,
                    });
                  })
                }
                onMoveAtom={(aid, p2) => void runTask("移动原子...", async () => { await molApi.moveAtom(aid, p2); })}
              />
            </div>
          )}

          {(layoutMode === "split" || layoutMode === "3d") && (
            <Viewport3D
              molecule={binaryMol}
              summary={summary}
              atoms2d={atoms2d}
              selectedIndices={selectedIndices}
              onSelectIndices={setSelectedIndices}
              mode={reprMode}
              onModeChange={setReprMode}
              darkTheme={darkTheme}
              activeTool={activeTool}
              onEraseIndex={(idx) => void runTask("删除选中原子...", async () => { await molApi.deleteIndices([idx]); })}
              onSproutIndex={(idx) => {
                const aid = atoms2d[idx]?.atom_id;
                if (typeof aid === "number") {
                  void runTask("连接新原子...", async () => {
                    await molApi.addAtom({ atomic_num: activeElementZ, bond_to: aid });
                  });
                }
              }}
              onTelemetry={setTelemetry}
            />
          )}

          {busyMsg && (
            <div
              className="absolute top-20 left-1/2 -translate-x-1/2 glass-pill rounded-full px-4 py-1.5 text-xs font-medium z-30 whitespace-nowrap"
              style={{ color: "var(--md-sys-color-primary)" }}
            >
              {busyMsg}
            </div>
          )}
        </main>

        {/* Right Inspector & A2UI Copilot */}
        {rightOpen && (
          <A2UICopilotPanel
            summary={summary}
            atoms2d={atoms2d}
            selectedIndices={selectedIndices}
            messages={messages}
            aiLoading={aiLoading}
            onSendPrompt={handleSendPrompt}
            onClearMessages={() =>
              setMessages([
                {
                  id: `clean_${Date.now()}`,
                  role: "assistant",
                  content: `对话已重置。当前活动体系：**${summary?.name || "Untitled"}**（\`${summary?.formula || ""}\`）。`,
                },
              ])
            }
            onAction={handleA2UIAction}
            onDeleteSelected={handleDeleteSelected}
            onSetChargeSpin={(q, m) => void runTask("更新电荷/自旋...", async () => { await molApi.setChargeSpin(q, m); })}
          />
        )}
      </div>

      {/* Fallback Open File Modal */}
      {openModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-6" style={{ background: "rgba(3,7,12,0.72)", backdropFilter: "blur(6px)" }}>
          <div className="w-full max-w-lg rounded-3xl p-5 space-y-4" style={{ background: "var(--md-sys-color-surface)", border: "1px solid var(--md-sys-color-outline-strong)" }}>
            <div className="text-sm font-semibold">输入分子结构路径 (.pdb / .xyz / .mol / .sdf / .cif / .mforge)</div>
            <input
              value={filePathInput}
              onChange={(e) => setFilePathInput(e.target.value)}
              className="w-full px-3 py-2 rounded-xl text-xs mono-num outline-none"
              style={{ background: "var(--md-sys-color-surface-low)", border: "1px solid var(--md-sys-color-outline)" }}
            />
            <div className="flex justify-end gap-2">
              <button onClick={() => setOpenModal(false)} className="px-3.5 py-1.5 rounded-xl text-xs cursor-pointer" style={{ border: "1px solid var(--md-sys-color-outline)" }}>
                取消
              </button>
              <button
                onClick={() => {
                  const p = filePathInput.trim();
                  setOpenModal(false);
                  if (p) {
                    void runTask(`解析 ${p}...`, async () => {
                      await molApi.openFile(p);
                    });
                  }
                }}
                className="px-4 py-1.5 rounded-xl text-xs font-semibold cursor-pointer"
                style={{ background: "var(--md-sys-color-primary)", color: "var(--md-sys-color-on-primary)" }}
              >
                立即解析并渲染
              </button>
            </div>
          </div>
        </div>
      )}

      <EnergyLadderModal open={qcModalOpen} onClose={() => setQcModalOpen(false)} summary={summary} />
      <AnalysisScienceModal open={analysisModalOpen} onClose={() => setAnalysisModalOpen(false)} />
      <PeriodicTableModal
        open={ptableModalOpen}
        onClose={() => setPtableModalOpen(false)}
        elements={allElements}
        activeElementZ={activeElementZ}
        selectedAtomCount={truncated2d ? 0 : selectedIndices.length}
        onSelectElement={(z, replaceSelected) => {
          setActiveElementZ(z);
          if (replaceSelected && !truncated2d && selectedIndices.length > 0) {
            void runTask("替换选中原子元素...", async () => {
              for (const idx of selectedIndices) {
                const aid = atoms2d[idx]?.atom_id;
                if (typeof aid === "number") {
                  await molApi.changeElement(aid, z);
                }
              }
            });
          } else if (activeTool === "select" || activeTool === "erase") {
            setActiveTool("atom");
          }
        }}
      />
    </div>
  );
};

export default App;
