"""Undoable local geometry and torsion edits preserving branch internal distances."""
from copy import deepcopy
import numpy as np
from .commands import Command,CommandResult
from .modeling_commands import connected_atoms
from ..domain.coordination import GEOMETRIES,fit_directions


def _rotation(source,target):
    a=source/np.linalg.norm(source);b=target/np.linalg.norm(target)
    cross=np.cross(a,b);s=np.linalg.norm(cross);c=float(a@b)
    if s<1e-10:
        if c>0:return np.eye(3)
        axis=np.cross(a,[1,0,0] if abs(a[0])<.8 else [0,1,0]);axis/=np.linalg.norm(axis)
        return 2*np.outer(axis,axis)-np.eye(3)
    k=np.array([[0,-cross[2],cross[1]],[cross[2],0,-cross[0]],[-cross[1],cross[0],0]])
    return np.eye(3)+k+k@k*((1-c)/(s*s))


class ArrangeGeometryCommand(Command):
    description='设置局部成键/配位几何'
    def __init__(self,center,geometry_key):
        if geometry_key not in GEOMETRIES:raise ValueError('未知几何')
        self.center=center;self.geometry_key=geometry_key;self._before=None

    def do(self,doc):
        if self.center not in doc.topology._atoms or not doc.has_3d:return CommandResult(False,message='需要中心原子及3D坐标')
        neighbors=sorted(doc.topology.neighbors_of(self.center))
        geometry=GEOMETRIES[self.geometry_key]
        if len(neighbors)>geometry.coordination:return CommandResult(False,message='现有邻居多于几何位点；不会自动删键')
        original=doc.coordinates.current.coords.copy();ids,mapping=doc.topology.atom_index_map();center=original[mapping[self.center]]
        directions=[original[mapping[a]]-center for a in neighbors]
        if any(np.linalg.norm(v)<1e-6 for v in directions):return CommandResult(False,message='中心与配体重合，请先修复坐标')
        rotated,assignment=fit_directions(geometry,directions)
        blocked=set(doc.topology._adjacency[self.center]);groups=[];seen=set()
        for neighbor in neighbors:
            group=connected_atoms(doc,neighbor,blocked)
            if self.center in group or seen&group:return CommandResult(False,message='环/桥联配体不能按独立支链整理；请使用环构象或约束优化')
            seen.update(group);groups.append(group)
        output=original.copy()
        for old,new,group in zip(directions,rotated[np.asarray(assignment,dtype=int)],groups):
            rotation=_rotation(old,new)
            rows=[mapping[a] for a in group]
            output[rows]=(original[rows]-center)@rotation.T+center
        if self._before is None:self._before=(original,deepcopy(doc.topology.get_atom(self.center).properties),dict(doc.coords_2d))
        doc.coordinates.update_current_coords(output)
        doc.topology.get_atom(self.center).properties['geometry_template']=self.geometry_key
        return CommandResult(True,changed=True,message=f'{geometry.name}：保持支链内部结构和中心键长；理想初值，非稳定性判定')

    def undo(self,doc):
        if self._before is None:return CommandResult(False,message='无旧构型')
        xyz,properties,xy=self._before;doc.coordinates.update_current_coords(xyz.copy())
        doc.topology.get_atom(self.center).properties=deepcopy(properties);doc.coords_2d=dict(xy)
        return CommandResult(True,changed=True)


class RotateBondFragmentCommand(Command):
    description='绕单键旋转一侧构象'
    def __init__(self,bond_id,side_atom,degrees):
        self.bond_id=bond_id;self.side_atom=side_atom;self.degrees=float(degrees);self._before=None
        if not np.isfinite(self.degrees):raise ValueError('角度无效')

    def do(self,doc):
        if self.bond_id not in doc.topology._bonds or not doc.has_3d:return CommandResult(False,message='需要单键及3D坐标')
        bond=doc.topology.get_bond(self.bond_id)
        if bond.order!=1 or bond.aromatic:return CommandResult(False,message='仅允许普通单键扭转；不把双键/芳香键当自由转子')
        if self.side_atom not in (bond.begin,bond.end):return CommandResult(False,message='转动端不在此键上')
        other=bond.other_end(self.side_atom);group=connected_atoms(doc,self.side_atom,{self.bond_id})
        if other in group:return CommandResult(False,message='环键不能直接切成两侧；未修改结构')
        ids,mapping=doc.topology.atom_index_map();xyz=doc.coordinates.current.coords.copy()
        origin=xyz[mapping[other]];axis=xyz[mapping[self.side_atom]]-origin;norm=np.linalg.norm(axis)
        if norm<1e-6:return CommandResult(False,message='键长为零')
        axis/=norm;angle=np.radians(self.degrees);k=np.array([[0,-axis[2],axis[1]],[axis[2],0,-axis[0]],[-axis[1],axis[0],0]])
        rotation=np.eye(3)+np.sin(angle)*k+(1-np.cos(angle))*(k@k)
        output=xyz.copy();rows=[mapping[a] for a in group if a!=self.side_atom]
        output[rows]=(xyz[rows]-origin)@rotation.T+origin
        if self._before is None:self._before=(xyz,dict(doc.coords_2d))
        doc.coordinates.update_current_coords(output)
        return CommandResult(True,changed=True,message=f'旋转{self.degrees:g}°；能量与稳定构象仍需力场/量化检验')

    def undo(self,doc):
        if self._before is None:return CommandResult(False)
        doc.coordinates.update_current_coords(self._before[0].copy());doc.coords_2d=dict(self._before[1])
        return CommandResult(True,changed=True)
