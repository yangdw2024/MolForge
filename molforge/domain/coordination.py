"""Ideal construction directions, not predictions of electronic state or stability."""
from dataclasses import dataclass
from itertools import permutations
import math
import numpy as np


@dataclass(frozen=True)
class Geometry:
    key: str
    name: str
    symbol: str
    directions: tuple[tuple[float,float,float], ...]

    @property
    def coordination(self):return len(self.directions)


def _unit(rows):
    a=np.asarray(rows,dtype=float)
    return tuple(map(tuple,a/np.linalg.norm(a,axis=1)[:,None]))


def _polygon(n,z=0.,phase=0.):
    return [(math.cos(phase+i*2*math.pi/n),math.sin(phase+i*2*math.pi/n),z) for i in range(n)]


GEOMETRIES={g.key:g for g in (
    Geometry('single','单一成键方向','1',_unit([(1,0,0)])),
    Geometry('linear','直线形 · 180°','L-2',_unit([(1,0,0),(-1,0,0)])),
    Geometry('bent','折线形 · 104.5°','A-2',_unit([(1,0,0),(math.cos(math.radians(104.5)),math.sin(math.radians(104.5)),0)])),
    Geometry('trigonal_planar','平面三角形 · 120°','TP-3',_unit(_polygon(3))),
    Geometry('trigonal_pyramidal','三角锥 · 约107°','TPY-3',_unit([(math.cos(i*2*math.pi/3),math.sin(i*2*math.pi/3),math.sqrt((math.cos(math.radians(107))+.5)/(1-math.cos(math.radians(107))))) for i in range(3)])),
    Geometry('tetrahedral','四面体 · 109.47°','T-4',_unit([(1,1,1),(1,-1,-1),(-1,1,-1),(-1,-1,1)])),
    Geometry('square_planar','平面四方形 · 90°','SP-4',_unit(_polygon(4))),
    Geometry('seesaw','跷跷板形','SS-4',_unit([(0,0,1),(0,0,-1),(1,0,0),(-.5,math.sqrt(3)/2,0)])),
    Geometry('trigonal_bipyramidal','三角双锥','TBPY-5',_unit(_polygon(3)+[(0,0,1),(0,0,-1)])),
    Geometry('square_pyramidal','四方锥','SPY-5',_unit(_polygon(4)+[(0,0,1)])),
    Geometry('octahedral','八面体','OC-6',_unit([(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)])),
    Geometry('trigonal_prismatic','三棱柱','TPR-6',_unit(_polygon(3,.65)+_polygon(3,-.65))),
    Geometry('pentagonal_bipyramidal','五角双锥','PBPY-7',_unit(_polygon(5)+[(0,0,1),(0,0,-1)])),
    Geometry('square_antiprismatic','四方反棱柱','SAPR-8',_unit(_polygon(4,.6)+_polygon(4,-.6,math.pi/4))),
    Geometry('cubic','立方体','CU-8',_unit([(i,j,k) for i in (-1,1) for j in (-1,1) for k in (-1,1)])),
    Geometry('tricapped_trigonal_prismatic','三帽三棱柱','TPRS-9',_unit(_polygon(3,.65)+_polygon(3,-.65)+_polygon(3,0,math.pi/3))),
    Geometry('pentagonal_antiprismatic','五角反棱柱','PAPR-10',_unit(_polygon(5,.6)+_polygon(5,-.6,math.pi/5))),
)}


def preferred_geometries(element):
    z=element.atomic_number
    if z>=104:return () # Do not invent preferred superheavy coordination chemistry.
    choices={1:('single',),5:('trigonal_planar','tetrahedral'),6:('tetrahedral','trigonal_planar','linear'),
        7:('trigonal_pyramidal','trigonal_planar','tetrahedral','linear'),8:('bent','single'),
        9:('single',),14:('tetrahedral',),15:('trigonal_pyramidal','trigonal_bipyramidal'),
        16:('bent','tetrahedral','octahedral'),17:('single',),34:('bent','tetrahedral','octahedral'),35:('single',),53:('single',)}
    if z in choices:return tuple(GEOMETRIES[k] for k in choices[z])
    if element.block in ('d','f') or element.group in (1,2):
        return tuple(GEOMETRIES[k] for k in ('octahedral','square_planar','tetrahedral','trigonal_bipyramidal','trigonal_prismatic','pentagonal_bipyramidal','square_antiprismatic'))
    return ()


