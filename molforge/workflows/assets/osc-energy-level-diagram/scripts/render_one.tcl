# =====================================================================
# render_one.tcl
# 用法: vmd -dispdev text -e render_one.tcl -args cube文件 输出名 等值面
# 风格完全对齐 D:/YDW/.../LMO/render_homo.vmd 的最终成品参数
# 注释可中文，puts 输出英文避免乱码
# =====================================================================

set cubefile [lindex $argv 0]
set outname  [lindex $argv 1]
set isoval   [lindex $argv 2]

# 全局显示设置：白底、关闭深度雾、关坐标轴
light 3 on
color Display Background white
display depthcue off
display rendermode GLSL
axes location Off

# C 元素改为论文用棕褐色 tan
color Name C tan
color change rgb tan 0.700000 0.560000 0.360000

# Opaque 材质：CPK 原子骨架
material change mirror Opaque 0.15
material change outline Opaque 4.000000
material change outlinewidth Opaque 0.500000
material change ambient Opaque 0.080000
material change mirror Opaque 0.000000

# Glossy 材质：轨道等值面半透明光滑
material change ambient Glossy 0.100000
material change diffuse Glossy 0.600000
material change opacity Glossy 0.750000
material change shininess Glossy 1.000000

# 载入 cube（含分子结构 + 轨道格点）
mol new $cubefile type {cube} first 0 last -1 step 1 waitfor 1

# rep0: CPK 原子骨架
mol modstyle 0 top CPK 0.800000 0.300000 22.000000 22.000000

# rep1: 正相位等值面 ColorID12 绿色
mol addrep top
mol modstyle 1 top Isosurface $isoval 0 0 0 1 1
mol modcolor 1 top ColorID 12
mol modmaterial 1 top Glossy

# rep2: 负相位等值面 ColorID22 蓝色
mol addrep top
mol modstyle 2 top Isosurface -$isoval 0 0 0 1 1
mol modcolor 2 top ColorID 22
mol modmaterial 2 top Glossy

# 视角自适应 + 弱透视
display resetview
display distance -7.000000
display height 10.000000
light 3 on

# 对齐参考脚本：连续放大使分子填满画面（已校准为6次，完整入镜不裁切）
scale by 1.200000
scale by 1.200000
scale by 1.200000
scale by 1.200000
scale by 1.200000
scale by 1.200000

# 输出分辨率 1200x1200
display resize 1200 1200

# Tachyon 离线光线追踪渲染为 BMP
render Tachyon $outname "D:/VMD/tachyon_WIN64.exe" -aasamples 12 %s -format BMP -o $outname.bmp

mol delete top
puts "RENDER DONE: $outname.bmp"
quit
