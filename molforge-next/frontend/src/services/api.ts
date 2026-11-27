import type {
  A2UIBlock,
  AnalysisCatalogItem,
  AnalysisRunResult,
  Atoms2DPayload,
  BinaryMoleculeData,
  DocumentSummary,
  ElementInfo,
  TightBindingResult,
} from "../types/molforge";

const API_BASE =
  typeof window !== "undefined" &&
  (window.location.protocol === "tauri:" ||
    window.location.hostname === "tauri.localhost" ||
    window.location.port === "1420")
    ? "http://127.0.0.1:18765"
    : "";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let lastErr: unknown;
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const res = await fetch(`${API_BASE}${path}`, {
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
        await new Promise((r) => setTimeout(r, 150));
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

  let minX = Infinity,
    minY = Infinity,
    minZ = Infinity;
  let maxX = -Infinity,
    maxY = -Infinity,
    maxZ = -Infinity;
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
    const ox = boxOrigin[0],
      oy = boxOrigin[1],
      oz = boxOrigin[2];
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
  health: () => requestJson<{ ok: boolean; version: string; document: DocumentSummary }>("/api/health"),
  getDocument: () => requestJson<DocumentSummary>("/api/document"),
  async getBinaryMolecule(): Promise<BinaryMoleculeData> {
    const res = await fetch(`${API_BASE}/api/document/binary`);
    if (!res.ok) throw new Error(`Binary fetch failed: HTTP ${res.status}`);
    const buf = await res.arrayBuffer();
    return decodeBinaryMolecule(buf);
  },
  getAtoms2D: () => requestJson<Atoms2DPayload>("/api/atoms"),
  getElements: () => requestJson<{ elements: ElementInfo[] }>("/api/elements"),
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
  openFileDialog: () =>
    requestJson<{ ok: boolean; cancelled?: boolean; path?: string; parse_ms?: number; document?: DocumentSummary }>(
      "/api/dialog/open_file",
      { method: "POST", body: "{}" }
    ),
  exportFile: (format: "pdb" | "xyz" | "mol" | "gjf" | "rest") =>
    requestJson<{ ok: boolean; filename: string; content: string }>("/api/export", {
      method: "POST",
      body: JSON.stringify({ format }),
    }),
  undo: () => requestJson<{ ok: boolean; document: DocumentSummary }>("/api/edit/undo", { method: "POST", body: "{}" }),
  redo: () => requestJson<{ ok: boolean; document: DocumentSummary }>("/api/edit/redo", { method: "POST", body: "{}" }),
  clean3D: () => requestJson<{ ok: boolean; message: string; document: DocumentSummary }>("/api/edit/clean_3d", { method: "POST", body: "{}" }),
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
  changeElement: (atom_id: number, atomic_num: number) =>
    requestJson<{ ok: boolean; document: DocumentSummary }>("/api/edit/change_element", {
      method: "POST",
      body: JSON.stringify({ atom_id, atomic_num }),
    }),
  addRing: (params: { size: number; aromatic: boolean; hetero?: Record<number, number>; attach_to?: number; center_2d?: [number, number] }) =>
    requestJson<{ ok: boolean; document: DocumentSummary }>("/api/edit/add_ring", {
      method: "POST",
      body: JSON.stringify(params),
    }),
  moveAtom: (atom_id: number, pos_2d: [number, number]) =>
    requestJson<{ ok: boolean; document: DocumentSummary }>("/api/edit/move_atom", {
      method: "POST",
      body: JSON.stringify({ atom_id, pos_2d }),
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
  computeTB: () => requestJson<TightBindingResult>("/api/qc/tight_binding", { method: "POST", body: "{}" }),
  exportQcInput: (kind: "gaussian" | "rest", route?: string) =>
    requestJson<{ ok: boolean; kind: string; content: string }>("/api/qc/export_input", {
      method: "POST",
      body: JSON.stringify({ kind, route }),
    }),
  getAnalysisCatalog: () => requestJson<{ items: AnalysisCatalogItem[] }>("/api/analysis/catalog"),
  runAnalysis: (analysis_id: string) =>
    requestJson<{ ok: boolean; result: AnalysisRunResult }>("/api/analysis/run", {
      method: "POST",
      body: JSON.stringify({ analysis_id }),
    }),
  aiChat: (prompt: string) =>
    requestJson<{ reply: string; a2ui_blocks: A2UIBlock[]; document: DocumentSummary }>("/api/ai/chat", {
      method: "POST",
      body: JSON.stringify({ prompt }),
    }),
};
