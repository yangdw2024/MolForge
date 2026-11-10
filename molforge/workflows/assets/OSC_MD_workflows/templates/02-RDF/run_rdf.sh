#!/bin/bash
# run_rdf.sh —— gmx rdf 批量计算模板（骨架级 / 片段级）
# 模板来源：Ternary_Datas/RDF 工作流（02 文档）
#
# 用法：
#   1) 先用 extract_atoms.py 生成各组原子号文件（*.out）；
#   2) 将各组写入 index.ndx（或 gmx rdf -sel 直接读原子号文件）；
#   3) 修改下方变量后执行。
set -e

# ============ 配置 ============
GMX="gmx_mpi"                 # 集群版 gmx_mpi / 单机 gmx
TPR="ply-md3.tpr"             # 拓扑文件
TRAJ="ply-md3.part0004.xtc"   # 轨迹（或 .gro 单帧）
INDEX="index.ndx"             # 索引文件
OUTDIR="rdf_out"
mkdir -p "$OUTDIR"

# 需要计算的组对（gmx rdf 的 -sel 语法，按需增删）
# 示例（三元体系）：D 给体 / A1 HDO / A2 BTn
SEL_DA1='group D_grp  and  group A1_grp'
SEL_A1A1='group A1_grp  and  group A1_grp'
SEL_A1A2='group A1_grp  and  group A2_grp'
# =============================

for pair in DA1 A1A1 A1A2; do
    sel_var="SEL_${pair}"
    eval "sel=\${$sel_var}"
    $GMX rdf -s "$TPR" -f "$TRAJ" -n "$INDEX" \
             -sel "$sel" -o "$OUTDIR/$pair.xvg" -xvg none
    echo "完成: $pair -> $OUTDIR/$pair.xvg"
done

echo "全部 RDF 计算完成。用 Origin 导入 $OUTDIR/*.xvg 成图。"
