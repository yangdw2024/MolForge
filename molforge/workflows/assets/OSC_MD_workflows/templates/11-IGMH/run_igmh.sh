#!/bin/bash
# run_igmh.sh —— Multiwfn IGMH 分析批处理模板
# 模板来源：Ternary_Datas/igmh 工作流（11 文档）
#
# 前置：Gaussian 单点生成 {NAME}.fchk（或 .wfn），D/A 两片段原子区间已知。
# 输入选择（示例，Multiwfn 交互）：
#   主功能 20（IGM）-> 选 IGMH（Hirshfeld 划分）
#   -> 定义两片段原子 -> 计算 sign(lambda2)rho
#   -> 设等值面 isovalue=0.004 -> 输出 .pdb（B 因子存色值）
set -e

# ============ 配置 ============
MULTIWFN="Multiwfn"
NAME="${1:-frag}"                 # 输入 fchk 前缀
ISOVAL="0.004"
OUTPDB="${NAME}-igmh.pdb"
# =============================

# 片段原子区间（按实际 D/A 结构填；Multiwfn 中即 prompt 值）
FRAG1="1-85"      # 片段1（如受体）
FRAG2="86-231"    # 片段2（如给体）

# 交互输入模板（Multiwfn 菜单编号需按实际版本核对！）
$MULTIWFN "${NAME}.fchk" <<EOF
20
3
${FRAG1}
${FRAG2}
2
0.004
3
0
EOF

echo "IGMH 结果请用 VMD 打开 .pdb，按 B 因子（= sign(lambda2)rho）着色："
echo "  蓝=吸引(负) / 绿=弱相互作用(近零) / 红=排斥(正)"
