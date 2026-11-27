import { create } from "zustand";
import { molApi } from "../services/api";
import type {
  AnalysisCatalogItem,
  AnalysisRunResult,
  Atoms2DPayload,
  BinaryMoleculeData,
  CalChemRunResult,
  ChatMessage,
  DocumentSummary,
  EditTool,
  ElementInfo,
  ExternalEngineStatus,
  FragmentInfo,
  GromacsPipelineResult,
  LibraryMoleculeEntry,
  MultiwfnRunResult,
  NavRoute,
  QcParsedOrbitalResult,
  RecentAnalysisRecord,
  RecentProjectEntry,
  RepresentationMode,
  RingTemplateSpec,
  StudioJob,
  StudioNotification,
  StudioTheme,
  SystemTelemetry,
  TightBindingResult,
  ViewLayoutMode,
} from "../types/studio";

export const DEFAULT_RING_TEMPLATES: RingTemplateSpec[] = [
  { id: "benzene", label: "苯环 (C₆ 芳香)", size: 6, aromatic: true },
  { id: "cyclohexane", label: "环己烷 (C₆ 饱和)", size: 6, aromatic: false },
  { id: "cp", label: "五元共轭环 (C₅)", size: 5, aromatic: true },
  { id: "thiophene", label: "噻吩环 (SC₄)", size: 5, aromatic: true, hetero: { 0: 16 } },
];

function applyDomTheme(theme: StudioTheme, reducedMotion: boolean, density: "compact" | "comfortable") {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.setAttribute("data-theme", theme);
  root.setAttribute("data-reduced-motion", reducedMotion ? "true" : "false");
  root.setAttribute("data-density", density);
}

function nowTimeStr(): string {
  return new Date().toLocaleTimeString("zh-CN", { hour12: false });
}

export interface StudioStoreState {
  initialized: boolean;
  busyLabel: string | null;
  theme: StudioTheme;
  reducedMotion: boolean;
  uiDensity: "compact" | "comfortable";
  activeRoute: NavRoute;
  navExpanded: boolean;
  showNavRail: boolean;
  inspectorOpen: boolean;
  inspectorWidth: number;
  layoutMode: ViewLayoutMode;
  splitRatio: number;
  autosaveEnabled: boolean;

  bridgeConnected: boolean;
  bridgeVersion: string;
  telemetry: SystemTelemetry | null;

  projectPath: string | null;
  lastSavedRev: number;
  isDirty: boolean;
  recoveryPrompt: {
    available: boolean;
    name?: string;
    formula?: string;
    savedAt?: string;
    base64Data?: string;
  } | null;

  summary: DocumentSummary | null;
  binary: BinaryMoleculeData | null;
  atoms2d: Atoms2DPayload | null;

  elements: ElementInfo[];
  fragments: FragmentInfo[];
  libraryItems: LibraryMoleculeEntry[];
  customLibraryItems: LibraryMoleculeEntry[];

  analysisCatalog: AnalysisCatalogItem[];
  lastAnalysisResult: AnalysisRunResult | null;
  tbResult: TightBindingResult | null;
  qcParsed: QcParsedOrbitalResult | null;
  enginesStatus: ExternalEngineStatus[];
  calchemBasisSets: string[];
  calchemResult: CalChemRunResult | null;
  multiwfnResult: MultiwfnRunResult | null;
  gromacsResult: GromacsPipelineResult | null;

  jobs: StudioJob[];
  notifications: StudioNotification[];
  toasts: StudioNotification[];
  recentProjects: RecentProjectEntry[];
  recentAnalyses: RecentAnalysisRecord[];

  selectedIndices: number[];
  activeTool: EditTool;
  activeElementZ: number;
  activeRing: RingTemplateSpec;
  activeFragmentId: string;

  reprMode: RepresentationMode;
  atomScale: number;
  bondScale: number;
  showHydrogens: boolean;
  showCell: boolean;
  showAxes: boolean;
  showAtomIds: boolean;
  fitNonce: number;

  commandPaletteOpen: boolean;
  periodicModalOpen: boolean;
  notificationsOpen: boolean;
  aiDrawerOpen: boolean;
  messages: ChatMessage[];
  aiLoading: boolean;

