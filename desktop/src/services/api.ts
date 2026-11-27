import type {
  A2UIBlock,
  AnalysisCatalogItem,
  AnalysisRunResult,
  Atoms2DPayload,
  BinaryMoleculeData,
  CalChemRunResult,
  DocumentSummary,
  ElementInfo,
  ExternalEngineStatus,
  FragmentInfo,
  GromacsPipelineResult,
  LibraryMoleculeEntry,
  LlmPreferences,
  MultiwfnRunResult,
  QcParsedOrbitalResult,
  StudioJob,
  TightBindingResult,
} from "../types/studio";

export function resolveApiBase(): string {
  if (typeof window === "undefined") return "http://127.0.0.1:18765";
  if (window.location.protocol === "file:" || window.molforgeDesktop?.isElectron) {
    return "http://127.0.0.1:18765";
  }
  return "";
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const base = resolveApiBase();
  let lastErr: unknown;
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const res = await fetch(`${base}${path}`, {
        headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
        ...init,
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.error || `HTTP ${res.status}`);
      }
      return data as T;
    } catch (err) {
      lastErr = err;
      if (attempt === 0) {
        await new Promise((r) => setTimeout(r, 140));
      }
    }
  }
  throw lastErr instanceof Error ? lastErr : new Error(String(lastErr));
}

export function decodeBinaryMolecule(buffer: ArrayBuffer): BinaryMoleculeData {
  const view = new DataView(buffer);
  const magic = view.getUint32(0, true);
  if (magic !== 0x4d4f4c46) {
    throw new Error("Invalid MolForge binary stream magic");
  }
  const numAtoms = view.getUint32(8, true);
  const numBonds = view.getUint32(12, true);
  const revision = view.getUint32(16, true);
  const hasCell = view.getUint32(20, true) === 1;

  let offset = 32;
  const coords = new Float32Array(buffer, offset, numAtoms * 3);
  offset += numAtoms * 3 * 4;

  const atomicNumbers = new Uint8Array(buffer, offset, numAtoms);
  const zPad = (4 - (numAtoms % 4)) % 4;
  offset += numAtoms + zPad;

  const vdwRadii = new Float32Array(buffer, offset, numAtoms);
  offset += numAtoms * 4;

  const atomRgba = new Uint8Array(buffer, offset, numAtoms * 4);
  offset += numAtoms * 4;

  const bondPairs = new Uint32Array(buffer, offset, numBonds * 2);
  offset += numBonds * 2 * 4;

  const bondOrders = new Uint8Array(buffer, offset, numBonds);
  const boPad = (4 - (numBonds % 4)) % 4;
  offset += numBonds + boPad;

  let boxOrigin: Float32Array | undefined;
  let cellMatrix: Float32Array | undefined;
  if (hasCell && offset + 48 <= buffer.byteLength) {
    boxOrigin = new Float32Array(buffer, offset, 3);
    offset += 12;
    cellMatrix = new Float32Array(buffer, offset, 9);
  }

  let minX = Infinity;
  let minY = Infinity;
  let minZ = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  let maxZ = -Infinity;

  for (let i = 0; i < numAtoms; i++) {
    const x = coords[i * 3];
    const y = coords[i * 3 + 1];
    const z = coords[i * 3 + 2];
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (z < minZ) minZ = z;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
    if (z > maxZ) maxZ = z;
  }

  if (hasCell && boxOrigin && cellMatrix) {
    const ox = boxOrigin[0];
    const oy = boxOrigin[1];
    const oz = boxOrigin[2];
    for (let mask = 0; mask < 8; mask++) {
      const a = mask & 1 ? 1 : 0;
      const b = mask & 2 ? 1 : 0;
      const c = mask & 4 ? 1 : 0;
      const cx = ox + a * cellMatrix[0] + b * cellMatrix[3] + c * cellMatrix[6];
      const cy = oy + a * cellMatrix[1] + b * cellMatrix[4] + c * cellMatrix[7];
      const cz = oz + a * cellMatrix[2] + b * cellMatrix[5] + c * cellMatrix[8];
      if (cx < minX) minX = cx;
      if (cy < minY) minY = cy;
      if (cz < minZ) minZ = cz;
      if (cx > maxX) maxX = cx;
      if (cy > maxY) maxY = cy;
      if (cz > maxZ) maxZ = cz;
    }
  }

  const cx = numAtoms > 0 ? 0.5 * (minX + maxX) : 0;
  const cy = numAtoms > 0 ? 0.5 * (minY + maxY) : 0;
  const cz = numAtoms > 0 ? 0.5 * (minZ + maxZ) : 0;
  const dx = maxX - minX;
  const dy = maxY - minY;
  const dz = maxZ - minZ;
  const boundingRadius = numAtoms > 0 ? Math.max(2.2, 0.5 * Math.hypot(dx, dy, dz)) : 4.0;

  return {
    numAtoms,
    numBonds,
    revision,
    coords,
    atomicNumbers,
    vdwRadii,
    atomRgba,
    bondPairs,
    bondOrders,
    hasCell,
    boxOrigin,
    cellMatrix,
    center: [cx, cy, cz],
    boundingRadius,
  };
}

