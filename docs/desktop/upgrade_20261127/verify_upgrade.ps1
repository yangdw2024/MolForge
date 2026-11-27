# MolForge Studio 8.1 (2026-11-27 升级版) 全量 API 与科学计算内核验收脚本
$ErrorActionPreference = 'Stop'
Remove-Item Env:HTTP_PROXY, Env:HTTPS_PROXY, Env:ALL_PROXY -ErrorAction SilentlyContinue

$base = 'http://127.0.0.1:18765'
$ev = 'E:\YDW\Trae_Chemdraw\docs\desktop\upgrade_20261127\evidence'
New-Item -ItemType Directory -Force -Path $ev | Out-Null

function Post($p, $obj) {
  Invoke-RestMethod -Uri "$base$p" -Method Post -Body ($obj | ConvertTo-Json -Depth 10) -ContentType 'application/json; charset=utf-8' -TimeoutSec 600
}
function GetJ($p) {
  Invoke-RestMethod -Uri "$base$p" -TimeoutSec 60
}
function Save($name, $obj) {
  $obj | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath "$ev\$name.json" -Encoding UTF8
}

$report = [System.Collections.Generic.List[object]]::new()
function Step($id, $desc, $block) {
  try {
    $r = & $block
    $report.Add([pscustomobject]@{ id=$id; desc=$desc; status='PASS'; detail=$r })
    Write-Output "[PASS] $id $desc :: $r"
  } catch {
    $msg = $_.Exception.Message
    $report.Add([pscustomobject]@{ id=$id; desc=$desc; status='FAIL'; detail=$msg })
    Write-Output "[FAIL] $id $desc :: $msg"
  }
}

Step 'U01' '/api/health calchem=true' {
  $h = GetJ '/api/health'
  Save 'u01_health' $h
  if (-not $h.ok -or -not $h.calchem) { throw "ok=$($h.ok) calchem=$($h.calchem)" }
  "version=$($h.version) calchem=$($h.calchem)"
}

Step 'U02' '/api/engines/status CalChem 0.3.0' {
  $e = GetJ '/api/engines/status'
  Save 'u02_engines' $e
  $cc = $e.engines | Where-Object { $_.id -eq 'calchem' }
  if (-not $cc.available -or $cc.version_hint -ne '0.3.0') { throw "cc=$($cc | ConvertTo-Json -Compress)" }
  "calchem=$($cc.version_hint) available=$($cc.available)"
}

Step 'U03' 'CalChem v0.3.0 HF/STO-3G + dipole + n_ao' {
  Post '/api/build/preset' @{ id='water' } | Out-Null
  $r = Post '/api/qc/run_calchem' @{ mode='sp'; method='hf'; basis='STO-3G' }
  Save 'u03_calchem_hf' $r
  if (-not $r.ok -or $null -eq $r.dipole_magnitude_debye -or $r.n_ao -ne 7) { throw "bad calchem hf: $($r | ConvertTo-Json -Compress)" }
  "E=$($r.total_energy_hartree) dip=$($r.dipole_magnitude_debye) nao=$($r.n_ao)"
}

Step 'U04' 'CalChem v0.3.0 rks + B3LYP/STO-3G' {
  $r = Post '/api/qc/run_calchem' @{ mode='sp'; method='rks'; basis='STO-3G' }
  Save 'u04_calchem_rks' $r
  if (-not $r.ok -or -not $r.converged -or $null -eq $r.dipole_magnitude_debye) { throw "bad rks: $($r | ConvertTo-Json -Compress)" }
  "E=$($r.total_energy_hartree) dip=$($r.dipole_magnitude_debye)"
}

