# MolForge Next — DESIGN.md (Google Stitch + Material 3 Expressive + A2UI Spec)

## 1. Visual Philosophy & Material 3 Expressive Hierarchy
- **Aesthetic Direction**: *Bioluminescent Precision Scientific Observatory*. Dark obsidian viewport surfaces create high contrast for CPK atoms, covalent bonds, and frontier orbital energy diagrams, paired with a switchable Academic Paper Light theme for publication export workflows.
- **Tonal Surface Layering** (no harsh 2px borders; rely on 4–6% luminance steps + `1px` `outline-variant` hairlines + frosted `18px` backdrop blur on floating docks):
  - `md.sys.color.surface-container-lowest`: `#070B10` (3D WebGPU Stage Canvas)
  - `md.sys.color.surface`: `#0D141D` (Top Bar & Navigation Rail)
  - `md.sys.color.surface-container-low`: `#121C28` (Left Drawer & Inspector)
  - `md.sys.color.surface-container-high`: `rgba(21, 32, 46, 0.84)` (Floating Bottom Expressive Dock & HUD Pills)
  - `md.sys.color.primary`: `#5EEAD4` (Bioluminescent Teal · Active State / HOMO Highlight)
  - `md.sys.color.on-primary`: `#042F2E`
  - `md.sys.color.secondary`: `#60A5FA` (Crystal Cobalt · Donor Ref / Bonds)
  - `md.sys.color.tertiary`: `#FB923C` (Amber Photon · Acceptor Ref / LUMO)
  - `md.sys.color.outline-variant`: `rgba(148, 163, 184, 0.14)`

## 2. Typography & Motion
- **UI Font**: `"Inter"`, `"Microsoft YaHei UI"`, `"PingFang SC"`, system-ui, sans-serif
- **Numeric / Coordinate Font**: `"JetBrains Mono"`, `"Cascadia Code"`, monospace with `font-variant-numeric: tabular-nums`
- **Motion Curve**: Material 3 Expressive standard easing `cubic-bezier(0.2, 0.0, 0.0, 1.0)` at `180ms` for rail drawers and floating pill transitions.

## 3. A2UI (Agent-to-UI) Component Catalog
Instead of unstructured markdown walls, the MolForge AI Copilot emits typed declarative A2UI surfaces mapped to verified UI components:
- `metrics_card`: Tabular key-value molecular properties (Formula, Atom/Bond count, Spin state, SVD Geometry)
- `orbital_card`: Live Tight-Binding / DFT HOMO-LUMO gap visualizer with PM6/Y6 frontier matching bar
- `action_row`: Safe one-click action pills dispatching commands to MolForge (`run_tb`, `clean_3d`, `open_qc_gjf`)
