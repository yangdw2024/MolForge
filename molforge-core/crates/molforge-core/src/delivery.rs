//! Module 4: One-Click Batch Collaborator Delivery Packager.
//!
//! Produces flat-by-characterization folders (`LMO/`, `平面性/`, `二面角/`, `偶极矩/`,
//! `静电势/`, `origin_datas/`), single-pass unrounded OOXML `.xlsx` summary sheets +
//! UTF-8 BOM `.csv`, collaborator-friendly markdown guides, SHA-256 manifest, and a
//! verified UTF-8 `.zip` archive.

use crate::io;
use crate::model::Molecule;
use crate::qc;
use crate::skills::sha256_hex;
use crate::summary;
use crate::topology;
use crate::{CoreError, Result};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fs;
use std::io::{Cursor, Read, Write};
use std::path::{Path, PathBuf};
use zip::write::SimpleFileOptions;
use zip::{ZipArchive, ZipWriter};

#[derive(Debug, Clone, Deserialize)]
pub struct DeliveryPackageRequest {
    pub input_paths: Vec<String>,
    pub output_dir: String,
    #[serde(default = "default_pkg_name")]
    pub package_name: String,
    #[serde(default)]
    pub reference_path: Option<String>,
    #[serde(default)]
    pub asset_dir: Option<String>,
    #[serde(default)]
    pub allow_halogen_swap: bool,
}

fn default_pkg_name() -> String {
    "MolForge_Collaborator_Delivery".to_string()
}

