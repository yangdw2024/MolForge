# Render planarity deviation (d_s) from pqr file
# Usage: drag-and-drop pqr into VMD, then: source render_planarity.tcl

set molid [molinfo top]
mol delrep 0 $molid

# CPK representation, colored by Charge field (holds d_s value)
mol representation CPK 1.0 0.3 12.0 12.0
mol color Charge
mol selection all
mol addrep $molid

# BWR color scale (blue-white-red)
color scale method BWR

# White background
color Display Background white
axes location off
display projection orthographic
display antialias on
display depthcue off

display update

puts "====================================="
puts "Planarity rendering complete"
puts " - CPK colored by d_s (plane deviation)"
puts " - BWR color scale: blue=in-plane, red=out-of-plane"
puts "====================================="
