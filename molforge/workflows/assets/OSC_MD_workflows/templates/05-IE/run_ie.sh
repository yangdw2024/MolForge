#!/bin/bash
# run_ie.sh —— 组分间相互作用能分解（energygrps + rerun）命令序列模板
# 模板来源：Ternary_Datas/IE/gmx相互作用.docx（05 文档）
#
# 原理：对 A/B/C 三组分分别构建 7 种拓扑（A,B,C,AB,AC,BC,complex），
#       用同一段轨迹 rerun 重算势能，再按 E_int(X-Y)=E(XY)-E(X)-E(Y) 相减。
#
# 用法：先在当前目录准备好 {A,B,C,AB,AC,BC}.top 与 indexABC.ndx、md.mdp、
#       以及轨迹文件 TRAJ 与参考结构 GRO 与 TPR。
set -e

# ============ 配置 ============
GMX="gmx_mpi"
TRAJ="ply-md3.part0004.xtc"   # 轨迹
GRO="ply-md3.part0004.gro"    # 参考结构（取一帧）
MDMDP="md.mdp"                # 与生产一致的 mdp
INDEX="indexABC.ndx"          # 定义 A/B/C 三组的索引
TB="65000"                    # 起始时间（ps，末段平衡窗口）
TE="70000"                    # 结束时间（ps）
GROUPS="A B C AB AC BC"       # 要处理的拓扑
# =============================

extract_energy () {
    # $1=组名
    local g=$1
    $GMX trjconv -f "$TRAJ" -s "$TPR_REF" -n "$INDEX" -o ${g}.xtc -b $TB -e $TE
    $GMX trjconv -f "$GRO"  -s "$TPR_REF" -n "$INDEX" -o ${g}.gro
    $GMX grompp -f "$MDMDP" -c ${g}.gro -p ${g}.top -o ${g}.tpr
    $GMX mdrun -s ${g}.tpr -rerun ${g}.xtc -e ${g}.edr
    for comp in LJ-SR Disper-corr Coul-SR Coul-recip; do
        # 交互选择项：LJ-SR=7, Disper-corr=8, Coul-SR=9, Coul-recip=10（按 gmx energy 列表核对）
        $GMX energy -f ${g}.edr -o ${g}-${comp}.xvg <<EOF
${comp}
0
EOF
    done
    echo "完成: $g"
}

for g in $GROUPS; do
    extract_energy $g
done

echo "全部能量提取完成。"
echo "相互作用能 = E(AB)-E(A)-E(B)（各能量分量分别相减），汇总见 05 文档。"