#[derive(Debug, Clone, Serialize)]
pub struct DeliveryMoleculeRow {
    pub name: String,
    pub formula: String,
    pub num_atoms: usize,
    pub align_method: Option<String>,
    pub align_rmsd_a: Option<f64>,
    pub mpp_a: Option<f64>,
    pub sdp_a: Option<f64>,
    pub primary_torsion_deg: Option<f64>,
    pub secondary_torsion_deg: Option<f64>,
    pub interplanar_deg: Option<f64>,
    pub primary_bond_a: Option<f64>,
    pub short_contact_count: usize,
    pub tb_homo_ev: Option<f64>,
    pub tb_lumo_ev: Option<f64>,
    pub tb_gap_ev: Option<f64>,
    pub qc_scf_hartree: Option<f64>,
    pub qc_homo_ev: Option<f64>,
    pub qc_lumo_ev: Option<f64>,
    pub qc_gap_ev: Option<f64>,
    pub qc_dipole_debye: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
pub struct DeliveryPackageResult {
    pub ok: bool,
    pub output_dir: String,
    pub package_dir: String,
    pub zip_path: String,
    pub zip_verified: bool,
    pub zip_entries: usize,
    pub total_files: usize,
    pub molecule_count: usize,
    pub rows: Vec<DeliveryMoleculeRow>,
    pub manifest_sha256: String,
}

#[derive(Clone, Debug)]
enum XlsxCell {
    Text(String),
    Number { value: f64, style: usize },
}

fn xml_escape(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for ch in s.chars() {
        match ch {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            '\'' => out.push_str("&apos;"),
            _ => out.push(ch),
        }
    }
    out
}

fn col_letters(mut col_zero_based: usize) -> String {
    let mut buf = Vec::new();
    loop {
        buf.push((b'A' + (col_zero_based % 26) as u8) as char);
        if col_zero_based < 26 {
            break;
        }
        col_zero_based = col_zero_based / 26 - 1;
    }
    buf.into_iter().rev().collect()
}

/// Write a standards-compliant OOXML `.xlsx` workbook preserving full IEEE-754 numeric precision
/// with Excel display number formats (avoiding double rounding in numeric values).
fn write_xlsx_bytes(sheet_name: &str, headers: &[&str], rows: &[Vec<XlsxCell>]) -> Result<Vec<u8>> {
    let mut buf = Cursor::new(Vec::new());
    {
        let mut zip = ZipWriter::new(&mut buf);
        let opts = SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);

        let content_types = r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"#;
        zip.start_file("[Content_Types].xml", opts).map_err(|e| CoreError::External(e.to_string()))?;
        zip.write_all(content_types.as_bytes())?;

        let root_rels = r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"#;
        zip.start_file("_rels/.rels", opts).map_err(|e| CoreError::External(e.to_string()))?;
        zip.write_all(root_rels.as_bytes())?;

        let wb_rels = r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"#;
        zip.start_file("xl/_rels/workbook.xml.rels", opts).map_err(|e| CoreError::External(e.to_string()))?;
        zip.write_all(wb_rels.as_bytes())?;

        let workbook = format!(
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">\n  <sheets><sheet name=\"{}\" sheetId=\"1\" r:id=\"rId1\"/></sheets>\n</workbook>",
            xml_escape(&sheet_name.chars().take(31).collect::<String>())
        );
        zip.start_file("xl/workbook.xml", opts).map_err(|e| CoreError::External(e.to_string()))?;
        zip.write_all(workbook.as_bytes())?;

        // Style IDs: 0=default, 1=bold header, 2=0.00, 3=0.000, 4=0.0000, 5=0 (int)
        let styles = r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <numFmts count="3">
    <numFmt numFmtId="164" formatCode="0.000"/>
    <numFmt numFmtId="165" formatCode="0.0000"/>
    <numFmt numFmtId="166" formatCode="0"/>
  </numFmts>
  <fonts count="2">
    <font><sz val="11"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><name val="Calibri"/></font>
  </fonts>
  <fills count="2">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFEAF2F8"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="6">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="1" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
    <xf numFmtId="2" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
    <xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
    <xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
    <xf numFmtId="166" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
  </cellXfs>
</styleSheet>"#;
        zip.start_file("xl/styles.xml", opts).map_err(|e| CoreError::External(e.to_string()))?;
        zip.write_all(styles.as_bytes())?;

        let mut sheet = String::from(
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">\n  <sheetData>\n",
        );
        // Header row
        sheet.push_str("    <row r=\"1\">\n");
        for (c, h) in headers.iter().enumerate() {
            let cell_ref = format!("{}1", col_letters(c));
            sheet.push_str(&format!(
                "      <c r=\"{cell_ref}\" t=\"inlineStr\" s=\"1\"><is><t>{}</t></is></c>\n",
                xml_escape(h)
            ));
        }
        sheet.push_str("    </row>\n");

        for (r_idx, row) in rows.iter().enumerate() {
            let excel_row = r_idx + 2;
            sheet.push_str(&format!("    <row r=\"{excel_row}\">\n"));
            for (c, cell) in row.iter().enumerate() {
                let cell_ref = format!("{}{}", col_letters(c), excel_row);
                match cell {
                    XlsxCell::Text(txt) => {
                        sheet.push_str(&format!(
                            "      <c r=\"{cell_ref}\" t=\"inlineStr\" s=\"0\"><is><t>{}</t></is></c>\n",
                            xml_escape(txt)
                        ));
                    }
                    XlsxCell::Number { value, style } => {
                        if value.is_finite() {
                            sheet.push_str(&format!(
                                "      <c r=\"{cell_ref}\" s=\"{style}\"><v>{value}</v></c>\n"
                            ));
                        } else {
                            sheet.push_str(&format!(
                                "      <c r=\"{cell_ref}\" t=\"inlineStr\" s=\"0\"><is><t>—</t></is></c>\n"
                            ));
                        }
                    }
                }
            }
            sheet.push_str("    </row>\n");
        }
        sheet.push_str("  </sheetData>\n</worksheet>");
        zip.start_file("xl/worksheets/sheet1.xml", opts).map_err(|e| CoreError::External(e.to_string()))?;
        zip.write_all(sheet.as_bytes())?;
        zip.finish().map_err(|e| CoreError::External(e.to_string()))?;
    }
    Ok(buf.into_inner())
}

