export type StudioTheme = "obsidian" | "arctic";
export type NavRoute =
  | "overview"
  | "library"
  | "editor"
  | "analysis"
  | "hub"
  | "jobs"
  | "reports"
  | "settings";

export type RepresentationMode = "ball_stick" | "cpk" | "stick" | "wireframe";
export type ViewLayoutMode = "split" | "3d" | "2d";
export type EditTool = "select" | "atom" | "bond" | "ring" | "erase" | "fragment";

export interface ElementInfo {
  atomic_number: number;
  symbol: string;
  name: string;
  name_cn: string;
  atomic_weight: number;
  electronegativity: number | null;
  vdw_radius: number;
  covalent_radius: number;
  electron_config: string;
  group: number;
  period: number;
  block: string;
  category: string;
  hex_color: string;
  text_color: string;
}

export interface FragmentInfo {
  id: string;
  name_cn: string;
  name_en: string;
  formula: string;
  category: string;
  smiles: string;
  attachment_bond_order: number;
  num_atoms: number;
  description: string;
}

export interface RingTemplateSpec {
  id: string;
  label: string;
  size: number;
  aromatic: boolean;
  hetero?: Record<number, number>;
}

export interface PresetItem {
  id: string;
  name: string;
  label: string;
  category: string;
  smiles: string;
}

export interface Preview2DStructure {
  atoms: Array<{
    index: number;
    symbol: string;
    atomic_num: number;
    x2: number;
    y2: number;
    color: [number, number, number];
  }>;
  bonds: Array<{
    i: number;
    j: number;
    order: number;
    aromatic: boolean;
  }>;
}

export interface LibraryMoleculeEntry {
  id: string;
  name: string;
  label: string;
  category: string;
  smiles: string;
  formula: string;
  molecular_weight: number;
  num_atoms: number;
  num_bonds: number;
  multiplicity: number;
  preview_2d: Preview2DStructure;
  error?: string;
}

export interface UnitCellSummary {
  a: number;
  b: number;
  c: number;
  alpha: number;
  beta: number;
  gamma: number;
  space_group?: string;
}

export interface DocumentSummary {
  document_id?: string;
  name: string;
  formula: string;
  molecular_weight?: number | null;
  num_atoms: number;
  num_bonds: number;
  charge: number;
  multiplicity: number;
  spin_label: string;
  geometry_label: string;
  point_group: string;
  revision: number;
  can_undo: boolean;
  can_redo: boolean;
  has_2d: boolean;
  has_3d: boolean;
  source_path?: string | null;
  cell?: UnitCellSummary | null;
  box_origin?: [number, number, number] | null;
  presets: PresetItem[];
}

export interface BinaryMoleculeData {
  numAtoms: number;
  numBonds: number;
  revision: number;
  coords: Float32Array;
  atomicNumbers: Uint8Array;
  vdwRadii: Float32Array;
  atomRgba: Uint8Array;
  bondPairs: Uint32Array;
  bondOrders: Uint8Array;
  hasCell: boolean;
  boxOrigin?: Float32Array;
  cellMatrix?: Float32Array;
  center: [number, number, number];
  boundingRadius: number;
}

export interface Atom2DItem {
  index: number;
  atom_id: number;
  display_id: number;
  symbol: string;
  atomic_num: number;
  x2: number;
  y2: number;
  x: number;
  y: number;
  z: number;
  formal_charge: number;
  color: [number, number, number];
}

export interface Bond2DItem {
  bond_id: number;
  i: number;
  j: number;
  order: number;
  aromatic: boolean;
}

export interface Atoms2DPayload {
  truncated: boolean;
  num_atoms: number;
  atoms: Atom2DItem[];
  bonds: Bond2DItem[];
}

export interface TightBindingResult {
  molecule_name?: string;
  formula?: string;
  method?: string;
  homo_ev?: number;
  lumo_ev?: number;
  gap_ev?: number;
  mo_energies_ev?: number[];
  homo_index?: number;
  transitions?: Array<{
    wavelength_nm: number;
    oscillator_f: number;
    energy_ev?: number;
  }>;
  references?: Array<{
    name: string;
    homo_ev: number;
    lumo_ev: number;
    color: string;
  }>;
  skipped?: boolean;
  reason?: string;
  error?: string;
}