def inferred_geometry(document, anchor):
    atom=document.topology.get_atom(anchor)
    explicit=atom.properties.get('geometry_template')
    if explicit in GEOMETRIES:return GEOMETRIES[explicit]
    orders=[document.topology.get_bond(b).order for b in document.topology._adjacency[anchor]]
    if atom.atomic_num in (6,7):
        if any(o>=3 for o in orders):return GEOMETRIES['linear']
        if atom.aromatic or any(o==2 for o in orders):return GEOMETRIES['trigonal_planar']
        if atom.atomic_num==7 and atom.formal_charge==0:return GEOMETRIES['trigonal_pyramidal']
        return GEOMETRIES['tetrahedral']
    if atom.atomic_num==8:return GEOMETRIES['bent']
    if atom.atomic_num in (1,9,17,35,53):return GEOMETRIES['single']
    if atom.atomic_num==5:return GEOMETRIES['trigonal_planar']
    if atom.atomic_num==14:return GEOMETRIES['tetrahedral']
    return None


def fit_directions(geometry, observed):
    """Orient an ideal polyhedron towards existing bonds, preserving its internal angles."""
    ideal=np.asarray(geometry.directions);observed=np.asarray(observed,dtype=float).reshape(-1,3)
    count=len(observed)
    if count==0:return ideal.copy(),[]
    if count>len(ideal):raise ValueError('现有配位数超过该几何的位点数')
    observed=observed/np.maximum(np.linalg.norm(observed,axis=1)[:,None],1e-12)
    def rotate(source,target):
        u,_,vt=np.linalg.svd(source.T@target)
        correction=np.eye(3);correction[-1,-1]=np.linalg.det(u@vt)
        return u@correction@vt
    best=None
    # Two fixed correspondence trials plus greedy matching avoid factorial work for CN 7–10.
    trials=permutations(range(len(ideal)),count) if count<=4 and len(ideal)<=6 else permutations(range(len(ideal)),min(count,2))
    for trial in trials:
        rotation=rotate(ideal[list(trial)],observed[:len(trial)])
        rotated=ideal@rotation
        assignment=list(trial);available=set(range(len(ideal)))-set(assignment)
        for obs in observed[len(trial):]:
            index=max(sorted(available),key=lambda j:float(rotated[j]@obs));assignment.append(index);available.remove(index)
        rotation=rotate(ideal[assignment],observed);rotated=ideal@rotation
        cost=float(np.sum((rotated[assignment]-observed)**2))
        if best is None or cost<best[0]-1e-10:best=(cost,rotated,assignment)
    return best[1],best[2]


def valence_limit(z, charge=0):
    if z==7:return 4 if charge>0 else 3
    if z==8:return 3 if charge>0 else (1 if charge<0 else 2)
    return {1:1,5:4 if charge<0 else 3,6:4,9:1,14:4,15:5,16:6,17:1,34:6,35:1,53:1}.get(z)


def automatic_bond_error(document, anchor, new_z, order):
    atom=document.topology.get_atom(anchor)
    used=sum(1.5 if document.topology.get_bond(b).aromatic else document.topology.get_bond(b).order for b in document.topology._adjacency[anchor])
    limit=valence_limit(atom.atomic_num,atom.formal_charge)
    if limit is not None and used+order>limit+1e-8:return '自动成键将超过常用价态；请选中离去H替换，或明确修改电荷/键级'
    new_limit=valence_limit(new_z)
    if new_limit is not None and order>new_limit:return '新元素不支持该自动成键键级'
    key=atom.properties.get('geometry_template')
    if key in GEOMETRIES and len(document.topology.neighbors_of(anchor))>=GEOMETRIES[key].coordination:
        return '该配位几何位点已占满；请替换已有配体或选择其他几何'
    return None
