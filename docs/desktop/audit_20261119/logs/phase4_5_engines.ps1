# Phase4/5 科学引擎与Hub工作流真实实测（全部真实调用+进程级证据）
$base = 'http://127.0.0.1:18765'
$ev = 'E:\YDW\Trae_Chemdraw\docs\desktop\audit_20261119\evidence\engines'
$log = @()
function Post($name, $path, $body, $timeoutSec = 180) {
    $json = $body | ConvertTo-Json -Depth 10
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try {
        $r = Invoke-WebRequest -Uri "$base$path" -Method Post -Body ([Text.Encoding]::UTF8.GetBytes($json)) -ContentType 'application/json; charset=utf-8' -TimeoutSec $timeoutSec
        $sw.Stop()
        $r.Content | Set-Content "$ev\$name.json" -Encoding utf8
        $p = $r.Content | ConvertFrom-Json
        return @{ ok = $true; ms = [math]::Round($sw.Elapsed.TotalMilliseconds, 1); data = $p; status = $r.StatusCode }
    } catch {
        $sw.Stop()
        $msg = if ($_.ErrorDetails.Message) { $_.ErrorDetails.Message } else { $_.Exception.Message }
        $msg | Set-Content "$ev\$name.json" -Encoding utf8
        return @{ ok = $false; ms = [math]::Round($sw.Elapsed.TotalMilliseconds, 1); data = ($msg | ConvertFrom-Json -ErrorAction SilentlyContinue); status = 'ERR'; err = $msg }
    }
}

# 0. 阿司匹林 SMILES 真实生成（RDKit worker）
$r0 = Post 'p4_build_aspirin' '/api/build/smiles' @{ smiles = 'CC(=O)Oc1ccccc1C(=O)O'; name = 'Aspirin' }
$log += "P4-0 SMILES阿司匹林: status=$($r0.status) ms=$($r0.ms) formula=$($r0.data.document.formula) atoms=$($r0.data.document.num_atoms)"

# 1. Tight-Binding 前线轨道
$r1 = Post 'p4_tight_binding' '/api/qc/tight_binding' @{}
$tb = $r1.data
$log += "P4-1 TB: ms=$($r1.ms) pi_atoms=$($tb.num_pi_atoms) pi_e=$($tb.num_pi_electrons) HOMO=$($tb.homo_ev) LUMO=$($tb.lumo_ev) Eg=$($tb.gap_ev) MO数=$($tb.mo_energies_ev.Count) 跃迁数=$($tb.transitions.Count)"
if ($tb.transitions.Count -gt 0) { $log += "      S1: λ=$($tb.transitions[0].wavelength_nm)nm f=$($tb.transitions[0].oscillator_f)" }

# 2. Clean3D 后键长合理性（真实RDKit MMFF）
Post 'p4_clean3d' '/api/edit/clean_3d' @{} | Out-Null
$atoms = (Invoke-RestMethod "$base/api/atoms")
$cc = @(); $co = @()
foreach ($b in $atoms.bonds) {
    $a1 = $atoms.atoms[$b.i]; $a2 = $atoms.atoms[$b.j]
    $d = [math]::Sqrt(($a1.x-$a2.x)*($a1.x-$a2.x)+($a1.y-$a2.y)*($a1.y-$a2.y)+($a1.z-$a2.z)*($a1.z-$a2.z))
    if ($a1.symbol -eq 'C' -and $a2.symbol -eq 'C') { $cc += $d }
    if (($a1.symbol -eq 'C' -and $a2.symbol -eq 'O') -or ($a1.symbol -eq 'O' -and $a2.symbol -eq 'C')) { $co += $d }
}
$ccAvg = if ($cc.Count) { [math]::Round(($cc | Measure-Object -Average).Average, 4) } else { 'n/a' }
$coAvg = if ($co.Count) { [math]::Round(($co | Measure-Object -Average).Average, 4) } else { 'n/a' }
$log += "P4-2 Clean3D键长: C-C平均=$ccAvg Å (期望1.35-1.55), C-O平均=$coAvg Å (期望1.2-1.45)"

# 2b. 测量HUD用2D坐标 vs 真实3D坐标偏差（EditorView.tsx:120-121 用 x2/y2）
$pair = $atoms.bonds[0]
$p1 = $atoms.atoms[$pair.i]; $p2 = $atoms.atoms[$pair.j]
$d2d = [math]::Sqrt(($p1.x2-$p2.x2)*($p1.x2-$p2.x2)+($p1.y2-$p2.y2)*($p1.y2-$p2.y2))
$d3d = [math]::Sqrt(($p1.x-$p2.x)*($p1.x-$p2.x)+($p1.y-$p2.y)*($p1.y-$p2.y)+($p1.z-$p2.z)*($p1.z-$p2.z))
$log += "P4-2b 测量偏差: 键#0 2D布局距离=$([math]::Round($d2d,4))Å vs 真实3D距离=$([math]::Round($d3d,4))Å (HUD显示2D值,非真实空间距离)"

