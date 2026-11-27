# 前后端契约错配实测（全部真实调用，证据落盘）
$base = 'http://127.0.0.1:18765'
$ev = 'E:\YDW\Trae_Chemdraw\docs\desktop\audit_20261119\evidence\api'
$log = @()

function Call($name, $path, $body) {
    $json = $body | ConvertTo-Json -Depth 8
    try {
        $r = Invoke-WebRequest -Uri "$base$path" -Method Post -Body ([Text.Encoding]::UTF8.GetBytes($json)) -ContentType 'application/json; charset=utf-8' -TimeoutSec 60
        $r.Content | Set-Content "$ev\mismatch_$name.json" -Encoding utf8
        return ($r.Content | ConvertFrom-Json)
    } catch {
        $msg = $_.ErrorDetails.Message
        if (-not $msg) { $msg = $_.Exception.Message }
        $msg | Set-Content "$ev\mismatch_$name.json" -Encoding utf8
        return ($msg | ConvertFrom-Json -ErrorAction SilentlyContinue)
    }
}

# 重置为苯（6原子，便于观察删除/成环）
Invoke-RestMethod "$base/api/build/preset" -Method Post -Body '{"id":"benzene"}' -ContentType 'application/json' | Out-Null
$doc0 = Invoke-RestMethod "$base/api/document"
$log += "T0 benzene atoms=$($doc0.num_atoms)"

# T1 前端 deleteAtoms 真实载荷 {atom_ids:[...]}（api.ts:271-275）
$atoms = Invoke-RestMethod "$base/api/atoms"
$aid = $atoms.atoms[0].atom_id
$r1 = Call 'delete_atoms_frontend_payload' '/api/edit/delete_atoms' @{ atom_ids = @($aid) }
$log += "T1 delete_atoms(atom_ids=[$aid]) -> ok=$($r1.ok) atoms=$($r1.document.num_atoms) (期望删除后5，若仍6=静默失效)"

# T2 后端正确字段 {ids:[...]}
$r2 = Call 'delete_atoms_backend_payload' '/api/edit/delete_atoms' @{ ids = @($aid) }
$log += "T2 delete_atoms(ids=[$aid]) -> ok=$($r2.ok) atoms=$($r2.document.num_atoms)"
Invoke-RestMethod "$base/api/edit/undo" -Method Post -Body '{}' -ContentType 'application/json' | Out-Null

# T3 前端 moveAtom 真实载荷 {atom_id,pos_2d}（api.ts:266-270）
$r3 = Call 'move_atom_frontend_payload' '/api/edit/move_atom' @{ atom_id = $aid; pos_2d = @(2.0, 1.0) }
$log += "T3 move_atom(pos_2d) -> ok=$($r3.ok) error=$($r3.error)"

# T4 前端 exportQcInput kind=rest（api.ts:293-297）
$r4 = Call 'export_input_kind_rest' '/api/qc/export_input' @{ kind = 'rest'; route = 'b3lyp def2-SVP' }
$head = ($r4.content -split "`n")[0..2] -join ' | '
$log += "T4 export_input(kind=rest) -> engine=$($r4.engine) 首行: $head (若为 gjf 格式=kind 被忽略)"

# T5 CalChem（前端 mode=sp）
$r5 = Call 'run_calchem' '/api/qc/run_calchem' @{ mode = 'sp'; method = 'B3LYP'; basis = 'STO-3G' }
$log += "T5 run_calchem -> available=$($r5.available) converged=$($r5.converged) E=$($r5.total_energy_hartree) msg=$($r5.message)"

# T6 前端保存 AI Key（api.ts:317-328 发送 api_key）
Invoke-RestMethod "$base/api/preferences" -Method Post -Body '{"api_key":"sk-TEST-AUDIT-KEY","base_url":"https://api.deepseek.com/v1","model":"deepseek-chat"}' -ContentType 'application/json' | Out-Null
$p = Invoke-RestMethod "$base/api/preferences"
$p | ConvertTo-Json | Set-Content "$ev\mismatch_preferences_after_save.json" -Encoding utf8
$log += "T6 preferences after save: api_key=$($p.api_key) ai_api_key=$($p.ai_api_key) (chat 读取 ai_api_key → 若两者不同=设置页 Key 不生效)"

# T7 add_ring 前端 center_2d 载荷
$r7 = Call 'add_ring_center2d' '/api/edit/add_ring' @{ size = 5; aromatic = $true; hetero = @{ '0' = 16 }; center_2d = @(5.0, 5.0) }
$atoms7 = Invoke-RestMethod "$base/api/atoms"
$new5 = $atoms7.atoms | Select-Object -Last 5
$zs = ($new5 | ForEach-Object { $_.symbol }) -join ','
$pos = ($new5 | ForEach-Object { "($([math]::Round($_.x,2)),$([math]::Round($_.y,2)))" }) -join ' '
$log += "T7 add_ring(size5,hetero{0:S},center_2d[5,5]) -> 新原子符号=$zs 坐标=$pos (若全C且中心在原点=hetero/center_2d 均被忽略)"

# T8 键级循环序列（右键菜单设键级实际走此路由）
Invoke-RestMethod "$base/api/build/preset" -Method Post -Body '{"id":"benzene"}' -ContentType 'application/json' | Out-Null
$a8 = Invoke-RestMethod "$base/api/atoms"
$b0 = $a8.bonds[0]
$seq = @("初始 order=$($b0.order) arom=$($b0.aromatic)")
1..4 | ForEach-Object {
    $rr = Invoke-RestMethod "$base/api/edit/cycle_bond_order" -Method Post -Body (@{bond_id=$b0.bond_id}|ConvertTo-Json) -ContentType 'application/json'
    $aa = Invoke-RestMethod "$base/api/atoms"
    $bb = $aa.bonds | Where-Object bond_id -eq $b0.bond_id
    $seq += "cycle$_ -> order=$($bb.order) arom=$($bb.aromatic)"
}
$log += "T8 键级循环: $($seq -join '; ') (无4=芳香键不可达)"
$seq | Set-Content "$ev\mismatch_bond_cycle.txt" -Encoding utf8

# 恢复咖啡因
Invoke-RestMethod "$base/api/build/preset" -Method Post -Body '{"id":"caffeine"}' -ContentType 'application/json' | Out-Null
# 清理测试 Key（恢复为空，避免污染）
Invoke-RestMethod "$base/api/preferences" -Method Post -Body '{"api_key":"","base_url":"","model":"deepseek-chat"}' -ContentType 'application/json' | Out-Null

$log | Set-Content "$ev\mismatch_summary.txt" -Encoding utf8
$log