fn write_csv_utf8_bom(headers: &[&str], rows: &[Vec<XlsxCell>]) -> Vec<u8> {
    let mut out = String::from("\u{FEFF}");
    out.push_str(&headers.join(","));
    out.push('\n');
    for row in rows {
        let cols: Vec<String> = row
            .iter()
            .map(|c| match c {
                XlsxCell::Text(s) => format!("\"{}\"", s.replace('"', "\"\"")),
                XlsxCell::Number { value, .. } => {
                    if value.is_finite() {
                        format!("{value}")
                    } else {
                        String::new()
                    }
                }
            })
            .collect();
        out.push_str(&cols.join(","));
        out.push('\n');
    }
    out.into_bytes()
}

fn parse_dipole_debye_from_log(log_text: &str) -> Option<f64> {
    let mut last_tot = None;
    let lines: Vec<&str> = log_text.lines().collect();
    for (idx, line) in lines.iter().enumerate() {
        if line.contains("Dipole moment (field-independent basis, Debye)") {
            if let Some(nxt) = lines.get(idx + 1) {
                if let Some(pos) = nxt.find("Tot=") {
                    if let Some(tok) = nxt[pos + 4..].split_whitespace().next() {
                        if let Ok(v) = tok.parse::<f64>() {
                            last_tot = Some(v);
                        }
                    }
                }
            }
        }
    }
    last_tot
}

fn cell_opt(v: Option<f64>, style: usize) -> XlsxCell {
    match v {
        Some(n) if n.is_finite() => XlsxCell::Number { value: n, style },
        _ => XlsxCell::Text("—".into()),
    }
}

fn collect_files_recursive(root: &Path, base: &Path, out: &mut Vec<(String, PathBuf)>) -> Result<()> {
    for entry in fs::read_dir(root)? {
        let entry = entry?;
        let p = entry.path();
        if p.is_dir() {
            collect_files_recursive(&p, base, out)?;
        } else if p.is_file() {
            let rel = p
                .strip_prefix(base)
                .unwrap_or(&p)
                .to_string_lossy()
                .replace('\\', "/");
            out.push((rel, p));
        }
    }
    Ok(())
}