# 3. xTB 真实外部进程
$r3 = Post 'p4_run_xtb' '/api/qc/run_xtb' @{ method = 'gfn2'; optimize = $true } 300
$xtb = $r3.data
$log += "P4-3 xTB: ms=$($r3.ms) exit=$($xtb.exit_code) E=$($xtb.energy_hartree) Eh workdir=$($xtb.workdir)"
if ($xtb.workdir -and (Test-Path $xtb.workdir)) {
    $files = Get-ChildItem $xtb.workdir | Select-Object -ExpandProperty Name
    $log += "      workdir文件: $($files -join ', ')"
    if (Test-Path "$($xtb.workdir)\xtbopt.xyz") { $log += "      xtbopt.xyz存在=True (真实优化产物)" }
    $xtb.stdout | Set-Content "$ev\xtb_stdout_full.txt" -Encoding utf8
    $tail = ($xtb.stdout -split "`n" | Select-Object -Last 12) -join ' | '
    $log += "      stdout尾: $tail"
}

# 4. Multiwfn WFN-12（宣称NCI/RDG）真实进程核验
$r4 = Post 'p4_multiwfn_wfn12' '/api/analysis/run_multiwfn' @{ analysis_id = 'WFN-12' } 120
$mw = $r4.data
$log += "P4-4 Multiwfn: ms=$($r4.ms) ok=$($mw.ok) msg=$($mw.message)"
$log += "      plot_y前6=$($mw.plot_y[0..5] -join ',') (若等于原子序数6,6,6,8...=假散点)"
$log += "      x_label=$($mw.x_label) y_label=$($mw.y_label)"
$mw.stdout_tail | Set-Content "$ev\multiwfn_stdout_tail.txt" -Encoding utf8
$log += "      stdout_tail: $($mw.stdout_tail -replace "`n",' | ')"
# 进程级交叉验证：直接用相同菜单序列跑 Multiwfn，捕获完整日志
$mwExe = 'D:\Multiwfn\Multiwfn_3.8_bin_Win64\Multiwfn.exe'
if (Test-Path $mwExe) {
    $tmp = "$ev\mwfn_crosscheck"; New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    $xyz = (Invoke-RestMethod "$base/api/export" -Method Post -Body '{"format":"xyz"}' -ContentType 'application/json').content
    $xyz | Set-Content "$tmp\input.xyz" -Encoding ascii
    "100`n1`n0`nq`n" | Set-Content "$tmp\cmds.txt" -Encoding ascii
    $p = Start-Process -FilePath $mwExe -ArgumentList 'input.xyz' -WorkingDirectory $tmp -RedirectStandardInput "$tmp\cmds.txt" -RedirectStandardOutput "$tmp\full_stdout.txt" -RedirectStandardError "$tmp\stderr.txt" -NoNewWindow -PassThru -Wait
    $log += "P4-4b Multiwfn交叉验证: exit=$($p.ExitCode) 完整日志=$tmp\full_stdout.txt"
    $head = Get-Content "$tmp\full_stdout.txt" -TotalCount 40 | Where-Object { $_ -match 'function|menu|task|NCI|RDG|promolecular|100|Loading|原子|功能' } | Select-Object -First 10
    $log += "      关键行: $($head -join ' | ')"
}

# 5. 量化输入生成器合法性
foreach ($eng in @('gaussian','orca','xtb')) {
    $r = Post "p4_export_$eng" '/api/qc/export_input' @{ engine = $eng; method = 'B3LYP'; basis = 'def2-SVP' }
    $content = $r.data.content
    $content | Set-Content "$ev\input_$eng.txt" -Encoding utf8
    $nLines = ($content -split "`n").Count
    $log += "P4-5 export($eng): ms=$($r.ms) 行数=$nLines 首行=$(($content -split "`n")[0])"
}
# gjf 原子数/电荷自旋校验
$gjf = Get-Content "$ev\input_gaussian.txt" -Raw
$hasChargeMult = $gjf -match '0 1'
$atomBlock = ($gjf -split "`n" | Where-Object { $_ -match '^\s*[A-Z][a-z]?\s+[-\d]' }).Count
$log += "P4-5b gjf校验: 电荷自旋行'0 1'=$hasChargeMult 坐标行数=$atomBlock (阿司匹林21原子)"

# 6. CalChem（feature未编译）
$r6 = Post 'p4_calchem' '/api/qc/run_calchem' @{ method = 'HF'; basis = 'STO-3G'; optimize = $false }
$log += "P4-6 CalChem: available=$($r6.data.available) converged=$($r6.data.converged) E=$($r6.data.total_energy_hartree) msg=$($r6.data.message)"

