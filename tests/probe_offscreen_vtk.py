"""Native VTK render smoke; runs in an isolated subprocess, not in Qt event handlers.

Exit 0 only if a PNG was actually rasterized. Needs GPU/Mesa/EGL at runtime.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import vtk

from molforge.rendering.glyph_scene import prepare_instances,GlyphMoleculeScene
from molforge.domain.ids import AtomId,BondId

def main(out:str):
    renderer=vtk.vtkRenderer()
    window=vtk.vtkRenderWindow()
    window.SetSize(640,400)
    window.SetOffScreenRendering(1)
    window.AddRenderer(renderer)
    renderer.SetBackground(.08,.12,.18)
    scene=GlyphMoleculeScene(renderer)
    atom_ids=[AtomId(10),AtomId(11),AtomId(12)]
    bond_ids=[BondId(20),BondId(21)]
    buffers=prepare_instances(
        np.array([[-1.25,0,0],[0.35,0,0],[1.8,.2,0]],dtype=np.float32),
        np.array([6,8,7],dtype=np.int32),atom_ids,
        [(0,1,1),(1,2,2)],bond_ids,
        atom_scales={atom_ids[1]:1.8},
        atom_colors={atom_ids[1]:(1,0.1,0.08)},
        bond_widths={bond_ids[1]:1.9},
        bond_colors={bond_ids[1]:(0.15,1.,0.4)},
    )
    scene.update(buffers)
    renderer.ResetCamera()
    renderer.GetActiveCamera().Azimuth(20)
    renderer.GetActiveCamera().Elevation(18)
    renderer.ResetCameraClippingRange()
    window.Render()
    filt=vtk.vtkWindowToImageFilter()
    filt.SetInput(window)
    filt.Update()
    writer=vtk.vtkPNGWriter()
    writer.SetInputConnection(filt.GetOutputPort())
    writer.SetFileName(str(out))
    writer.Write()
    img=vtk.vtkPNGReader()
    img.SetFileName(str(out))
    img.Update()
    dims=img.GetOutput().GetDimensions()
    assert dims[:2]==(640,400),dims
    assert Path(out).stat().st_size>1500
    print("VTK rendered",dims,"PNG bytes",Path(out).stat().st_size)
if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("Usage: python -m tests.probe_offscreen_vtk <out.png>")
    main(sys.argv[1])