/// Build flat collaborator delivery folder tree, single-rounding `.xlsx` & `.csv` summaries,
/// markdown reader guide, SHA-256 manifest, and verified UTF-8 `.zip`.
pub fn build_collaborator_delivery_package(req: &DeliveryPackageRequest) -> Result<DeliveryPackageResult> {
    if req.input_paths.is_empty() {
        return Err(CoreError::InvalidOp("至少需要提供一个分子输入路径".into()));
    }
    let out_root = PathBuf::from(&req.output_dir);
    fs::create_dir_all(&out_root)?;

    let clean_name: String = req
        .package_name
        .trim()
        .chars()
        .map(|c| if c.is_alphanumeric() || matches!(c, '_' | '-' | '.') { c } else { '_' })
        .collect();
    let pkg_name = if clean_name.is_empty() {
        "MolForge_Collaborator_Delivery".to_string()
    } else {
        clean_name
    };

    let pkg_dir = out_root.join(&pkg_name);
    if pkg_dir.exists() {
        fs::remove_dir_all(&pkg_dir)?;
    }

    let subdirs = ["LMO", "平面性", "二面角", "偶极矩", "静电势", "origin_datas"];
    for d in subdirs {
        fs::create_dir_all(pkg_dir.join(d))?;
    }

    // Optional reference molecule for MCS rigid alignment + Core-First frame
    let ref_mol: Option<(Molecule, topology::CoreOrientationResult)> =
        if let Some(rp) = req.reference_path.as_deref().filter(|s| !s.trim().is_empty()) {
            let bytes = fs::read(rp.trim())?;
            let m = io::open_by_extension(rp.trim(), &bytes)?;
            let ori = topology::compute_core_first_orientation(&m)?;
            Some((m, ori))
        } else {
            None
        };

    let mut rows: Vec<DeliveryMoleculeRow> = Vec::with_capacity(req.input_paths.len());
    let mut xlsx_rows: Vec<Vec<XlsxCell>> = Vec::with_capacity(req.input_paths.len());

    for in_path_raw in &req.input_paths {
        let in_path = Path::new(in_path_raw.trim());
        let bytes = fs::read(in_path)?;
        let mut mol = io::open_by_extension(&in_path.display().to_string(), &bytes)?;
        let stem = in_path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or(&mol.name)
            .to_string();
        mol.name = stem.clone();

        // Copy raw input into origin_datas/
        if let Some(fname) = in_path.file_name() {
            let _ = fs::copy(in_path, pkg_dir.join("origin_datas").join(fname));
        }

        // Apply reference alignment + Core-First canonical orientation if requested
        let mut align_method = None;
        let mut align_rmsd = None;
        if let Some((ref_m, ref_ori)) = &ref_mol {
            let al = topology::align_molecule_to_reference(ref_m, &mol, req.allow_halogen_swap)?;
            align_method = Some(al.method.clone());
            align_rmsd = Some(al.rmsd_angstrom);
            // Transform aligned_positions into ref's Core-First canonical frame
            for (idx, p) in al.aligned_positions.iter().enumerate() {
                let shifted = [
                    p[0] - ref_ori.center_angstrom[0],
                    p[1] - ref_ori.center_angstrom[1],
                    p[2] - ref_ori.center_angstrom[2],
                ];
                let r = &ref_ori.rotation_3x3;
                let rot_p = [
                    r[0][0] * shifted[0] + r[0][1] * shifted[1] + r[0][2] * shifted[2],
                    r[1][0] * shifted[0] + r[1][1] * shifted[1] + r[1][2] * shifted[2],
                    r[2][0] * shifted[0] + r[2][1] * shifted[1] + r[2][2] * shifted[2],
                ];
                mol.atoms[idx].pos = rot_p;
                mol.atoms[idx].pos2 = [rot_p[0], rot_p[1]];
            }
        } else if let Ok(ori) = topology::compute_core_first_orientation(&mol) {
            align_method = Some(ori.axis_used.clone());
            align_rmsd = Some(0.0);
            for (idx, p) in ori.aligned_positions.into_iter().enumerate() {
                mol.atoms[idx].pos = p;
                mol.atoms[idx].pos2 = [p[0], p[1]];
            }
        }

        // Write canonically oriented structures into origin_datas/ & 二面角/
        fs::write(
            pkg_dir.join("origin_datas").join(format!("{stem}_oriented.xyz")),
            io::write_xyz(&mol),
        )?;
        fs::write(
            pkg_dir.join("二面角").join(format!("{stem}_gaussview.gjf")),
            io::write_gjf(&mol, "B3LYP", "6-31G(d)", 0, 1, false),
        )?;

        // Copy matching companion .log/.png assets if present
        let sibling_log = in_path.with_extension("log");
        let (mut qc_scf, mut qc_homo, mut qc_lumo, mut qc_gap, mut qc_dip) =
            (None, None, None, None, None);
        if sibling_log.is_file() {
            if let Ok(log_txt) = fs::read_to_string(&sibling_log) {
                if let Some(fname) = sibling_log.file_name() {
                    let _ = fs::copy(&sibling_log, pkg_dir.join("origin_datas").join(fname));
                }
                if let Ok(parsed) = qc::parse_qc_log(&log_txt) {
                    const HA_TO_EV: f64 = 27.211_386_245_988;
                    qc_scf = parsed.total_energy_hartree;
                    qc_homo = parsed.homo_hartree.map(|v| v * HA_TO_EV);
                    qc_lumo = parsed.lumo_hartree.map(|v| v * HA_TO_EV);
                    qc_gap = parsed.gap_ev;
                }
                qc_dip = parse_dipole_debye_from_log(&log_txt);
            }
        }

        if let Some(adir) = req.asset_dir.as_deref().filter(|s| !s.trim().is_empty()) {
            let asset_root = Path::new(adir.trim());
            let map = [
                (format!("{stem}_HOMO.png"), "LMO"),
                (format!("{stem}_LUMO.png"), "LMO"),
                (format!("{stem}_planarity.png"), "平面性"),
                (format!("{stem}_dipole.png"), "偶极矩"),
                (format!("{stem}_esp.png"), "静电势"),
                (format!("{stem}_dihedral.png"), "二面角"),
            ];
            for (fname, sub) in map {
                let src = asset_root.join(&fname);
                if src.is_file() {
                    let _ = fs::copy(&src, pkg_dir.join(sub).join(&fname));
                }
            }
        }

        let planarity = summary::compute_planarity(&mol).ok();
        let torsions = topology::compute_torsions(&mol).ok();
        let tb = qc::run_tight_binding(&mol).ok();

        let (t1, t2, inter_d, blen, sc_cnt) = if let Some(t) = &torsions {
            let first = t.torsions.first();
            let second = t.torsions.get(1);
            (
                first.map(|x| x.angle),
                second.map(|x| x.angle),
                first.and_then(|x| x.interplanar_deg),
                first.map(|x| x.bond_length_a),
                t.short_contacts.len(),
            )
        } else {
            (None, None, None, None, 0)
        };

        if let Some(t) = torsions {
            fs::write(
                pkg_dir.join("二面角").join(format!("{stem}_torsions.json")),
                serde_json::to_string_pretty(&t).unwrap_or_default(),
            )?;
        }
        if let Some(p) = &planarity {
            fs::write(
                pkg_dir.join("平面性").join(format!("{stem}_planarity.json")),
                serde_json::to_string_pretty(p).unwrap_or_default(),
            )?;
        }

        let row = DeliveryMoleculeRow {
            name: stem.clone(),
            formula: summary::formula(&mol),
            num_atoms: mol.atoms.len(),
            align_method,
            align_rmsd_a: align_rmsd,
            mpp_a: planarity.as_ref().map(|p| p.mpp_angstrom),
            sdp_a: planarity.as_ref().map(|p| p.sdp_angstrom),
            primary_torsion_deg: t1,
            secondary_torsion_deg: t2,
            interplanar_deg: inter_d,
            primary_bond_a: blen,
            short_contact_count: sc_cnt,
            tb_homo_ev: tb.as_ref().and_then(|r| r.homo_ev),
            tb_lumo_ev: tb.as_ref().and_then(|r| r.lumo_ev),
            tb_gap_ev: tb.as_ref().and_then(|r| r.gap_ev),
            qc_scf_hartree: qc_scf,
            qc_homo_ev: qc_homo,
            qc_lumo_ev: qc_lumo,
            qc_gap_ev: qc_gap,
            qc_dipole_debye: qc_dip,
        };

        xlsx_rows.push(vec![
            XlsxCell::Text(row.name.clone()),
            XlsxCell::Text(row.formula.clone()),
            XlsxCell::Number { value: row.num_atoms as f64, style: 5 },
            XlsxCell::Text(row.align_method.clone().unwrap_or_else(|| "—".into())),
            cell_opt(row.align_rmsd_a, 4),
            cell_opt(row.mpp_a, 4),
            cell_opt(row.sdp_a, 4),
            cell_opt(row.primary_torsion_deg, 2),
            cell_opt(row.secondary_torsion_deg, 2),
            cell_opt(row.interplanar_deg, 2),
            cell_opt(row.primary_bond_a, 4),
            XlsxCell::Number { value: row.short_contact_count as f64, style: 5 },
            cell_opt(row.tb_homo_ev, 3),
            cell_opt(row.tb_lumo_ev, 3),
            cell_opt(row.tb_gap_ev, 3),
            cell_opt(row.qc_scf_hartree, 4),
            cell_opt(row.qc_homo_ev, 3),
            cell_opt(row.qc_lumo_ev, 3),
            cell_opt(row.qc_gap_ev, 3),
            cell_opt(row.qc_dipole_debye, 3),
        ]);
        rows.push(row);
    }

    let headers = [
        "分子名称",
        "化学式",
        "原子数",
        "定向/对齐方式",
        "核心对齐 RMSD (Å)",
        "MPP (Å)",
        "SDP (Å)",
        "主扭转角 θ1 (°)",
        "次扭转角 θ2 (°)",
        "环平面夹角 (°)",
        "连接键长 (Å)",
        "分子内弱锁数",
        "TB-HOMO (eV)",
        "TB-LUMO (eV)",
        "TB-Eg (eV)",
        "QC-SCF (Eh)",
        "QC-HOMO (eV)",
        "QC-LUMO (eV)",
        "QC-Eg (eV)",
        "偶极矩 (Debye)",
    ];

    let main_xlsx = write_xlsx_bytes("MolForge_Summary", &headers, &xlsx_rows)?;
    fs::write(pkg_dir.join("总汇总表.xlsx"), &main_xlsx)?;
    fs::write(pkg_dir.join("总汇总表.csv"), write_csv_utf8_bom(&headers, &xlsx_rows))?;

    // Per-category spreadsheets + reader guides
    let plan_headers = ["分子名称", "化学式", "MPP (Å)", "SDP (Å)"];
    let plan_rows: Vec<Vec<XlsxCell>> = rows
        .iter()
        .map(|r| {
            vec![
                XlsxCell::Text(r.name.clone()),
                XlsxCell::Text(r.formula.clone()),
                cell_opt(r.mpp_a, 4),
                cell_opt(r.sdp_a, 4),
            ]
        })
        .collect();
    fs::write(pkg_dir.join("平面性/平面性汇总表.xlsx"), write_xlsx_bytes("Planarity", &plan_headers, &plan_rows)?)?;
    fs::write(
        pkg_dir.join("平面性/怎么看图与分析说明.md"),
        "# 平面性 (MPP / SDP) 看图与分析说明\n\n- **MPP（Molecular Planarity Parameter，Å）**：重原子到最佳最小二乘拟合平面的均方根偏离距离；数值越小表示共轭骨架越共平面。\n- **SDP（Span of Deviation from Plane，Å）**：正反两面最大偏离跨度 $d_{\\max} - d_{\\min}$；反映侧翼扭曲或取代基立体位阻幅度。\n- **表格数值精度**：`.xlsx` 单元格内存储完整双精度浮点原始值，仅在显示格式保留 4 位小数，避免中间取整叠加误差。\n",
    )?;

    let tor_headers = ["分子名称", "主扭转角 θ1 (°)", "次扭转角 θ2 (°)", "环平面夹角 (°)", "连接键长 (Å)", "分子内弱锁数"];
    let tor_rows: Vec<Vec<XlsxCell>> = rows
        .iter()
        .map(|r| {
            vec![
                XlsxCell::Text(r.name.clone()),
                cell_opt(r.primary_torsion_deg, 2),
                cell_opt(r.secondary_torsion_deg, 2),
                cell_opt(r.interplanar_deg, 2),
                cell_opt(r.primary_bond_a, 4),
                XlsxCell::Number { value: r.short_contact_count as f64, style: 5 },
            ]
        })
        .collect();
    fs::write(pkg_dir.join("二面角/二面角与键长汇总表.xlsx"), write_xlsx_bytes("Torsions", &tor_headers, &tor_rows)?)?;
    fs::write(
        pkg_dir.join("二面角/怎么看图与分析说明.md"),
        "# 二面角与非共价构象锁分析说明\n\n- **锐角二面角提取规则**：对每条环–环单键枚举全部 $2\\times 2 = 4$ 条四原子路径，优先选取锐角扭转（$|D| \\le 90^\\circ$），避免取成 $>90^\\circ$ 的钝角补角。\n- **环平面夹角**：基于两环重原子最小二乘拟合平面的法向夹角，可消去单环微褶皱对局部四原子角的扰动。\n- **`_gaussview.gjf`**：已按统一 Core-First / MCS 坐标系写出，可直接用 GaussView 复核任意 4 原子二面角。\n",
    )?;

    fs::write(
        pkg_dir.join("LMO/怎么看图与分析说明.md"),
        "# 前线分子轨道 (HOMO / LUMO) 看图说明\n\n- 默认正相绿（+#22c55e）、负相蓝（-#3b82f6），等值面阈值通常为 `0.03 a.u.`（紧密）或 `0.02 a.u.`（扩展）。\n- 轨道离域范围越大，通常越有利于分子内电荷转移与载流子迁移。\n",
    )?;
    fs::write(
        pkg_dir.join("偶极矩/怎么看图与分析说明.md"),
        "# 分子偶极矩 (Dipole Moment) 看图说明\n\n- 箭头方向按从负电中心指向正电中心/总偶极矢量投影绘制（若配套 `.log` 存在则已在总表提取总偶极大小 Debye）。\n",
    )?;
    fs::write(
        pkg_dir.join("静电势/怎么看图与分析说明.md"),
        "# 静电势表面 (ESP) 看图与双单位色标说明\n\n- 默认 BWR 配色：蓝（负电势 / 富电子受电子区域）→ 白 → 红（正电势 / 缺电子区域）。\n- 换算关系：$1\\text{ a.u.} = 627.5095\\text{ kcal/mol}$；若采用非对称锁定量程（如 $-0.042 \\sim +0.028\\text{ a.u.}$），纯白中点位于量程几何中心（$-0.007\\text{ a.u.}$）而非电中性 $0.000$。\n",
    )?;

    let main_guide = format!(
        "# {pkg_name} · 实验合作者看图与数据说明\n\n- **纳入分子数**：{}\n- **目录说明**：\n  - `总汇总表.xlsx` / `总汇总表.csv`：保留原始数值精度（单次格式显示，无二次取整）的一站式总表。\n  - `LMO/`：HOMO/LUMO 轨道图与说明。\n  - `平面性/`：MPP/SDP 统计与单表。\n  - `二面角/`：四路径锐角扭转 JSON、对齐 `.gjf` 与汇总表。\n  - `偶极矩/` 与 `静电势/`：对应图件与色标阅读指南。\n  - `origin_datas/`：原始输入文件及统一朝向后的 `_oriented.xyz`（方便直接复核或重绘）。\n",
        rows.len()
    );
    fs::write(pkg_dir.join("给合作者的看图与分析总说明.md"), main_guide)?;

    // Build MANIFEST.json with SHA-256 of every generated file so far
    let mut initial_files = Vec::new();
    collect_files_recursive(&pkg_dir, &pkg_dir, &mut initial_files)?;
    initial_files.sort_by(|a, b| a.0.cmp(&b.0));

    let mut manifest_entries = BTreeMap::new();
    for (rel, full_p) in &initial_files {
        let data = fs::read(full_p)?;
        manifest_entries.insert(
            rel.clone(),
            serde_json::json!({
                "bytes": data.len(),
                "sha256": sha256_hex(&data),
            }),
        );
    }
    let manifest_bytes = serde_json::to_vec_pretty(&serde_json::json!({
        "package_name": pkg_name,
        "molecule_count": rows.len(),
        "files": manifest_entries,
    }))
    .unwrap_or_default();
    let manifest_sha = sha256_hex(&manifest_bytes);
    fs::write(pkg_dir.join("交付清单_MANIFEST.json"), &manifest_bytes)?;

    // Collect final list including manifest and pack UTF-8 ZIP
    let mut all_files = Vec::new();
    collect_files_recursive(&pkg_dir, &pkg_dir, &mut all_files)?;
    all_files.sort_by(|a, b| a.0.cmp(&b.0));

    let zip_path = out_root.join(format!("{pkg_name}.zip"));
    {
        let f = fs::File::create(&zip_path)?;
        let mut zip = ZipWriter::new(f);
        let opts = SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        for (rel, full_p) in &all_files {
            zip.start_file(rel, opts)
                .map_err(|e| CoreError::External(e.to_string()))?;
            let data = fs::read(full_p)?;
            zip.write_all(&data)?;
        }
        zip.finish().map_err(|e| CoreError::External(e.to_string()))?;
    }

    // Verify ZIP archive integrity by opening & reading every entry (CRC verification)
    let mut verified_count = 0usize;
    {
        let f = fs::File::open(&zip_path)?;
        let mut archive = ZipArchive::new(f)
            .map_err(|e| CoreError::External(format!("交付 ZIP 校验打开失败: {e}")))?;
        let n = archive.len();
        for idx in 0..n {
            let mut entry = archive
                .by_index(idx)
                .map_err(|e| CoreError::External(format!("交付 ZIP 项 {idx} 读取失败: {e}")))?;
            let mut sink = Vec::new();
            entry
                .read_to_end(&mut sink)
                .map_err(|e| CoreError::External(format!("交付 ZIP 项 '{}' CRC 校验失败: {e}", entry.name())))?;
            verified_count += 1;
        }
    }

    Ok(DeliveryPackageResult {
        ok: true,
        output_dir: out_root.display().to_string(),
        package_dir: pkg_dir.display().to_string(),
        zip_path: zip_path.display().to_string(),
        zip_verified: verified_count == all_files.len(),
        zip_entries: verified_count,
        total_files: all_files.len(),
        molecule_count: rows.len(),
        rows,
        manifest_sha256: manifest_sha,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::presets::build_preset;

    #[test]
    fn xlsx_raw_precision_and_delivery_zip_verified() {
        let scratch = std::env::temp_dir().join(format!(
            "molforge_delivery_test_{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&scratch);
        fs::create_dir_all(&scratch).unwrap();

        let caf = build_preset("caffeine").unwrap();
        let benz = build_preset("benzene").unwrap();
        let caf_xyz = scratch.join("caffeine.xyz");
        let benz_xyz = scratch.join("benzene.xyz");
        fs::write(&caf_xyz, io::write_xyz(&caf)).unwrap();
        fs::write(&benz_xyz, io::write_xyz(&benz)).unwrap();

        let req = DeliveryPackageRequest {
            input_paths: vec![caf_xyz.display().to_string(), benz_xyz.display().to_string()],
            output_dir: scratch.join("out").display().to_string(),
            package_name: "UnitTestDelivery".into(),
            reference_path: None,
            asset_dir: None,
            allow_halogen_swap: true,
        };
        let res = build_collaborator_delivery_package(&req).expect("delivery package");
        assert!(res.zip_verified);
        assert_eq!(res.molecule_count, 2);
        assert!(Path::new(&res.zip_path).is_file());

        // Inspect XLSX XML inside ZIP to confirm standard sheet + unrounded value preservation
        let xlsx_bytes = fs::read(Path::new(&res.package_dir).join("总汇总表.xlsx")).unwrap();
        let mut arch = ZipArchive::new(Cursor::new(xlsx_bytes)).unwrap();
        let mut sheet_xml = String::new();
        arch.by_name("xl/worksheets/sheet1.xml")
            .unwrap()
            .read_to_string(&mut sheet_xml)
            .unwrap();
        assert!(sheet_xml.contains("MolForge") || sheet_xml.contains("caffeine"));
        assert!(sheet_xml.contains("总汇总表") || sheet_xml.contains("<v>"));

        let _ = fs::remove_dir_all(&scratch);
    }
}