export const molApi = {
  health: () =>
    requestJson<{ ok: boolean; version: string; document: DocumentSummary }>("/api/health"),
  getDocument: () => requestJson<DocumentSummary>("/api/document"),
  async getBinaryMolecule(): Promise<BinaryMoleculeData> {
    const res = await fetch(`${resolveApiBase()}/api/document/binary`);
    if (!res.ok) throw new Error(`Binary fetch failed: HTTP ${res.status}`);
    return decodeBinaryMolecule(await res.arrayBuffer());
  },
  getAtoms2D: () => requestJson<Atoms2DPayload>("/api/atoms"),
  getElements: () => requestJson<{ elements: ElementInfo[] }>("/api/elements"),
  getFragments: () => requestJson<{ fragments: FragmentInfo[] }>("/api/fragments"),
  getLibraryPresets: () => requestJson<{ items: LibraryMoleculeEntry[] }>("/api/library/presets"),
  inspectSmilesBatch: (items: Array<{ name: string; smiles: string; category?: string }>) =>
    requestJson<{ ok: boolean; items: Array<LibraryMoleculeEntry & { ok: boolean }> }>(
      "/api/library/inspect_smiles",
      { method: "POST", body: JSON.stringify({ items }) }
    ),
  buildSmiles: (smiles: string, name?: string) =>
    requestJson<{ ok: boolean; document: DocumentSummary }>("/api/build/smiles", {
      method: "POST",
      body: JSON.stringify({ smiles, name }),
    }),
  loadPreset: (id: string) =>
    requestJson<{ ok: boolean; document: DocumentSummary }>("/api/build/preset", {
      method: "POST",
      body: JSON.stringify({ id }),
    }),
  openFile: (path: string) =>
    requestJson<{ ok: boolean; parse_ms: number; document: DocumentSummary }>("/api/open", {
      method: "POST",
      body: JSON.stringify({ path }),
    }),
  exportMforgeBytes: (name?: string) =>
    requestJson<{ ok: boolean; base64: string; document: DocumentSummary }>(
      "/api/project/export_mforge_bytes",
      { method: "POST", body: JSON.stringify({ name }) }
    ),
  importMforgeBytes: (base64: string, source_path?: string) =>
    requestJson<{ ok: boolean; document: DocumentSummary }>(
      "/api/project/import_mforge_bytes",
      { method: "POST", body: JSON.stringify({ base64, source_path }) }
    ),
  exportFile: (format: "pdb" | "xyz" | "mol" | "gjf" | "rest") =>
    requestJson<{ ok: boolean; filename: string; content: string }>("/api/export", {
      method: "POST",
      body: JSON.stringify({ format }),
    }),
  undo: () =>
    requestJson<{ ok: boolean; document: DocumentSummary }>("/api/edit/undo", {
      method: "POST",
      body: "{}",
    }),
  redo: () =>
    requestJson<{ ok: boolean; document: DocumentSummary }>("/api/edit/redo", {
      method: "POST",
      body: "{}",
    }),
  clean3D: () =>
    requestJson<{ ok: boolean; message: string; document: DocumentSummary }>(
      "/api/edit/clean_3d",
      { method: "POST", body: "{}" }
    ),
  addAtom: (params: { atomic_num: number; bond_to?: number; pos_2d?: [number, number] }) =>
    requestJson<{ ok: boolean; document: DocumentSummary }>("/api/edit/add_atom", {
      method: "POST",
      body: JSON.stringify(params),
    }),
  addBond: (atom_a: number, atom_b: number, order = 1) =>
    requestJson<{ ok: boolean; document: DocumentSummary }>("/api/edit/add_bond", {
      method: "POST",
      body: JSON.stringify({ atom_a, atom_b, order }),
    }),
  deleteBond: (bond_id: number) =>
    requestJson<{ ok: boolean; document: DocumentSummary }>("/api/edit/delete_bond", {
      method: "POST",
      body: JSON.stringify({ bond_id }),
    }),
  cycleBondOrder: (bond_id: number) =>
    requestJson<{ ok: boolean; document: DocumentSummary }>("/api/edit/cycle_bond_order", {
      method: "POST",
      body: JSON.stringify({ bond_id }),
    }),
  setBondOrder: (bond_id: number, order: number) =>
    requestJson<{ ok: boolean; document: DocumentSummary }>("/api/edit/set_bond_order", {
      method: "POST",
      body: JSON.stringify({ bond_id, order }),
    }),
  setAtomCharge: (atom_id: number, charge: number) =>
    requestJson<{ ok: boolean; document: DocumentSummary }>("/api/edit/set_atom_charge", {
      method: "POST",
      body: JSON.stringify({ atom_id, charge }),
    }),
  changeElement: (atom_id: number, atomic_num: number) =>
    requestJson<{ ok: boolean; document: DocumentSummary }>("/api/edit/change_element", {
      method: "POST",
      body: JSON.stringify({ atom_id, atomic_num }),
    }),
  addRing: (params: {
    size: number;
    aromatic: boolean;
    hetero?: Record<number, number>;
    attach_to?: number;
    center_2d?: [number, number];
  }) =>
    requestJson<{ ok: boolean; document: DocumentSummary }>("/api/edit/add_ring", {
      method: "POST",
      body: JSON.stringify(params),
    }),
  insertFragment: (params: {
    fragment_id: string;
    anchor_atom_id?: number;
    attach_to_existing?: boolean;
  }) =>
    requestJson<{ ok: boolean; message: string; document: DocumentSummary }>(
      "/api/edit/insert_fragment",
      { method: "POST", body: JSON.stringify(params) }
    ),
  moveAtom: (atom_id: number, pos_2d: [number, number]) =>
    requestJson<{ ok: boolean; document: DocumentSummary }>("/api/edit/move_atom", {
      method: "POST",
      body: JSON.stringify({ atom_id, pos_2d: { x: pos_2d[0], y: pos_2d[1] } }),
    }),
  deleteAtoms: (atomIds: number[]) =>
    requestJson<{ ok: boolean; document: DocumentSummary }>("/api/edit/delete_atoms", {
      method: "POST",
      body: JSON.stringify({ atom_ids: atomIds }),
    }),
  deleteIndices: (indices: number[]) =>
    requestJson<{ ok: boolean; document: DocumentSummary }>("/api/edit/delete_indices", {
      method: "POST",
      body: JSON.stringify({ indices }),
    }),
  setChargeSpin: (charge: number, multiplicity: number) =>
    requestJson<{ ok: boolean; document: DocumentSummary }>("/api/edit/set_charge_spin", {
      method: "POST",
      body: JSON.stringify({ charge, multiplicity }),
    }),
  computeTB: () =>
    requestJson<TightBindingResult>("/api/qc/tight_binding", { method: "POST", body: "{}" }),
  parseQcLog: (path: string) =>
    requestJson<QcParsedOrbitalResult>("/api/qc/parse_log", {
      method: "POST",
      body: JSON.stringify({ path }),
    }),
  exportQcInput: (kind: "gaussian" | "rest" | "orca" | "xtb", route?: string) =>
    requestJson<{ ok: boolean; engine: string; content: string }>("/api/qc/export_input", {
      method: "POST",
      body: JSON.stringify({ kind, engine: kind, route }),
    }),
  getAnalysisCatalog: () =>
    requestJson<{ items: AnalysisCatalogItem[] }>("/api/analysis/catalog"),
  runAnalysis: (analysis_id: string) =>
    requestJson<{ ok: boolean; result: AnalysisRunResult }>("/api/analysis/run", {
      method: "POST",
      body: JSON.stringify({ analysis_id }),
    }),
  listJobs: () => requestJson<{ jobs: StudioJob[] }>("/api/jobs"),
  submitJob: (kind: string, label: string, params?: Record<string, unknown>) =>
    requestJson<{ ok: boolean; job: StudioJob }>("/api/jobs/submit", {
      method: "POST",
      body: JSON.stringify({ kind, label, params }),
    }),
  cancelJob: (job_id: string) =>
    requestJson<{ ok: boolean; job: StudioJob }>("/api/jobs/cancel", {
      method: "POST",
      body: JSON.stringify({ job_id }),
    }),
  getPreferences: () => requestJson<LlmPreferences>("/api/preferences"),
  savePreferences: (prefs: {
    base_url?: string;
    model?: string;
    api_key?: string;
    temperature?: number;
    max_tokens?: number;
    reasoning_effort?: string;
  }) =>
    requestJson<{ ok: boolean }>("/api/preferences", {
      method: "POST",
      body: JSON.stringify(prefs),
    }),
  getEnginesStatus: () =>
    requestJson<{ engines: ExternalEngineStatus[]; calchem_basis_sets: string[] }>(
      "/api/engines/status"
    ),
  configureEngine: (tool_id: string, executable_path: string) =>
    requestJson<{ engines: ExternalEngineStatus[]; calchem_basis_sets: string[] }>(
      "/api/engines/configure",
      { method: "POST", body: JSON.stringify({ tool_id, executable_path }) }
    ),
  runCalchem: (params: {
    mode?: "sp" | "opt";
    method?: string;
    basis?: string;
    max_steps?: number;
  }) =>
    requestJson<CalChemRunResult>("/api/qc/run_calchem", {
      method: "POST",
      body: JSON.stringify(params),
    }),
  runXtb: (params: { gfn_level?: number; apply_geometry?: boolean; method?: string; optimize?: boolean }) =>
    requestJson<{
      ok: boolean;
      engine: string;
      energy_hartree: number | null;
      converged?: boolean | null;
      timed_out?: boolean;
      exit_code?: number;
      workdir?: string;
      message: string;
      error?: string | null;
      stdout_tail: string;
    }>("/api/qc/run_xtb", {
      method: "POST",
      body: JSON.stringify(params),
    }),
  runExternalQc: (params: { engine: "orca" | "gaussian"; keywords?: string; method?: string; basis?: string }) =>
    requestJson<{
      ok: boolean;
      status: string;
      engine: string;
      exit_code: number;
      energy_hartree: number | null;
      timed_out: boolean;
      workdir: string;
      stdout_tail: string;
    }>("/api/qc/run_external", {
      method: "POST",
      body: JSON.stringify(params),
    }),
  runMultiwfn: (params: { analysis_id: string; input_file?: string }) =>
    requestJson<MultiwfnRunResult>("/api/analysis/run_multiwfn", {
      method: "POST",
      body: JSON.stringify(params),
    }),
  generateGromacs: (params: {
    temp_k?: number;
    pressure_bar?: number;
    nsteps_md?: number;
    dt_ps?: number;
  }) =>
    requestJson<GromacsPipelineResult>("/api/md/generate_gromacs", {
      method: "POST",
      body: JSON.stringify(params),
    }),
  aiChat: (prompt: string) =>
    requestJson<{
      reply: string;
      a2ui_blocks: A2UIBlock[];
      document: DocumentSummary;
      offline?: boolean;
      offline_reason?: string;
      document_replaced?: boolean;
    }>("/api/ai/chat", {
      method: "POST",
      body: JSON.stringify({ prompt }),
    }),
  getHubResources: (query?: string, kind?: string) => {
    const qs = new URLSearchParams();
    if (query) qs.set("query", query);
    if (kind && kind !== "all") qs.set("kind", kind);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return requestJson<{ ok: boolean; items: import("../types/studio").HubResource[] }>(
      `/api/hub/resources${suffix}`
    );
  },
  getHubCapabilities: () =>
    requestJson<{ ok: boolean; capabilities: import("../types/studio").CapabilitySpec[] }>(
      "/api/hub/capabilities"
    ),
  toggleHubFavorite: (id: string) =>
    requestJson<{ ok: boolean; id: string; favorite: boolean }>("/api/hub/favorite", {
      method: "POST",
      body: JSON.stringify({ id }),
    }),
  toggleHubPin: (id: string) =>
    requestJson<{ ok: boolean; id: string; pinned: boolean }>("/api/hub/pin", {
      method: "POST",
      body: JSON.stringify({ id }),
    }),
  importSkillMd: (markdown: string, source = "local://import", capabilities: string[] = []) =>
    requestJson<{ ok: boolean; skill: Record<string, unknown> }>("/api/skills/import", {
      method: "POST",
      body: JSON.stringify({ markdown, source, capabilities }),
    }),
  getWorkflowsCatalog: () =>
    requestJson<{ ok: boolean; workflows: import("../types/studio").WorkflowSpec[] }>(
      "/api/workflows/catalog"
    ),
  getWorkflowRuns: () =>
    requestJson<{ ok: boolean; runs: import("../types/studio").WorkflowRun[] }>(
      "/api/workflows/runs"
    ),
  runWorkflow: (workflow_id: string, approved = false, params?: Record<string, unknown>) =>
    requestJson<{ ok: boolean; run: import("../types/studio").WorkflowRun }>(
      "/api/workflows/run",
      {
        method: "POST",
        body: JSON.stringify({ workflow_id, approved, params }),
      }
    ),
  planWorkflow: (query: string) =>
    requestJson<{ ok: boolean; proposal: import("../types/studio").WorkflowProposal }>(
      "/api/ai/plan_workflow",
      {
        method: "POST",
        body: JSON.stringify({ query }),
      }
    ),
  computeReorganizationEnergy: (params: {
    carrier?: "hole" | "electron";
    e_n_n?: number;
    e_n_i?: number;
    e_i_i?: number;
    e_i_n?: number;
    path_n_n?: string;
    path_n_i?: string;
    path_i_i?: string;
    path_i_n?: string;
  }) =>
    requestJson<{
      ok: boolean;
      carrier: string;
      e_n_n: number;
      e_n_i: number;
      e_i_i: number;
      e_i_n: number;
      lambda1_hartree: number;
      lambda2_hartree: number;
      lambda_total_hartree: number;
      lambda1_ev: number;
      lambda2_ev: number;
      lambda_total_ev: number;
      lambda_total_mev: number;
      lambda_total_kcal: number;
    }>("/api/qc/reorganization_energy", {
      method: "POST",
      body: JSON.stringify(params),
    }),
};