  initWorkspace: () => Promise<void>;
  refreshScene: () => Promise<void>;
  syncExternalChanges: () => Promise<void>;
  refreshTelemetry: () => Promise<void>;
  refreshJobs: () => Promise<void>;
  refreshEngines: () => Promise<void>;

  setRoute: (route: NavRoute) => void;
  setTheme: (theme: StudioTheme) => void;
  toggleTheme: () => void;
  setReducedMotion: (v: boolean) => void;
  setUiDensity: (d: "compact" | "comfortable") => void;
  setNavExpanded: (v: boolean) => void;
  setShowNavRail: (v: boolean) => void;
  setInspectorOpen: (v: boolean) => void;
  setInspectorWidth: (w: number) => void;
  setLayoutMode: (m: ViewLayoutMode) => void;
  setSplitRatio: (r: number) => void;
  setAutosaveEnabled: (v: boolean) => void;
  resetWorkspaceLayout: () => void;

  setSelectedIndices: (indices: number[]) => void;
  setActiveTool: (t: EditTool) => void;
  setActiveElementZ: (z: number) => void;
  setActiveRing: (r: RingTemplateSpec) => void;
  setActiveFragmentId: (id: string) => void;
  setReprMode: (m: RepresentationMode) => void;
  setAtomScale: (v: number) => void;
  setBondScale: (v: number) => void;
  setShowHydrogens: (v: boolean) => void;
  setShowCell: (v: boolean) => void;
  setShowAxes: (v: boolean) => void;
  setShowAtomIds: (v: boolean) => void;
  triggerFitCamera: () => void;

  setCommandPaletteOpen: (v: boolean) => void;
  setPeriodicModalOpen: (v: boolean) => void;
  setNotificationsOpen: (v: boolean) => void;
  setAiDrawerOpen: (v: boolean) => void;

  pushNotification: (level: StudioNotification["level"], title: string, detail?: string) => void;
  dismissToast: (id: string) => void;
  runTask: <T>(label: string, fn: () => Promise<T>, switchToEditor?: boolean) => Promise<T | undefined>;

  openStructureDialog: () => Promise<void>;
  openProjectDialog: () => Promise<void>;
  openFilePath: (filePath: string) => Promise<void>;
  saveProject: (saveAs?: boolean) => Promise<void>;
  restoreAutosave: () => Promise<void>;
  dismissAutosave: () => Promise<void>;
  runAutosaveSnapshot: () => Promise<void>;

  addCustomLibraryItems: (items: LibraryMoleculeEntry[]) => void;
  runAndRecordAnalysis: (analysisId: string) => Promise<AnalysisRunResult | undefined>;
  runTightBinding: () => Promise<TightBindingResult | undefined>;
  submitBackgroundJob: (kind: string, label: string, params?: Record<string, unknown>) => Promise<void>;
  cancelBackgroundJob: (jobId: string) => Promise<void>;
  sendAiPrompt: (prompt: string) => Promise<void>;
}

function persistStatePatch(patch: Record<string, unknown>) {
  void window.molforgeDesktop?.workspace.saveStudioState(patch);
}