Step 'U05' 'jobs/submit calchem_sp 统一契约' {
  $j = Post '/api/jobs/submit' @{ kind='calchem_sp'; label='CalChem job contract test'; params=@{ method='b3lyp'; basis='STO-3G' } }
  $jid = $j.job.job_id
  $me = $null
  for ($i=0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 300
    $me = (GetJ '/api/jobs').jobs | Where-Object { $_.job_id -eq $jid }
    if ($me.status -in @('completed','failed')) { break }
  }
  Save 'u05_job_calchem' $me
  if ($me.status -ne 'completed' -or -not $me.result.ok -or $null -eq $me.result.dipole_magnitude_debye) { throw "status=$($me.status) res=$($me.result | ConvertTo-Json -Compress)" }
  "ok=$($me.result.ok) homo_ev=$($me.result.homo_ev) dip=$($me.result.dipole_magnitude_debye)"
}

Step 'U06' 'PROP-MPP 纯 Rust 平面性 (benzene & caffeine)' {
  Post '/api/build/preset' @{ id='benzene' } | Out-Null
  $rb = Post '/api/analysis/run' @{ analysis_id='PROP-MPP' }
  Save 'u06_mpp_benzene' $rb
  if (-not $rb.ok -or $rb.result.metrics.mpp_angstrom -gt 0.01) { throw "benz mpp=$($rb.result.metrics.mpp_angstrom)" }
  Post '/api/build/preset' @{ id='caffeine' } | Out-Null
  $rc = Post '/api/analysis/run' @{ analysis_id='PROP-MPP' }
  Save 'u06_mpp_caffeine' $rc
  if (-not $rc.ok -or $rc.result.plot_x.Count -lt 10) { throw "caf pts=$($rc.result.plot_x.Count)" }
  "benz_mpp=$($rb.result.metrics.mpp_angstrom) caf_mpp=$($rc.result.metrics.mpp_angstrom)"
}

Step 'U07' 'MD-RDF analysis/run + jobs/submit + workflow' {
  $ra = Post '/api/analysis/run' @{ analysis_id='MD-RDF' }
  Save 'u07_rdf_analysis' $ra
  if (-not $ra.ok -or $ra.result.plot_x.Count -ne 80) { throw "rdf plot=$($ra.result.plot_x.Count)" }

  $jm = Post '/api/jobs/submit' @{ kind='md_rdf'; label='RDF bg job' }
  $mid = $jm.job.job_id
  $me = $null
  for ($i=0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 250
    $me = (GetJ '/api/jobs').jobs | Where-Object { $_.job_id -eq $mid }
    if ($me.status -in @('completed','failed')) { break }
  }
  Save 'u07_rdf_job' $me
  if ($me.status -ne 'completed' -or -not $me.result.ok) { throw "job status=$($me.status)" }

  $pl = Post '/api/ai/plan_workflow' @{ query='对当前体系做分子动力学径向分布函数 RDF 分析' }
  Save 'u07_rdf_plan' $pl
  if (-not $pl.proposal.runnable) { throw "plan runnable=$($pl.proposal.runnable) reason=$($pl.proposal.status_reason)" }

  $wf = Post '/api/workflows/run' @{ workflow_id='org.molforge.workflow.md-rdf'; approved=$true }
  Save 'u07_rdf_workflow' $wf
  if ($wf.run.status -ne 'completed' -or -not $wf.run.provenance.input_molecule_sha256) { throw "wf status=$($wf.run.status)" }
  "peak=$($ra.result.metrics.first_peak_r_angstrom)A wf=$($wf.run.status) sha=$($wf.run.provenance.input_molecule_sha256.Substring(0,12))"
}

Step 'U08' 'OSC 4-char workflow (TB + MPP + Torsion)' {
  $wf = Post '/api/workflows/run' @{ workflow_id='org.molforge.workflow.osc-4char'; approved=$true }
  Save 'u08_osc_workflow' $wf
  if ($wf.run.status -ne 'completed' -or $wf.run.node_records.Count -lt 4) { throw "status=$($wf.run.status) nodes=$($wf.run.node_records.Count)" }
  "status=$($wf.run.status) nodes=$($wf.run.node_records.Count)"
}

