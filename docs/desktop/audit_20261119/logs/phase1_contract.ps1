# Phase1 零404契约回归 — 真实调用5条历史丢失路由
$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:18765'
$ev = 'E:\YDW\Trae_Chemdraw\docs\desktop\audit_20261119\evidence\api'
$results = @()

function Test-Route {
    param([string]$Name, [string]$Method, [string]$Path, [hashtable]$Body)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        if ($Method -eq 'POST') {
            $json = ($Body | ConvertTo-Json -Depth 8)
            $resp = Invoke-WebRequest -Uri "$base$Path" -Method Post -Body ([System.Text.Encoding]::UTF8.GetBytes($json)) -ContentType 'application/json; charset=utf-8' -TimeoutSec 120
        } else {
            $resp = Invoke-WebRequest -Uri "$base$Path" -Method Get -TimeoutSec 120
        }
        $sw.Stop()
        $ct = $resp.Headers['Content-Type']
        $isJson = $false; $parsed = $null
        try { $parsed = $resp.Content | ConvertFrom-Json; $isJson = $true } catch {}
        $resp.Content | Set-Content -LiteralPath "$ev\$Name.json" -Encoding utf8
        $script:results += [pscustomobject]@{
            Route = $Path; HTTP = $resp.StatusCode; ContentType = $ct; ValidJson = $isJson
            ElapsedMs = [math]::Round($sw.Elapsed.TotalMilliseconds, 1)
            Bytes = $resp.Content.Length
            OkField = if ($isJson -and $null -ne $parsed.PSObject.Properties['ok']) { $parsed.ok } else { 'n/a' }
        }
    } catch {
        $sw.Stop()
        $code = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 'EXC' }
        $script:results += [pscustomobject]@{
            Route = $Path; HTTP = $code; ContentType = ''; ValidJson = $false
            ElapsedMs = [math]::Round($sw.Elapsed.TotalMilliseconds, 1); Bytes = 0; OkField = $_.Exception.Message
        }
    }
}

# 记录初始内存
$p0 = Get-Process -Id 33584
"WS_before_MB=$([math]::Round($p0.WorkingSet64/1MB,2))" | Set-Content "$ev\memory_probe.txt"

Test-Route -Name 'contract_health' -Method GET -Path '/api/health'
Test-Route -Name 'contract_inspect_smiles' -Method POST -Path '/api/library/inspect_smiles' -Body @{ items = @(@{ smiles = 'CC(=O)Oc1ccccc1C(=O)O'; name = '阿司匹林'; category = '药物' }, @{ smiles = 'Cn1cnc2c1c(=O)n(C)c(=O)n2C'; name = '咖啡因'; category = '生物碱' }) }
Test-Route -Name 'contract_clean3d' -Method POST -Path '/api/edit/clean_3d' -Body @{}
Test-Route -Name 'contract_insert_fragment' -Method POST -Path '/api/edit/insert_fragment' -Body @{ fragment_id = 'phenyl'; anchor_atom_id = 0; attach_to_existing = $true }
Test-Route -Name 'contract_run_external' -Method POST -Path '/api/qc/run_external' -Body @{ engine = 'orca'; keywords = '! B3LYP def2-SVP Opt'; workdir = 'E:\YDW\Trae_Chemdraw\docs\desktop\audit_20261119\evidence\engines' }
Test-Route -Name 'contract_ai_chat' -Method POST -Path '/api/ai/chat' -Body @{ prompt = '分析该体系前线轨道分布与亲电位点' }

# 恢复文档为咖啡因（插入片段改变了拓扑）
Invoke-RestMethod -Uri "$base/api/build/preset" -Method Post -Body '{"id":"caffeine"}' -ContentType 'application/json' | Out-Null

# 内存/死锁压力：200 次 health + 20 次并发
$sw = [System.Diagnostics.Stopwatch]::StartNew()
1..200 | ForEach-Object { Invoke-RestMethod "$base/api/health" | Out-Null }
$sw.Stop()
"health_200_sequential_ms=$([math]::Round($sw.Elapsed.TotalMilliseconds,1))" | Add-Content "$ev\memory_probe.txt"
$jobs = 1..20 | ForEach-Object { Start-ThreadJob { (Invoke-WebRequest 'http://127.0.0.1:18765/api/health' -TimeoutSec 10).StatusCode } }
$codes = $jobs | Wait-Job -Timeout 30 | Receive-Job
$jobs | Remove-Job -Force
"health_20_parallel_codes=$($codes -join ',')" | Add-Content "$ev\memory_probe.txt"
$p1 = Get-Process -Id 33584
"WS_after_MB=$([math]::Round($p1.WorkingSet64/1MB,2))" | Add-Content "$ev\memory_probe.txt"
"Handles=$($p1.HandleCount) Threads=$($p1.Threads.Count)" | Add-Content "$ev\memory_probe.txt"

$results | Format-Table -AutoSize | Out-String -Width 220
$results | Export-Csv "$ev\contract_matrix.csv" -NoTypeInformation -Encoding utf8
Get-Content "$ev\memory_probe.txt"