export interface QcParsedOrbitalResult {
  ok: boolean;
  source: string;
  kind: "fchk" | "log";
  method: string;
  alpha_electrons?: number;
  homo_index?: number;
  homo_ev: number;
  lumo_ev: number;
  gap_ev: number;
  mo_energies_ev: number[];
  window_start_index?: number;
}

export interface AnalysisCatalogItem {
  id: string;
  category: string;
  title: string;
  engine: string;
  state: string;
  note: string;
}

export interface AnalysisRunResult {
  analysis_id: string;
  title: string;
  status: string;
  summary: string;
  metrics: Record<string, unknown>;
  plot_x: number[];
  plot_y: number[];
  x_label: string;
  y_label: string;
}

export type JobStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

export interface StudioJob {
  job_id: string;
  kind: string;
  name: string;
  document_name: string;
  input_revision: number;
  params: Record<string, unknown>;
  status: JobStatus;
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
  logs: string[];
  result: unknown;
  error: string;
}

export interface LlmPreferences {
  base_url: string;
  model: string;
  temperature: number;
  max_tokens: number;
  reasoning_effort: string;
  has_api_key: boolean;
  masked_api_key: string;
}

export interface ExternalEngineStatus {
  id: string;
  name: string;
  available: boolean;
  executable_path: string | null;
  version_hint: string;
  sha256: string | null;
  diagnostic: string;
}

export interface CalChemRunResult {
  ok: boolean;
  mode: "sp" | "opt";
  method?: string;
  basis?: string;
  converged: boolean;
  total_energy_hartree?: number;
  energy_hartree?: number;
  electronic_energy_hartree?: number;
  nuclear_repulsion_hartree?: number;
  homo_ev?: number | null;
  lumo_ev?: number | null;
  gap_ev?: number | null;
  dipole_magnitude_debye?: number;
  n_ao?: number;
  steps?: number;
  error?: string;
}

export interface MultiwfnRunResult {
  ok: boolean;
  analysis_id: string;
  input_file: string;
  metrics: Record<string, unknown>;
  plot_x: number[];
  plot_y: number[];
  x_label: string;
  y_label: string;
  message: string;
  stdout_tail: string;
  error?: string;
}

export interface GromacsPipelineResult {
  ok: boolean;
  gmx_available: boolean;
  gmx_path: string | null;
  files: Record<string, string>;
}

export type A2UIBlock =
  | {
      type: "metrics_card";
      title: string;
      items: Array<{ label: string; value: string }>;
    }
  | {
      type: "orbital_card";
      title: string;
      homo_ev: number;
      lumo_ev: number;
      gap_ev: number;
      s1_text: string;
      pm6_match?: boolean;
    }
  | {
      type: "action_row";
      title: string;
      actions: Array<{ label: string; action: string }>;
    };

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  a2uiBlocks?: A2UIBlock[];
}

export interface RecentProjectEntry {
  name: string;
  path: string;
  formula?: string;
  numAtoms?: number;
  updatedAt: string;
}

export interface RecentAnalysisRecord {
  analysisId: string;
  title: string;
  moleculeName: string;
  status: string;
  timestamp: string;
}

export interface StudioNotification {
  id: string;
  level: "info" | "success" | "warning" | "error";
  title: string;
  detail?: string;
  timestamp: string;
}

export interface SystemTelemetry {
  appVersion: string;
  electronVersion: string;
  platform: string;
  arch: string;
  rssMb: number;
  sysFreeGb: number;
  sysTotalGb: number;
}

export interface PersistedStudioState {
  schemaVersion: number;
  theme: StudioTheme;
  reducedMotion: boolean;
  uiDensity: "compact" | "comfortable";
  navExpanded: boolean;
  layoutMode: ViewLayoutMode;
  inspectorWidth: number;
  splitRatio: number;
  autosaveEnabled: boolean;
  recentProjects: RecentProjectEntry[];
  recentAnalyses: RecentAnalysisRecord[];
  libraryCustomMolecules: LibraryMoleculeEntry[];
}

