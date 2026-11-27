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

export type RepresentationMode = "ball_stick" | "cpk" | "stick" | "wireframe";

export type ViewLayoutMode = "split" | "3d" | "2d";

export type EditTool = "select" | "atom" | "bond" | "ring" | "erase";

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
  name: string;
  formula: string;
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
