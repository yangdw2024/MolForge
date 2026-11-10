#!/bin/bash
# run_esp.sh —— Multiwfn 分子表面静电势（ESP）定量分析批处理模板
# 模板来源：Ternary_Datas/数据/ESP 工作流（12 文档）
#
# 前置：Gaussian 单点生成 {NAME}.fchk
# 输出：逐原子 ESP 统计（全/正/负区域平均与方差，kcal/mol）
set -e
MULTIWFN="Multiwfn"

for fchk in "$@"; do
    [ -f "$fchk" ] || { echo "跳过不存在: $fchk"; continue; }
    base="${fchk%.fchk}"
    # 主功能 12 = 定量分子表面分析（Multiwfn 菜单编号按版本核对）
    $MULTIWFN "$fchk" <<EOF > "${base}_surfanalysis.txt"
12
0
EOF
    echo "完成: ${base}_surfanalysis.txt"
done