export interface MolForgeDesktopBridge {
  isElectron: boolean;
  windowControls: {
    minimize: () => Promise<void>;
    toggleMaximize: () => Promise<boolean>;
    close: () => Promise<void>;
    isMaximized: () => Promise<boolean>;
  };
  dialogs: {
    openStructureFile: () => Promise<{ cancelled: boolean; filePath?: string }>;
    openProjectFile: () => Promise<{ cancelled: boolean; filePath?: string }>;
    openQcLogFile: () => Promise<{ cancelled: boolean; filePath?: string }>;
    openExecutableFile: () => Promise<{ cancelled: boolean; filePath?: string }>;
    saveFile: (
      defaultName?: string,
      filters?: Array<{ name: string; extensions: string[] }>
    ) => Promise<{ cancelled: boolean; filePath?: string }>;
  };
  files: {
    writeTextAtomic: (targetPath: string, content: string) => Promise<{ ok: boolean; path: string }>;
    writeBase64Atomic: (targetPath: string, base64Data: string) => Promise<{ ok: boolean; path: string }>;
    readBase64: (targetPath: string) => Promise<{ ok: boolean; path: string; base64Data: string }>;
    readText: (targetPath: string) => Promise<{ ok: boolean; path: string; content: string }>;
  };
  workspace: {
    loadStudioState: () => Promise<PersistedStudioState>;
    saveStudioState: (patch: Partial<PersistedStudioState>) => Promise<PersistedStudioState>;
    saveAutosaveBase64: (base64Data: string, meta: Record<string, unknown>) => Promise<{ ok: boolean }>;
    loadAutosave: () => Promise<{
      available: boolean;
      meta?: { name?: string; formula?: string; savedAt?: string };
      base64Data?: string;
    }>;
    clearAutosave: () => Promise<{ ok: boolean }>;
  };
  system: {
    getTelemetry: () => Promise<SystemTelemetry>;
    openExternalHttps: (url: string) => Promise<{ ok: boolean }>;
    restartBridge: () => Promise<{ ok: boolean; detail: string }>;
  };
  onEvent: (channel: string, handler: (payload: unknown) => void) => () => void;
}

declare global {
  interface Window {
    molforgeDesktop?: MolForgeDesktopBridge;
  }
}

export type HubResourceKind = "plugin" | "skill" | "workflow" | "model";

export interface HubResource {
  id: string;
  kind: HubResourceKind;
  name: string;
  title: string;
  version: string;
  author: string;
  license: string;
  source: string;
  category: string;
  description: string;
  tags: string[];
  provides_capabilities: string[];
  requires_capabilities: string[];
  permissions: string[];
  sha256: string | null;
  installed: boolean;
  trusted: boolean;
  favorite: boolean;
  pinned: boolean;
  runnable: boolean;
  missing_dependencies: string[];
  status_reason: string;
  security_warnings: string[];
}

export interface CapabilitySpec {
  id: string;
  title: string;
  category: string;
  provider_plugin_id: string;
  adapter: string;
  permission: string;
  available: boolean;
  diagnostic: string;
}

export interface WorkflowNodeSpec {
  id: string;
  title: string;
  kind: string;
  capability: string | null;
  depends_on: string[];
  params: Record<string, unknown>;
}

export interface WorkflowSpec {
  schema_version: string;
  id: string;
  version: string;
  title: string;
  category: string;
  description: string;
  tags: string[];
  requires_capabilities: string[];
  permissions: string[];
  nodes: WorkflowNodeSpec[];
}

export interface WorkflowRun {
  run_id: string;
  workflow_id: string;
  title: string;
  status: "pending_approval" | "completed" | "failed" | "blocked";
  missing_dependencies: string[];
  requires_approval: boolean;
  node_records: Array<{
    node_id: string;
    title: string;
    capability: string | null;
    status: string;
    duration_ms: number;
    summary: string;
    output?: unknown;
  }>;
  outputs: Record<string, unknown>;
  provenance: {
    run_id: string;
    workflow_id: string;
    workflow_version: string;
    workflow_sha256: string;
    input_molecule_name: string;
    input_molecule_formula: string;
    input_molecule_sha256: string;
    matched_skill_ids: string[];
    capabilities_used: string[];
    approved_by_user: boolean;
    timestamp_unix: number;
  };
  error: string | null;
}

export interface WorkflowProposal {
  query: string;
  intent_capabilities: string[];
  matched_skills: Array<{
    id: string;
    name: string;
    description: string;
    sha256: string;
  }>;
  selected_workflow: WorkflowSpec;
  runnable: boolean;
  missing_dependencies: string[];
  status_reason: string;
  explanation: string;
}
