# render_straight.tcl - ??????
set cubefile [lindex $argv 0]
set outname  [lindex $argv 1]
set isoval   [lindex $argv 2]

light 3 on
color Display Background white
display depthcue off
display rendermode GLSL
axes location Off
color Name C tan
color change rgb tan 0.700000 0.560000 0.360000

material change mirror Opaque 0.15
material change outline Opaque 4.000000
material change outlinewidth Opaque 0.500000
material change ambient Opaque 0.080000
material change mirror Opaque 0.000000
material change ambient Glossy 0.100000
material change diffuse Glossy 0.600000
material change opacity Glossy 0.750000
material change shininess Glossy 1.000000

mol new $cubefile type {cube} first 0 last -1 step 1 waitfor 1
mol modstyle 0 top CPK 0.800000 0.300000 22.000000 22.000000

mol addrep top
mol modstyle 1 top Isosurface $isoval 0 0 0 1 1
mol modcolor 1 top ColorID 12
mol modmaterial 1 top Glossy

mol addrep top
mol modstyle 2 top Isosurface -$isoval 0 0 0 1 1
mol modcolor 2 top ColorID 22
mol modmaterial 2 top Glossy

display projection orthographic
display resetview
rotate x by 90
scale by 1.5
display resize 1200 1200

render Tachyon $outname "D:/VMD/tachyon_WIN64.exe" -aasamples 12 %s -format BMP -o $outname.bmp
mol delete top
puts "RENDER DONE: $outname.bmp"
quit