# 7. 后台任务真实性（orca_sp 应真实执行?）
$r7 = Post 'p4_job_orca_sp' '/api/jobs/submit' @{ kind = 'orca_sp'; label = 'AUDIT ORCA SP'; params = @{ keywords = '! HF STO-3G' } }
$jid = $r7.data.job.job_id
Start-Sleep -Seconds 2
$jobs = (Invoke-RestMethod "$base/api/jobs").jobs
$j = $jobs | Where-Object job_id -eq $jid
$log += "P4-7 后台orca_sp任务: status=$($j.status) result=$($j.result | ConvertTo-Json -Compress) logs=$($j.logs -join '; ')"
$log += "      (若result仅{ok,num_atoms}且无ORCA进程输出=假完成)"

# 8. Hub 搜索匹配
$h1 = Invoke-RestMethod "$base/api/hub/resources?query=HOMO"
$h2 = Invoke-RestMethod "$base/api/hub/resources?query=MD"
$log += "P5-1 Hub搜索HOMO: 命中=$($h1.items.Count) 首项=$($h1.items[0].name) runnable=$($h1.items[0].runnable)"
$log += "P5-1b Hub搜索MD: 命中=$($h2.items.Count) 首项=$($h2.items[0].name)"
$h1 | ConvertTo-Json -Depth 6 | Set-Content "$ev\hub_search_homo.json" -Encoding utf8

# 9. AI 工作流规划
$r9 = Post 'p5_plan_homolumo' '/api/ai/plan_workflow' @{ query = '计算当前分子的HOMO/LUMO与能隙' }
$prop = $r9.data.proposal
$log += "P5-2 规划HOMO/LUMO: wf=$($prop.selected_workflow.id) runnable=$($prop.runnable) skills=$($prop.matched_skills.Count) reason=$($prop.status_reason)"
$r9b = Post 'p5_plan_md' '/api/ai/plan_workflow' @{ query = 'MD 轨迹 RDF 分析' }
$log += "P5-2b 规划MD: wf=$($r9b.data.proposal.selected_workflow.id) runnable=$($r9b.data.proposal.runnable) missing=$($r9b.data.proposal.missing_dependencies -join ',')"

# 10. 执行 frontier-mo 工作流 → Provenance
$r10 = Post 'p5_run_frontier_mo' '/api/workflows/run' @{ workflow_id = 'org.molforge.workflow.frontier-mo'; approved = $true }
$run = $r10.data.run
$prov = $run.provenance
$log += "P5-3 工作流执行: status=$($run.status) run_id=$($run.run_id)"
$log += "      分子SHA256=$($prov.input_molecule_sha256)"
$log += "      工作流SHA256=$($prov.workflow_sha256)"
$log += "      节点耗时: $(($run.node_records | ForEach-Object { "$($_.node_id)=$($_.duration_ms)ms[$($_.status)]" }) -join ', ')"
$log += "      匹配技能: $($prov.matched_skill_ids -join ', ')"
# 独立复算 SHA256 验证溯源真实性
$xyzNow = (Invoke-RestMethod "$base/api/export" -Method Post -Body '{"format":"xyz"}' -ContentType 'application/json').content
$bytes = [Text.Encoding]::UTF8.GetBytes($xyzNow)
$sha = [Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
$shaHex = ([BitConverter]::ToString($sha) -replace '-','').ToLower()
$log += "P5-3b SHA256独立复算: $shaHex 匹配=$($shaHex -eq $prov.input_molecule_sha256)"

# 11. xtb-preopt 工作流（审批门+真实外部进程）
$r11a = Post 'p5_xtb_wf_noapprove' '/api/workflows/run' @{ workflow_id = 'org.molforge.workflow.xtb-preopt'; approved = $false }
$log += "P5-4 xtb工作流未审批: status=$($r11a.data.run.status) (期望pending_approval)"
$r11b = Post 'p5_xtb_wf_approved' '/api/workflows/run' @{ workflow_id = 'org.molforge.workflow.xtb-preopt'; approved = $true } 300
$log += "P5-4b xtb工作流已审批: status=$($r11b.data.run.status) 节点=$(($r11b.data.run.node_records | ForEach-Object { "$($_.node_id):$($_.status):$($_.duration_ms)ms" }) -join ', ')"

# 12. calchem 工作流（应诚实失败而非假成功）
$r12 = Post 'p5_calchem_wf' '/api/workflows/run' @{ workflow_id = 'org.molforge.workflow.calchem-sp-opt'; approved = $true }
$log += "P5-5 calchem工作流: status=$($r12.data.run.status) error=$($r12.data.run.error) (期望blocked/failed,不假成功)"

# 恢复咖啡因
Invoke-RestMethod "$base/api/build/preset" -Method Post -Body '{"id":"caffeine"}' -ContentType 'application/json' | Out-Null
$log | Set-Content "$ev\phase4_5_summary.txt" -Encoding utf8
$log