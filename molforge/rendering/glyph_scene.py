"""
True per-object VTK rendering for MolForge v4.

Two persistent, batched vtkGlyph3DMapper actors (atoms and bonds), not one actor
per atom. The VTK arrays are created from the Domain's stable AtomId/BondId
styles. Selection is a tint on the *actual atom glyph*, never a fake overlaid
sphere. No QWidget, Qt event loop or WebEngine import is needed by this module.

Atoms: unit sphere scaled by one float radius per AtomId.
Bonds: unit cylinder along +X, oriented along each bond and scaled by
(length, radius, radius). Double/triple bonds use parallel cylinders; an
aromatic bond is represented by two lanes as a visual approximation (its
aromatic *chemical* semantics stay in Domain).

This backend is appropriate for small/medium molecules. Benchmarks/LOD are
still required before claiming million-atom performance.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping
import numpy as np

try:
    import vtk
    from vtk.util import numpy_support
except ImportError:  # Pure NumPy preparation can still be validated.
    vtk = None
    numpy_support = None

BASE_VDW_RADII = {1: 1.10, 5: 1.80, 6: 1.70, 7: 1.55, 8: 1.52,
                  9: 1.47, 14: 2.10, 15: 1.80, 16: 1.80,
                  17: 1.75, 35: 1.85, 53: 1.98}
BASE_CPK_COLOR = {
    1:(0.95,0.97,0.99), 5:(0.96,0.68,0.50), 6:(0.52,0.61,0.70),
    7:(0.32,0.62,0.98), 8:(0.96,0.36,0.38), 9:(0.36,0.88,0.58),
    14:(0.82,0.72,0.56), 15:(0.98,0.62,0.26), 16:(0.96,0.82,0.28),
    17:(0.30,0.84,0.52), 35:(0.68,0.28,0.22), 53:(0.58,0.24,0.68),
}
DEFAULT_VDW_RADIUS = 1.60
DEFAULT_COLOR = (0.60,0.68,0.74)
SELECTED_COLOR = (1.00,0.87,0.40)
DEFAULT_BOND_COLOR = (0.62,0.73,0.79)

@dataclass(frozen=True)
class InstanceBuffers:
    atom_positions: np.ndarray
    atom_radii: np.ndarray
    atom_rgb: np.ndarray
    bond_positions: np.ndarray
    bond_directions: np.ndarray
    bond_scales: np.ndarray
    bond_rgb: np.ndarray
    bond_source_indices: np.ndarray

def _rgb(value: object) -> np.ndarray:
    arr = np.asarray(value, dtype=np.float64)
    if arr.shape != (3,) or not np.all(np.isfinite(arr)) or np.any(arr < 0) or np.any(arr > 1):
        raise ValueError("RGB must contain three finite color channels in [0,1]")
    return np.rint(arr * 255.0).astype(np.uint8)

def _scale(value: object) -> float:
    x = float(value)
    if not math.isfinite(x) or not 0.15 <= x <= 6.0:
        raise ValueError("Per-atom/bond scale must be finite and in [0.15,6]")
    return x

def prepare_instances(
    coordinates: np.ndarray,
    atomic_numbers: np.ndarray,
    atom_ids: list,
    bonds: list[tuple[int,int,int]],
    bond_ids: list | None = None,
    atom_scales: Mapping | None = None,
    atom_colors: Mapping | None = None,
    bond_widths: Mapping | None = None,
    bond_colors: Mapping | None = None,
    selected_atoms: set | None = None,
    *,
    mode: str = "ball_stick",
    global_atom_scale: float = 1.0,
    global_bond_scale: float = 1.0,
) -> InstanceBuffers:
    """Build typed geometry arrays without VTK side effects.

    `atom_colors` and `atom_scales` are keyed by *stable AtomId*.
    `bond_colors` and `bond_widths` are keyed by *stable BondId*.
    """
    coords=np.asarray(coordinates, dtype=np.float64)
    nums=np.asarray(atomic_numbers, dtype=np.int32)
    n=len(atom_ids)
    if coords.shape != (n,3) or nums.shape != (n,):
        raise ValueError("RenderSnapshot coordinates/atomic_numbers/AtomIds shapes disagree")
    if not np.all(np.isfinite(coords)):
        raise ValueError("3D coordinates must be finite")
    if np.any(nums < 1) or np.any(nums > 118):
        raise ValueError("unsupported atomic number")
    if bond_ids is not None and len(bond_ids) != len(bonds):
        raise ValueError("bond ID ordering must match bond list")
    if len(set(atom_ids))!=n:
        raise ValueError("duplicate stable AtomId")
    g_atom=_scale(global_atom_scale)
    g_bond=_scale(global_bond_scale)
    atom_scales=atom_scales or {}
    atom_colors=atom_colors or {}
    bond_widths=bond_widths or {}
    bond_colors=bond_colors or {}
    selected_atoms=selected_atoms or set()
    if mode in ("cpk","space_fill"):factor=0.92
    elif mode=="line":factor=0.10
    else:factor=0.25
    radii=np.empty(n,dtype=np.float32)
    colors=np.empty((n,3),dtype=np.uint8)
    for i,aid in enumerate(atom_ids):
        z=int(nums[i])
        radii[i]=BASE_VDW_RADII.get(z,DEFAULT_VDW_RADIUS)*factor*g_atom*_scale(atom_scales.get(aid,1.0))
        actual=atom_colors.get(aid,BASE_CPK_COLOR.get(z,DEFAULT_COLOR))
        if aid in selected_atoms:
            # Selection is a subtle tint of the REAL glyph. The underlying custom
            # RGB remains visible immediately even while the atom is selected.
            actual=0.82*np.asarray(actual,dtype=np.float64)+0.18*np.asarray(SELECTED_COLOR)
        colors[i]=_rgb(actual)

    pos=[];directions=[];sizes=[];bond_rgb=[];source_index=[]
    for bidx,(i,j,order) in enumerate(bonds):
        if not (isinstance(i,(int,np.integer)) and isinstance(j,(int,np.integer))
                and 0<=i<n and 0<=j<n and i!=j):
            raise ValueError(f"bad bond endpoints at bond index {bidx}")
        if int(order) not in (1,2,3,4):
            raise ValueError("invalid bond order")
        p1,p2=coords[int(i)],coords[int(j)]
        vector=p2-p1
        length=float(np.linalg.norm(vector))
        if length<1e-6:
            continue  # Degenerate geometry is not drawable; topology remains untouched.
        direction=vector/length
        normal=np.cross(direction,np.array([0.,0.,1.]))
        if np.linalg.norm(normal)<1e-6:
            normal=np.cross(direction,np.array([0.,1.,0.]))
        normal=normal/float(np.linalg.norm(normal))
        bid=bond_ids[bidx] if bond_ids is not None else bidx
        width=_scale(bond_widths.get(bid,1.0))
        radius=(0.060 if mode=="line" else 0.085)*g_bond*width
        rgb=_rgb(bond_colors.get(bid,DEFAULT_BOND_COLOR))
        lanes={1:(0.,),2:(-0.10,+0.10),3:(-0.16,0.,+0.16),4:(-0.10,+0.10)}[int(order)]
        for k,offset in enumerate(lanes):
            pos.append((p1+p2)*0.5+normal*offset)
            directions.append(direction)
            sizes.append((length,radius*2.,radius*2.))
            bond_rgb.append(rgb)
            source_index.append(bidx)
    m=len(pos)
    def array(values,shape,dtype):
        return np.ascontiguousarray(np.asarray(values,dtype=dtype).reshape(shape))
    return InstanceBuffers(
        atom_positions=array(coords,(n,3),np.float32),
        atom_radii=np.ascontiguousarray(radii),
        atom_rgb=np.ascontiguousarray(colors),
        bond_positions=array(pos,(m,3),np.float32),
        bond_directions=array(directions,(m,3),np.float32),
        bond_scales=array(sizes,(m,3),np.float32),
        bond_rgb=array(bond_rgb,(m,3),np.uint8),
        bond_source_indices=array(source_index,(m,),np.int32),
    )

def _set_array(poly, name:str, values:np.ndarray, *, scalars:bool=False):
    vtka=numpy_support.numpy_to_vtk(np.ascontiguousarray(values),deep=True)
    vtka.SetName(name)
    if scalars:
        poly.GetPointData().SetScalars(vtka)
    else:
        poly.GetPointData().AddArray(vtka)
    return vtka

class GlyphMoleculeScene:
    """Persistent two-actor VTK batching with true per-atom and per-bond style."""

    def __init__(self, renderer):
        if vtk is None:
            raise RuntimeError("vtk is required for GlyphMoleculeScene")
        self.renderer=renderer
        self.atoms=vtk.vtkPolyData()
        self.bonds=vtk.vtkPolyData()
        self.atom_mapper=self._build_atom_mapper()
        self.bond_mapper=self._build_bond_mapper()
        self.atom_actor=vtk.vtkActor()
        self.atom_actor.SetMapper(self.atom_mapper)
        self.bond_actor=vtk.vtkActor()
        self.bond_actor.SetMapper(self.bond_mapper)
        for actor in (self.atom_actor,self.bond_actor):
            actor.SetPickable(False)  # stable ID pick uses backend math and same instance radii.
            prop=actor.GetProperty()
            prop.SetInterpolationToPhong()
            prop.SetAmbient(0.25)
            prop.SetDiffuse(0.76)
            prop.SetSpecular(0.38)
            prop.SetSpecularPower(38.0)
            renderer.AddActor(actor)
        self.buffers=None

    def _build_atom_mapper(self):
        source=vtk.vtkSphereSource()
        source.SetRadius(1.0)
        source.SetThetaResolution(20)
        source.SetPhiResolution(16)
        self.atom_source=source
        mapper=vtk.vtkGlyph3DMapper()
        mapper.SetSourceConnection(source.GetOutputPort())
        mapper.SetInputData(self.atoms)
        mapper.ScalingOn()
        mapper.SetScaleArray("mf_atom_radius")
        mapper.SetScaleModeToScaleByMagnitude()
        mapper.SetScaleFactor(1.0)
        mapper.SetColorModeToDirectScalars()
        mapper.SetScalarModeToUsePointFieldData()
        mapper.SelectColorArray("mf_rgb")
        mapper.ScalarVisibilityOn()
        return mapper

    def _build_bond_mapper(self):
        cylinder=vtk.vtkCylinderSource()
        cylinder.SetRadius(1.0)
        cylinder.SetHeight(1.0)
        cylinder.SetResolution(14)
        cylinder.CappingOn()
        transform=vtk.vtkTransform()
        transform.RotateZ(-90.0)  # cylinder intrinsic +Y becomes +X
        apply=vtk.vtkTransformPolyDataFilter()
        apply.SetTransform(transform)
        apply.SetInputConnection(cylinder.GetOutputPort())
        self.bond_source=cylinder
        self.bond_source_transform=apply
        mapper=vtk.vtkGlyph3DMapper()
        mapper.SetSourceConnection(apply.GetOutputPort())
        mapper.SetInputData(self.bonds)
        mapper.ScalingOn()
        mapper.SetScaleArray("mf_bond_xyz_scale")
        mapper.SetScaleModeToScaleByVectorComponents()
        mapper.SetOrientationArray("mf_bond_axis")
        mapper.SetOrientationModeToDirection()
        mapper.SetColorModeToDirectScalars()
        mapper.SetScalarModeToUsePointFieldData()
        mapper.SelectColorArray("mf_rgb")
        mapper.ScalarVisibilityOn()
        return mapper

    @staticmethod
    def _load_polydata(poly, xyz:np.ndarray, scale:np.ndarray, rgb:np.ndarray,
                       scale_name:str, axis:np.ndarray | None=None):
        pts=vtk.vtkPoints()
        pts.SetData(numpy_support.numpy_to_vtk(np.ascontiguousarray(xyz),deep=True))
        poly.SetPoints(pts)
        poly.GetPointData().Initialize()
        _set_array(poly,scale_name,scale)
        _set_array(poly,"mf_rgb",rgb,scalars=True)
        if axis is not None:
            _set_array(poly,"mf_bond_axis",axis)
        poly.Modified()

    def update(self,buffers:InstanceBuffers):
        self.buffers=buffers
        self._load_polydata(self.atoms,buffers.atom_positions,buffers.atom_radii,
                            buffers.atom_rgb,"mf_atom_radius")
        self._load_polydata(self.bonds,buffers.bond_positions,buffers.bond_scales,
                            buffers.bond_rgb,"mf_bond_xyz_scale",buffers.bond_directions)
        self.atom_mapper.Modified()
        self.bond_mapper.Modified()

    def set_material(self, *,roughness:float=None, metallic:float=None):
        for actor in (self.atom_actor,self.bond_actor):
            prop=actor.GetProperty()
            if roughness is not None:
                value=max(.05,min(.95,float(roughness)))
                prop.SetSpecular(max(.1,1.-value))
                prop.SetSpecularPower(max(10.,(1.-value)*65.))
            if metallic is not None:
                value=max(0.,min(1.,float(metallic)))
                prop.SetAmbient(.22+.28*value)
