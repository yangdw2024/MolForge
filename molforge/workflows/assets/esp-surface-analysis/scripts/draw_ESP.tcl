# ==============================================================================
# draw_ESP.tcl
# 离屏渲染 Multiwfn ESPrhoiso 输出的 0.001 a.u. 电子密度等值面 + ESP 着色
# 用法:
#   vmd -dispdev text -e draw_ESP.tcl -args \
#       <mol.pdb> <surfanalysis.pdb> <density.cub> <esp.cub> <outname.bmp> \
#       [isoval] [colorlow] [colorhigh]
# 例:
#   vmd -dispdev text -e draw_ESP.tcl -args \
#       ClFFCl_mol.pdb ClFFCl_surfanalysis.pdb \
#       ydw-BTP-ClFFCl_density.cub ydw-BTP-ClFFCl_totesp.cub ClFFCl_esp.bmp \
#       0.001 -0.065 0.045
# 若 colorlow/colorhigh 传 auto 或留空，则用 VMD 数据自动极值。
# 视觉参数对齐用户已校准的 draw_ESP.vmd（BWR / EdgyGlass / 正交投影）。
# ==============================================================================

set molpdbname      [lindex $argv 0]
set surfana_pdbname [lindex $argv 1]
set dens_cub_name   [lindex $argv 2]
set esp_cub_name    [lindex $argv 3]
set outname         [lindex $argv 4]
set isoval_raw      [lindex $argv 5]
if {$isoval_raw eq ""} { set isoval 0.001 } else { set isoval $isoval_raw }
set colorlow_arg    [lindex $argv 6]
set colorhigh_arg   [lindex $argv 7]

# ===================== 全局渲染参数 =====================
color scale method BWR
color Display Background white
axes location Off
display depthcue off
display rendermode GLSL
light 2 on
light 3 on

# ===================== EdgyGlass 材质 =====================
material change transparency EdgyGlass 1.0
material change specular EdgyGlass 0.15
material change shininess EdgyGlass 0.95
material change opacity EdgyGlass 0.7
material change outlinewidth EdgyGlass 0.9
material change outline EdgyGlass 0

# ===================== 分子骨架 CPK =====================
mol new $molpdbname
mol modstyle 0 top CPK 1.000000 0.300000 22.000000 0.000000

# ===================== cube 表面 + ESP 着色 =====================
mol new $dens_cub_name
mol addfile $esp_cub_name
set cubid [molinfo top]

mol addrep $cubid
mol modstyle 0 $cubid Isosurface $isoval 0 0 0 1 1
mol modmaterial 0 $cubid EdgyGlass
mol modcolor 0 $cubid Volume 1

if {$colorlow_arg ne "" && $colorlow_arg ne "auto" && $colorhigh_arg ne "" && $colorhigh_arg ne "auto"} {
    mol scaleminmax $cubid 0 $colorlow_arg $colorhigh_arg
    puts "Color scale (a.u.): $colorlow_arg ~ $colorhigh_arg"
} else {
    puts "Color scale: auto (VMD data extrema)"
}

# ===================== ESP 极值点小球 =====================
mol new $surfana_pdbname
set exid [molinfo top]

# 极大值点 name=C -> 红色小球 (colorid 32)
mol modstyle 0 $exid VDW 0.07 20
mol modselect 0 $exid {name C}
mol modcolor 0 $exid colorid 32

# 极小值点 name=O -> 蓝色小球 (colorid 21)
mol addrep $exid
mol modstyle 1 $exid VDW 0.07 20
mol modselect 1 $exid {name O}
mol modcolor 1 $exid colorid 21

# ===================== 投影 & 视角 =====================
display projection Orthographic
display resetview
# 自动放大让分子填满画面（与 render_one.tcl 校准值对齐）
scale by 1.25
scale by 1.25
scale by 1.25
display resize 1600 1600

# ===================== 离屏渲染 BMP =====================
render Tachyon $outname "D:/VMD/tachyon_WIN64.exe" -aasamples 12 %s -format BMP -o $outname

puts "=================================================="
puts "ESP surface render finished"
puts "Output: $outname"
puts "mol: $molpdbname"
puts "density cube: $dens_cub_name"
puts "ESP cube: $esp_cub_name"
puts "=================================================="
quit