Step 'U09' 'Multiwfn 4项能力 (WFN-12/01/06/08 + 裸坐标拒假)' {
  $fchk = 'D:\YDW\MolForge_Scratch\probe_mwfn_20261127\ch2o.fchk'
  $w12 = Post '/api/analysis/run' @{ analysis_id='WFN-12' }
  Save 'u09_wfn12' $w12
  if (-not $w12.ok -or $w12.result.metrics.total_scatter_points -lt 1000) { throw "wfn12 fail" }

  $w01_no = Post '/api/analysis/run' @{ analysis_id='WFN-01' }
  Save 'u09_wfn01_nowfn' $w01_no
  if ($w01_no.ok) { throw "WFN-01 without fchk should reject honestly" }

  $w01 = Post '/api/analysis/run_multiwfn' @{ analysis_id='WFN-01'; input_file=$fchk }
  Save 'u09_wfn01_esp' $w01
  if (-not $w01.ok -or $null -eq $w01.metrics.vs_min_kcal -or $null -eq $w01.metrics.mpi_kcal) { throw "wfn01 fail: $($w01.message)" }

  $w06 = Post '/api/analysis/run_multiwfn' @{ analysis_id='WFN-06'; input_file=$fchk }
  Save 'u09_wfn06_mayer' $w06
  if (-not $w06.ok -or $w06.metrics.bond_count -lt 3) { throw "wfn06 fail: $($w06.message)" }

  $w08 = Post '/api/analysis/run_multiwfn' @{ analysis_id='WFN-08'; input_file=$fchk }
  Save 'u09_wfn08_adch' $w08
  if (-not $w08.ok -or $w08.metrics.atom_count -ne 4) { throw "wfn08 fail: $($w08.message)" }

  "nci_pts=$($w12.result.metrics.total_scatter_points) esp_min=$($w01.metrics.vs_min_kcal) mayer_bonds=$($w06.metrics.bond_count) adch_atoms=$($w08.metrics.atom_count)"
}

Step 'U10' 'GROMACS 5文件返回契约 + 四点法重组能' {
  $gmx = Post '/api/md/generate_gromacs' @{ temp_k=300; nsteps_md=100000 }
  Save 'u10_gromacs' $gmx
  if (-not $gmx.ok -or -not $gmx.files.'minim.mdp' -or -not $gmx.files.'run_gmx.sh') { throw "gromacs files missing" }

  $re = Post '/api/qc/reorganization_energy' @{ carrier='hole'; e_n_n=-100.010; e_n_i=-100.005; e_i_i=-99.810; e_i_n=-99.805 }
  Save 'u10_reorg' $re
  if (-not $re.ok -or [math]::Abs($re.lambda_total_hartree - 0.01) -gt 1e-6) { throw "reorg=$($re | ConvertTo-Json -Compress)" }
  "gmx_files=$((($gmx.files | Get-Member -MemberType NoteProperty).Count)) lambda_mev=$($re.lambda_total_mev)"
}

Step 'U11' 'C盘Temp零残留 + D盘Scratch隔离校验' {
  $ctemp = Get-ChildItem "$env:TEMP" -Filter "molforge*" -ErrorAction SilentlyContinue
  if ($ctemp) { throw "Found in C Temp: $($ctemp.FullName -join ', ')" }
  $dscratch = Get-ChildItem "D:\YDW\MolForge_Scratch" -Filter "molforge_mwfn*" -ErrorAction SilentlyContinue
  if (-not $dscratch) { throw "No mwfn scratch found on D:" }
  "C_temp=0 D_mwfn_dirs=$($dscratch.Count)"
}

Save 'upgrade_report' $report
$fails = @($report | Where-Object { $_.status -eq 'FAIL' }).Count
Write-Output "`n[UPGRADE VERIFY] TOTAL=$($report.Count) PASS=$($report.Count - $fails) FAIL=$fails"
if ($fails -gt 0) { exit 1 }
