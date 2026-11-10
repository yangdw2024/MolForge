# Dipole moment arrow rendering in VMD
# Usage: drag-and-drop xyz/pdb into VMD, then: source render_dipole.tcl

# ==================== 在这里修改参数 ====================
# 片段定义（根据你的分子修改 serial 范围）
set sel1 "(serial 1 to 10) or (serial 20 to 25)"
set sel2 "(serial 11 to 19) or (serial 26 to 42)"
set sel3 "(serial 43 to 52)"

# 偶极矩矢量 (a.u.) — 从 Multiwfn 输出里复制
set dip1x -3.619951
set dip1y 0.010993
set dip1z 0.377859

set dip2x -0.000751
set dip2y -0.961283
set dip2z -0.000052

set dip3x 3.620771
set dip3y 0.010982
set dip3z -0.378040

# 总偶极矩
set totalx 0.000069
set totaly -0.939308
set totalz -0.000233

# 箭头参数
set scl 1.2
set rad 0.12
# ========================================================

# Draw arrow procedure (from Multiwfn)
proc drawarrow {atmrange fragdx fragdy fragdz {scl 1} {rad 0.2} {showgoc 1}} {
    set sel [atomselect top $atmrange]
    set cen [measure center $sel]
    set cenx [lindex $cen 0]
    set ceny [lindex $cen 1]
    set cenz [lindex $cen 2]
    if {$showgoc==1} {puts "Geometry center: $cenx $ceny $cenz"}
    set fragdx [expr $fragdx*$scl]
    set fragdy [expr $fragdy*$scl]
    set fragdz [expr $fragdz*$scl]
    set body 0.75
    set begx [expr $cenx-$fragdx/2]
    set begy [expr $ceny-$fragdy/2]
    set begz [expr $cenz-$fragdz/2]
    set endx [expr $cenx+$fragdx*$body-$fragdx/2]
    set endy [expr $ceny+$fragdy*$body-$fragdy/2]
    set endz [expr $cenz+$fragdz*$body-$fragdz/2]
    draw cylinder "$begx $begy $begz" "$endx $endy $endz" radius $rad filled yes resolution 20
    set endx2 [expr $cenx+$fragdx/2]
    set endy2 [expr $ceny+$fragdy/2]
    set endz2 [expr $cenz+$fragdz/2]
    draw cone "$endx $endy $endz" "$endx2 $endy2 $endz2" radius [expr $rad*2.5] resolution 20
}

# Display settings
draw delete all
color Display Background white
axes location off
display projection orthographic
display antialias on
display depthcue off
light 0 on
light 1 off
light 2 on
light 3 off

# CPK representation
mol delrep all 0
mol rep CPK 1.0 0.3 8.0 8.0
mol addrep 0

# Draw fragment dipoles
color green
drawarrow $sel1 $dip1x $dip1y $dip1z $scl $rad 1

color red
drawarrow $sel2 $dip2x $dip2y $dip2z $scl $rad 1

color yellow
drawarrow $sel3 $dip3x $dip3y $dip3z $scl $rad 1

# Draw total dipole (blue, thicker)
color blue
drawarrow all $totalx $totaly $totalz $scl 0.14 1

puts "====================================="
puts "Dipole arrows drawn"
puts " Green: fragment 1"
puts " Red:   fragment 2"
puts " Yellow: fragment 3"
puts " Blue:  total dipole"
puts "====================================="