export const useStudioStore = create<StudioStoreState>((set, get) => ({
  initialized: false,
  busyLabel: null,
  theme: "obsidian",
  reducedMotion: false,
  uiDensity: "compact",
  activeRoute: "overview",
  navExpanded: false,
  showNavRail: true,
  inspectorOpen: false,
  inspectorWidth: 320,
  layoutMode: "split",
  splitRatio: 0.44,
  autosaveEnabled: true,

  bridgeConnected: false,
  bridgeVersion: "Offline",
  telemetry: null,

  projectPath: null,
  lastSavedRev: 0,
  isDirty: false,
  recoveryPrompt: null,

  summary: null,
  binary: null,
  atoms2d: null,

  elements: [],
  fragments: [],
  libraryItems: [],
  customLibraryItems: [],

  analysisCatalog: [],
  lastAnalysisResult: null,
  tbResult: null,
  qcParsed: null,
  enginesStatus: [],
  calchemBasisSets: ["sto-3g", "6-31g", "6-31g(d)"],
  calchemResult: null,
  multiwfnResult: null,
  gromacsResult: null,

  jobs: [],
  notifications: [],
  toasts: [],
  recentProjects: [],
  recentAnalyses: [],

  selectedIndices: [],
  activeTool: "select",
  activeElementZ: 6,
  activeRing: DEFAULT_RING_TEMPLATES[0],
  activeFragmentId: "methyl",

  reprMode: "ball_stick",
  atomScale: 1.0,
  bondScale: 1.0,
  showHydrogens: true,
  showCell: true,
  showAxes: true,
  showAtomIds: false,
  fitNonce: 0,

  commandPaletteOpen: false,
  periodicModalOpen: false,
  notificationsOpen: false,
  aiDrawerOpen: false,
  messages: [
    {
      id: "welcome",
      role: "assistant",
      content:
        "欢迎使用 **MolForge Studio**。我已挂载本地化学引擎与实时紧束缚轨道求解器，可直接为您解析分子结构、搭建体系或生成 Gaussian / REST 计算输入。",
    },
  ],
  aiLoading: false,

  pushNotification: (level, title, detail) => {
    const entry: StudioNotification = {
      id: `n_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
      level,
      title,
      detail,
      timestamp: nowTimeStr(),
    };
    set((s) => ({ notifications: [entry, ...s.notifications].slice(0, 40) }));
    // 即时 toast：失败/成功/警告必须当场可见，不能只进铃铛抽屉
    if (level !== "info") {
      set((s) => ({ toasts: [...s.toasts, entry].slice(-4) }));
      const ttl = level === "error" ? 8000 : 4000;
      setTimeout(() => {
        set((s) => ({ toasts: s.toasts.filter((t) => t.id !== entry.id) }));
      }, ttl);
    }
  },

  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),

  initWorkspace: async () => {
    if (get().initialized) return;
    if (window.molforgeDesktop) {
      try {
        const saved = await window.molforgeDesktop.workspace.loadStudioState();
        applyDomTheme(saved.theme, saved.reducedMotion, saved.uiDensity);
        set({
          theme: saved.theme,
          reducedMotion: saved.reducedMotion,
          uiDensity: saved.uiDensity,
          navExpanded: saved.navExpanded,
          layoutMode: saved.layoutMode,
          inspectorWidth: saved.inspectorWidth || 320,
          splitRatio: saved.splitRatio || 0.44,
          autosaveEnabled: saved.autosaveEnabled ?? true,
          recentProjects: saved.recentProjects ?? [],
          recentAnalyses: saved.recentAnalyses ?? [],
          customLibraryItems: saved.libraryCustomMolecules ?? [],
        });

        const auto = await window.molforgeDesktop.workspace.loadAutosave();
        if (auto.available && auto.base64Data) {
          set({
            recoveryPrompt: {
              available: true,
              name: auto.meta?.name,
              formula: auto.meta?.formula,
              savedAt: auto.meta?.savedAt,
              base64Data: auto.base64Data,
            },
          });
        }
      } catch (err) {
        get().pushNotification("warning", "本地配置恢复降级为默认设置", String(err));
      }
    } else {
      applyDomTheme("obsidian", false, "compact");
    }

    await get().refreshTelemetry();

    try {
      const [health, els, frags, lib, cat, jobsRes, engRes] = await Promise.all([
        molApi.health(),
        molApi.getElements(),
        molApi.getFragments(),
        molApi.getLibraryPresets(),
        molApi.getAnalysisCatalog(),
        molApi.listJobs(),
        molApi.getEnginesStatus(),
      ]);
      set({
        bridgeConnected: health.ok,
        bridgeVersion: health.version,
        elements: els.elements,
        fragments: frags.fragments,
        libraryItems: lib.items,
        analysisCatalog: cat.items,
        jobs: jobsRes.jobs,
        enginesStatus: engRes.engines,
        calchemBasisSets: engRes.calchem_basis_sets,
        lastSavedRev: health.document.revision,
      });
      await get().refreshScene();
      set({ initialized: true });
    } catch (err) {
      set({ bridgeConnected: false, initialized: true });
      get().pushNotification("error", "化学计算引擎尚未连接", String(err));
    }
  },

  refreshScene: async () => {
    try {
      const [doc, bin, a2] = await Promise.all([
        molApi.getDocument(),
        molApi.getBinaryMolecule(),
        molApi.getAtoms2D(),
      ]);
      const cat = await molApi.getAnalysisCatalog();
      const savedRev = get().lastSavedRev;
      set({
        summary: doc,
        binary: bin,
        atoms2d: a2,
        analysisCatalog: cat.items,
        bridgeConnected: true,
        isDirty: doc.revision !== savedRev,
        selectedIndices: [],
      });
    } catch (err) {
      set({ bridgeConnected: false });
      get().pushNotification("error", "刷新分子数据失败", String(err));
    }
  },

  // 服务端文档可能被外部客户端/API 改变（多客户端同步）：轮询 revision，变了才真刷新，
  // 避免画布/上下文停留在旧分子上（悬停热键、测量、AI 上下文全部依赖最新原子表）。
  syncExternalChanges: async () => {
    try {
      const doc = await molApi.getDocument();
      const cur = get().summary;
      if (!cur || doc.revision !== cur.revision) {
        await get().refreshScene();
      }
    } catch {
      // 断连时忽略，StatusBar 另有离线提示
    }
  },

  refreshTelemetry: async () => {
    if (!window.molforgeDesktop) return;
    try {
      const telemetry = await window.molforgeDesktop.system.getTelemetry();
      set({ telemetry });
    } catch {
      // ignore telemetry probe failure
    }
  },

  refreshJobs: async () => {
    try {
      const res = await molApi.listJobs();
      set({ jobs: res.jobs });
    } catch {
      // ignore if disconnected
    }
  },

  refreshEngines: async () => {
    try {
      const res = await molApi.getEnginesStatus();
      set({ enginesStatus: res.engines, calchemBasisSets: res.calchem_basis_sets });
    } catch {
      // ignore if disconnected
    }
  },

  setRoute: (route) => set({ activeRoute: route }),
  setTheme: (theme) => {
    applyDomTheme(theme, get().reducedMotion, get().uiDensity);
    set({ theme });
    persistStatePatch({ theme });
  },
  toggleTheme: () => {
    const next: StudioTheme = get().theme === "obsidian" ? "arctic" : "obsidian";
    get().setTheme(next);
  },
  setReducedMotion: (v) => {
    applyDomTheme(get().theme, v, get().uiDensity);
    set({ reducedMotion: v });
    persistStatePatch({ reducedMotion: v });
  },
  setUiDensity: (d) => {
    applyDomTheme(get().theme, get().reducedMotion, d);
    set({ uiDensity: d });
    persistStatePatch({ uiDensity: d });
  },
  setNavExpanded: (v) => {
    set({ navExpanded: v });
    persistStatePatch({ navExpanded: v });
  },
  setShowNavRail: (v) => {
    set({ showNavRail: v });
    persistStatePatch({ showNavRail: v });
  },
  setInspectorOpen: (v) => set({ inspectorOpen: v }),
  setInspectorWidth: (w) => {
    const clamped = Math.max(260, Math.min(460, Math.round(w)));
    set({ inspectorWidth: clamped });
    persistStatePatch({ inspectorWidth: clamped });
  },
  setLayoutMode: (m) => {
    set({ layoutMode: m });
    persistStatePatch({ layoutMode: m });
  },
  setSplitRatio: (r) => {
    const clamped = Math.max(0.24, Math.min(0.75, r));
    set({ splitRatio: clamped });
    persistStatePatch({ splitRatio: clamped });
  },
  setAutosaveEnabled: (v) => {
    set({ autosaveEnabled: v });
    persistStatePatch({ autosaveEnabled: v });
  },
  resetWorkspaceLayout: () => {
    set({
      navExpanded: true,
      inspectorOpen: true,
      inspectorWidth: 320,
      layoutMode: "split",
      splitRatio: 0.44,
    });
    persistStatePatch({
      navExpanded: true,
      inspectorWidth: 320,
      layoutMode: "split",
      splitRatio: 0.44,
    });
    get().pushNotification("info", "已恢复工作区默认分栏布局");
  },

  setSelectedIndices: (indices) => set({ selectedIndices: indices }),
  setActiveTool: (t) => set({ activeTool: t }),
  setActiveElementZ: (z) => set({ activeElementZ: z }),
  setActiveRing: (r) => set({ activeRing: r }),
  setActiveFragmentId: (id) => set({ activeFragmentId: id }),
  setReprMode: (m) => set({ reprMode: m }),
  setAtomScale: (v) => set({ atomScale: v }),
  setBondScale: (v) => set({ bondScale: v }),
  setShowHydrogens: (v) => set({ showHydrogens: v }),
  setShowCell: (v) => set({ showCell: v }),
  setShowAxes: (v) => set({ showAxes: v }),
  setShowAtomIds: (v) => set({ showAtomIds: v }),
  triggerFitCamera: () => set((s) => ({ fitNonce: s.fitNonce + 1 })),

  setCommandPaletteOpen: (v) => set({ commandPaletteOpen: v }),
  setPeriodicModalOpen: (v) => set({ periodicModalOpen: v }),
  setNotificationsOpen: (v) => set({ notificationsOpen: v }),
  setAiDrawerOpen: (v) => set({ aiDrawerOpen: v }),

  runTask: async (label, fn, switchToEditor = false) => {
    set({ busyLabel: label });
    try {
      const result = await fn();
      await get().refreshScene();
      if (switchToEditor) set({ activeRoute: "editor" });
      return result;
    } catch (err) {
      get().pushNotification("error", `${label} 失败`, err instanceof Error ? err.message : String(err));
      return undefined;
    } finally {
      set({ busyLabel: null });
    }
  },

  openStructureDialog: async () => {
    if (!window.molforgeDesktop) return;
    const picked = await window.molforgeDesktop.dialogs.openStructureFile();
    if (picked.cancelled || !picked.filePath) return;
    await get().openFilePath(picked.filePath);
  },

  openProjectDialog: async () => {
    if (!window.molforgeDesktop) return;
    const picked = await window.molforgeDesktop.dialogs.openProjectFile();
    if (picked.cancelled || !picked.filePath) return;
    await get().openFilePath(picked.filePath);
  },

  openFilePath: async (filePath: string) => {
    await get().runTask(
      `打开 ${filePath.split(/[\\/]/).pop()}`,
      async () => {
        const res = await molApi.openFile(filePath);
        const doc = res.document;
        const nextEntry: RecentProjectEntry = {
          name: doc.name,
          path: filePath,
          formula: doc.formula,
          numAtoms: doc.num_atoms,
          updatedAt: new Date().toISOString(),
        };
        const merged = [
          nextEntry,
          ...get().recentProjects.filter((p) => p.path !== filePath),
        ].slice(0, 12);
        set({
          projectPath: filePath.toLowerCase().endsWith(".mforge") ? filePath : null,
          lastSavedRev: doc.revision,
          isDirty: false,
          recentProjects: merged,
          fitNonce: get().fitNonce + 1,
        });
        persistStatePatch({ recentProjects: merged });
        get().pushNotification(
          "success",
          `已加载 ${doc.name}`,
          `${doc.num_atoms.toLocaleString()} atoms · 解析耗时 ${res.parse_ms} ms`
        );
      },
      true
    );
  },

  saveProject: async (saveAs = false) => {
    if (!window.molforgeDesktop) {
      const exp = await molApi.exportMforgeBytes(get().summary?.name);
      get().pushNotification("info", "Web 预览模式下已准备 .mforge 归档", `${exp.document.name}`);
      return;
    }
    let targetPath = saveAs ? null : get().projectPath;
    if (!targetPath) {
      const safeName = (get().summary?.name || "molecule").replace(/[\\/:*?"<>|]/g, "_");
      const dlg = await window.molforgeDesktop.dialogs.saveFile(`${safeName}.mforge`, [
        { name: "MolForge 工程 (*.mforge)", extensions: ["mforge"] },
      ]);
      if (dlg.cancelled || !dlg.filePath) return;
      targetPath = dlg.filePath;
    }
    set({ busyLabel: "正在原子保存 .mforge 工程..." });
    try {
      const exp = await molApi.exportMforgeBytes(get().summary?.name);
      await window.molforgeDesktop.files.writeBase64Atomic(targetPath, exp.base64);
      const entry: RecentProjectEntry = {
        name: exp.document.name,
        path: targetPath,
        formula: exp.document.formula,
        numAtoms: exp.document.num_atoms,
        updatedAt: new Date().toISOString(),
      };
      const merged = [
        entry,
        ...get().recentProjects.filter((p) => p.path !== targetPath),
      ].slice(0, 12);
      set({
        projectPath: targetPath,
        lastSavedRev: exp.document.revision,
        isDirty: false,
        recentProjects: merged,
      });
      persistStatePatch({ recentProjects: merged });
      await window.molforgeDesktop.workspace.clearAutosave();
      get().pushNotification("success", "工程已安全保存 (.mforge v1.1)", targetPath);
    } catch (err) {
      get().pushNotification("error", "工程保存失败", err instanceof Error ? err.message : String(err));
    } finally {
      set({ busyLabel: null });
    }
  },

  restoreAutosave: async () => {
    const rec = get().recoveryPrompt;
    if (!rec?.base64Data) return;
    await get().runTask("恢复上次自动备份会话...", async () => {
      await molApi.importMforgeBytes(rec.base64Data!);
      set({ recoveryPrompt: null });
      await window.molforgeDesktop?.workspace.clearAutosave();
      get().pushNotification("success", "已从本地自动备份恢复分子工程");
    }, true);
  },

  dismissAutosave: async () => {
    set({ recoveryPrompt: null });
    await window.molforgeDesktop?.workspace.clearAutosave();
  },

  runAutosaveSnapshot: async () => {
    if (!window.molforgeDesktop || !get().autosaveEnabled || !get().isDirty) return;
    try {
      const exp = await molApi.exportMforgeBytes(get().summary?.name);
      await window.molforgeDesktop.workspace.saveAutosaveBase64(exp.base64, {
        name: exp.document.name,
        formula: exp.document.formula,
        numAtoms: exp.document.num_atoms,
      });
    } catch {
      // silent background autosave
    }
  },

  addCustomLibraryItems: (items) => {
    const merged = [...items, ...get().customLibraryItems].slice(0, 200);
    set({ customLibraryItems: merged });
    persistStatePatch({ libraryCustomMolecules: merged });
  },

  runAndRecordAnalysis: async (analysisId) => {
    set({ busyLabel: `执行分析 ${analysisId}...` });
    try {
      const res = await molApi.runAnalysis(analysisId);
      const record: RecentAnalysisRecord = {
        analysisId,
        title: res.result.title,
        moleculeName: get().summary?.name || "当前分子",
        status: res.result.status,
        timestamp: nowTimeStr(),
      };
      const merged = [record, ...get().recentAnalyses].slice(0, 25);
      set({ lastAnalysisResult: res.result, recentAnalyses: merged });
      persistStatePatch({ recentAnalyses: merged });
      return res.result;
    } catch (err) {
      get().pushNotification("error", `分析 ${analysisId} 执行失败`, String(err));
      return undefined;
    } finally {
      set({ busyLabel: null });
    }
  },

  runTightBinding: async () => {
    set({ busyLabel: "正在执行 Tight-Binding 前线轨道计算..." });
    try {
      const res = await molApi.computeTB();
      set({ tbResult: res });
      return res;
    } catch (err) {
      get().pushNotification("error", "紧束缚求解失败", String(err));
      return undefined;
    } finally {
      set({ busyLabel: null });
    }
  },

  submitBackgroundJob: async (kind, label, params) => {
    try {
      const res = await molApi.submitJob(kind, label, params);
      set((s) => ({ jobs: [res.job, ...s.jobs] }));
      get().pushNotification("info", `已提交后台任务：${label}`);
    } catch (err) {
      get().pushNotification("error", "提交后台任务失败", String(err));
    }
  },

  cancelBackgroundJob: async (jobId) => {
    try {
      await molApi.cancelJob(jobId);
      await get().refreshJobs();
    } catch (err) {
      get().pushNotification("error", "取消任务失败", String(err));
    }
  },

  sendAiPrompt: async (prompt) => {
    const clean = prompt.trim();
    if (!clean || get().aiLoading) return;
    const userMsg: ChatMessage = { id: `u_${Date.now()}`, role: "user", content: clean };
    set((s) => ({ messages: [...s.messages, userMsg], aiLoading: true }));
    try {
      const res = await molApi.aiChat(clean);
      const assistantMsg: ChatMessage = {
        id: `a_${Date.now()}`,
        role: "assistant",
        content: res.reply,
        a2uiBlocks: res.a2ui_blocks,
      };
      set((s) => ({ messages: [...s.messages, assistantMsg] }));
      await get().refreshScene();
    } catch (err) {
      const errMsg: ChatMessage = {
        id: `e_${Date.now()}`,
        role: "assistant",
        content: `请求失败：${err instanceof Error ? err.message : String(err)}`,
      };
      set((s) => ({ messages: [...s.messages, errMsg] }));
    } finally {
      set({ aiLoading: false });
    }
  },
}));
