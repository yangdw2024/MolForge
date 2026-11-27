# MolForge Studio v8.2 P0-P2 End-to-End Backend & Artifact Verification
$ErrorActionPreference = "Stop"

foreach ($v in @("HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","http_proxy","https_proxy","all_proxy")) {
  [Environment]::SetEnvironmentVariable($v, $null, "Process")
}

$base = "http://127.0.0.1:18765"
$scratch = "D:\YDW\MolForge_Scratch\v82_p0_p2_verify"
Remove-Item -Recurse -Force $scratch -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $scratch | Out-Null

$pass = 0; $fail = 0
function Record([string]$name, [bool]$ok, [string]$detail) {
  if ($ok) { $script:pass++; Write-Output "[PASS] $name :: $detail" }
  else     { $script:fail++; Write-Output "[FAIL] $name :: $detail" }
}
function PostJson([string]$path, [hashtable]$body) {
  $json = $body | ConvertTo-Json -Depth 10 -Compress
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
  return Invoke-RestMethod -Uri "$base$path" -Method Post -ContentType "application/json; charset=utf-8" -Body $bytes -TimeoutSec 60
}

# Build a naphthyl-phenyl twisted test XYZ + scrambled rotated copy in D: scratch
$napPhRef = @"
16
NaphthylPhenylRef
C   -1.210000    0.700000    0.000000
C    0.000000    1.400000    0.000000
C    1.210000    0.700000    0.000000
C    1.210000   -0.700000    0.000000
C    0.000000   -1.400000    0.000000
C   -1.210000   -0.700000    0.000000
C    2.420000    1.400000    0.000000
C    3.630000    0.700000    0.000000
C    3.630000   -0.700000    0.000000
C    2.420000   -1.400000    0.000000
C    5.100000    0.700000    0.000000
C    5.800000    1.599200    0.809600
C    7.200000    1.599200    0.809600
C    7.900000    0.700000    0.000000
C    7.200000   -0.199200   -0.809600
C    5.800000   -0.199200   -0.809600
"@
$refPath = "$scratch\Mol_Ref.xyz"
[System.IO.File]::WriteAllText($refPath, $napPhRef, [System.Text.UTF8Encoding]::new($false))

# Same molecule rotated + shifted AND atom order reversed (to force MCS subgraph matching)
$py = "D:\YDW\Trae_Gromacs\miniconda3\python.exe"
$scrPath = "$scratch\Mol_Scrambled.xyz"
$pyPrep = @"
import math
lines = open(r'$refPath').read().splitlines()[2:]
atoms = [(l.split()[0], [float(x) for x in l.split()[1:4]]) for l in lines]
cz, sz = math.cos(1.1), math.sin(1.1)
cx, sx = math.cos(-0.7), math.sin(-0.7)
rot = []
for sym, (x, y, z) in reversed(atoms):
    x1, y1, z1 = cz*x - sz*y, sz*x + cz*y, z
    x2, y2, z2 = x1 + 9.4, cx*y1 - sx*z1 - 4.2, sx*y1 + cx*z1 + 3.1
    rot.append((sym, x2, y2, z2))
with open(r'$scrPath', 'w', encoding='utf-8') as f:
    f.write(f'{len(rot)}\nScrambledCopy\n')
    for sym, x, y, z in rot:
        f.write(f'{sym} {x:.6f} {y:.6f} {z:.6f}\n')
"@
$pyPrep | & $py -

# V01: Open NaphthylPhenylRef & run PROP-TORSION
$openRes = PostJson "/api/open" @{ path = $refPath }
$torRes = PostJson "/api/analysis/run" @{ analysis_id = "PROP-TORSION" }
$cw = $torRes.result.metrics.torsions | Where-Object { $_.type -eq "core-wing" } | Select-Object -First 1
$ok1 = $openRes.ok -and $torRes.ok -and ($null -ne $cw) -and ([Math]::Abs($cw.angle) -le 90.0) -and ($cw.interplanar_deg -gt 35)
Record "V01 PROP-TORSION 拓扑核-翼锐角二面角与环面夹角" $ok1 "angle=$($cw.angle) inter=$($cw.interplanar_deg) blen=$($cw.bond_length_a)"

# V02: Core-First orientation endpoint + apply
$oriRes = PostJson "/api/geometry/orient" @{ apply = $true }
$ok2 = $oriRes.ok -and $oriRes.orientation.axis_used -eq "core" -and $oriRes.orientation.core_atoms.Count -eq 10 -and ($null -ne $oriRes.document)
Record "V02 /api/geometry/orient Core-First 确定性定向" $ok2 "axis=$($oriRes.orientation.axis_used) core=$($oriRes.orientation.core_atoms.Count)"

# V03: osc-4char workflow now includes torsion node (5 nodes: validate, tb, mpp, torsion, viz)
$wfRes = PostJson "/api/workflows/run" @{ workflow_id = "org.molforge.workflow.osc-4char"; approved = $true }
$ok3 = $wfRes.ok -and $wfRes.run.status -eq "completed" -and $wfRes.run.node_records.Count -eq 5
Record "V03 osc-4char 工作流集成 PROP-TORSION 节点" $ok3 "status=$($wfRes.run.status) nodes=$($wfRes.run.node_records.Count)"

# V04: Multi-molecule order-independent MCS rigid alignment on reversed-atom rotated molecule
$alRes = PostJson "/api/geometry/align_batch" @{
  reference_path = $refPath
  target_paths = @($scrPath)
  allow_halogen_swap = $true
}
$item = $alRes.items[0]
$ok4 = $alRes.ok -and $item.ok -and $item.method -eq "mcs_kabsch" -and $item.rmsd_angstrom -lt 0.05
Record "V04 /api/geometry/align_batch 打乱编号 MCS+Kabsch 对齐" $ok4 "method=$($item.method) matched=$($item.matched_count) rmsd=$($item.rmsd_angstrom)"

# V05: One-click batch collaborator delivery package (.xlsx + .zip + CRC)
$delRes = PostJson "/api/delivery/build_package" @{
  input_paths = @($refPath, $scrPath)
  output_dir = "$scratch\out"
  package_name = "Test_OPV_Delivery"
  reference_path = $refPath
  allow_halogen_swap = $true
}
$zipVerifyOut = & $py -c "import zipfile, xml.etree.ElementTree as ET; z=zipfile.ZipFile(r'$($delRes.zip_path)'); bad=z.testzip(); xdata=z.read('总汇总表.xlsx'); import io; xz=zipfile.ZipFile(io.BytesIO(xdata)); root=ET.fromstring(xz.read('xl/worksheets/sheet1.xml')); print('BAD='+str(bad)+' SHEET_OK='+str(len(list(root))))" 2>&1
$ok5 = $delRes.ok -and $delRes.zip_verified -and ($delRes.molecule_count -eq 2) -and ($zipVerifyOut -match "BAD=None SHEET_OK=")
Record "V05 /api/delivery/build_package 交付打包 + .xlsx + ZIP CRC校验" $ok5 "files=$($delRes.total_files) $zipVerifyOut"

# Check C Temp clean
$cRem = @(Get-ChildItem "$env:TEMP" -Filter "molforge*" -ErrorAction SilentlyContinue).Count
Record "V06 C盘 Temp 零残留检查" ($cRem -eq 0) "C_temp=$cRem"

Write-Output ""
Write-Output "[V8.2 VERIFY] TOTAL=$($pass + $fail) PASS=$pass FAIL=$fail"
if ($fail -gt 0) { exit 1 }
