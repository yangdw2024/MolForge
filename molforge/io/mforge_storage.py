"""
Reliable .mforge project ZIP persistence, compatible with v4's Domain model.

This replaces the original loader's TODOs: BondId, AtomId, 2D layout, frames,
per-atom/per-bond appearance, and document metadata round-trip. Save writes to
a sibling temporary file then atomically replaces the destination.

The ZIP reader NEVER extracts paths and accepts only the two expected JSON
entries. Large trajectory/blobs require future bounded streaming support;
this JSON-based v1.1 deliberately rejects too-large archives.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import zipfile

import numpy as np

from ..domain.document import MoleculeDocument, DocumentStatus
from ..domain.ids import AtomId, BondId

SCHEMA = "1.1"
MAX_DOCUMENT_BYTES = 128 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_ARCHIVE_BYTES = 160 * 1024 * 1024

def _rgb(value):
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError("invalid RGB color in .mforge")
    color = tuple(float(q) for q in value)
    if not all(math.isfinite(q) and 0 <= q <= 1 for q in color):
        raise ValueError("non-finite/out-of-range RGB color")
    return color

def _atom_properties(value):
    if not isinstance(value,dict):
        raise ValueError("invalid atom properties")
    output=dict(value)
    if "frozen" in output and not isinstance(output["frozen"],bool):
        raise ValueError("frozen must be boolean")
    for key in ("opacity","glow"):
        if key in output:
            number=float(output[key])
            if not math.isfinite(number) or not 0<=number<=1:
                raise ValueError("invalid atom "+key)
            output[key]=number
    if "glow_color" in output:
        output["glow_color"]=list(_rgb(output["glow_color"]))
    return output

def _scale(value):
    number = float(value)
    if not math.isfinite(number) or not 0.15 <= number <= 6:
        raise ValueError("invalid appearance scale")
    return number

def _limited_json(zf: zipfile.ZipFile, name: str, maximum: int):
    info=zf.getinfo(name)
    if info.file_size > maximum:
        raise ValueError(f"{name}: exceeds size limit")
    if info.file_size > 100_000 and info.file_size / max(info.compress_size, 1) > 1000:
        raise ValueError(f"{name}: suspicious compression ratio")
    with zf.open(info) as stream:
        data=stream.read(maximum + 1)
    if len(data)>maximum:
        raise ValueError(f"{name}: expanded data too large")
    return json.loads(data.decode("utf-8")), data

def serialize_document_to_dict(doc: MoleculeDocument) -> dict:
    """将 MoleculeDocument 序列化为规范标准字典结构。"""
    atoms = []
    for aid in doc.topology.atom_ids:
        a = doc.topology.get_atom(aid)
        atoms.append({
            "id": aid.value, "atomic_num": a.atomic_num,
            "formal_charge": a.formal_charge, "aromatic": a.aromatic,
            "implicit_h": a.implicit_h, "color": _rgb(a.color),
            "scale": _scale(a.scale), "properties": _atom_properties(a.properties)
        })
    bonds = []
    for bid in doc.topology.bond_ids:
        b = doc.topology.get_bond(bid)
        bonds.append({
            "id": bid.value, "begin": b.begin.value, "end": b.end.value,
            "order": b.order, "aromatic": b.aromatic,
            "color": _rgb(b.color), "width_scale": _scale(b.width_scale),
            "properties": b.properties
        })
    frames = []
    if doc._coordinates is not None:
        for frame in doc._coordinates:
            if frame.coords.shape != (doc.num_atoms, 3) or not np.all(np.isfinite(frame.coords)):
                raise ValueError("coordinate shape or NaN/Inf mismatch")
            frames.append({"coords": frame.coords.tolist(), "energy": frame.energy, "source": frame.source})
    coords2d = []
    for aid, xy in doc.coords_2d.items():
        if aid not in doc.topology._atoms or len(xy) != 2 or not all(math.isfinite(float(q)) for q in xy):
            raise ValueError("invalid 2D layout coordinates")
        coords2d.append([aid.value, float(xy[0]), float(xy[1])])
    return {
        "document_id": doc.document_id, "name": doc.name, "revision": doc.revision,
        "status": doc.status.value, "source_format": doc.source_format,
        "source_path": doc.source_path, "properties": doc.properties,
        "units": doc.units, "topology": {"atoms": atoms, "bonds": bonds},
        "coordinates": {"frames": frames,
                       "current_index": doc._coordinates.current_index if doc._coordinates is not None else -1},
        "coords_2d": coords2d,
        "id_counter": doc.topology._id_counter.state_dict()
    }


def save_mforge(doc: MoleculeDocument, path: str | Path) -> None:
    dest=Path(path)
    # Only structural checks; full RDKit sanitization isn't applicable to
    # all drafts/metals. This must not destroy a user's in-progress sketch.
    old_status = doc.status
    try:
        problems=doc.check_invariants()
    finally:
        # validate()/check_invariants() mutates status in v4; Save must be read-only.
        doc.status = old_status
    if problems:
        raise ValueError("Refusing to save inconsistent document: " + "; ".join(problems))
    record = serialize_document_to_dict(doc)
    document_bytes=json.dumps(record,ensure_ascii=False,allow_nan=False,separators=(",",":")).encode("utf-8")
    if len(document_bytes)>MAX_DOCUMENT_BYTES:
        raise ValueError("project is too large for current JSON-based .mforge; streaming project required")
    manifest={
       "format":"mforge","version":SCHEMA,"document_id":doc.document_id,
       "name":doc.name,"revision":doc.revision,
       "num_atoms":doc.num_atoms,"num_bonds":doc.num_bonds,
       "document_sha256":hashlib.sha256(document_bytes).hexdigest()
    }
    manifest_bytes=json.dumps(manifest,ensure_ascii=False,separators=(",",":")).encode("utf-8")
    dest.parent.mkdir(parents=True,exist_ok=True)
    tmp_name=None
    try:
        with tempfile.NamedTemporaryFile(mode="wb",suffix=".mforge.tmp",
                                          prefix="."+dest.name+".",dir=dest.parent,
                                          delete=False) as f:
            tmp_name=f.name
        with zipfile.ZipFile(tmp_name,"w",compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6) as z:
            z.writestr("manifest.json",manifest_bytes)
            z.writestr("document.json",document_bytes)
        with open(tmp_name,"r+b") as f:
            os.fsync(f.fileno())
        os.replace(tmp_name,dest)
        tmp_name=None
    finally:
        if tmp_name and os.path.exists(tmp_name):
            os.unlink(tmp_name)

def load_mforge(path: str | Path) -> MoleculeDocument:
    src=Path(path)
    if not src.is_file():raise FileNotFoundError(src)
    if src.stat().st_size>MAX_ARCHIVE_BYTES:
        raise ValueError("project archive exceeds safe size limit")
    with zipfile.ZipFile(src,"r") as z:
        names=z.namelist()
        if len(names)!=2 or set(names)!={"manifest.json","document.json"}:
            raise ValueError("invalid .mforge archive structure")
        manifest,_=_limited_json(z,"manifest.json",MAX_MANIFEST_BYTES)
        data,raw=_limited_json(z,"document.json",MAX_DOCUMENT_BYTES)
    if not isinstance(manifest,dict) or manifest.get("format")!="mforge":
        raise ValueError("incorrect .mforge manifest")
    if manifest.get("version") not in ("1.0","1.1"):
        raise ValueError("unsupported .mforge schema")
    if manifest.get("document_sha256") and hashlib.sha256(raw).hexdigest()!=manifest["document_sha256"]:
        raise ValueError("document checksum mismatch")
    if not isinstance(data,dict) or not isinstance(data.get("topology"),dict):
        raise ValueError("missing document topology")
    topo=data["topology"]
    atom_data=topo.get("atoms")
    bond_data=topo.get("bonds")
    if not isinstance(atom_data,list) or not isinstance(bond_data,list):
        raise ValueError("invalid atom/bond list")
    if manifest.get("num_atoms")!=len(atom_data) or manifest.get("num_bonds")!=len(bond_data):
        raise ValueError("manifest atom/bond counts disagree with document")
    doc=MoleculeDocument(name=str(data.get("name",manifest.get("name","untitled"))))
    doc.document_id=str(data.get("document_id",manifest["document_id"]))
    doc.revision=int(data.get("revision",manifest.get("revision",0)))
    doc.source_format=data.get("source_format","mforge")
    doc.source_path=data.get("source_path")
    doc.properties=data.get("properties",{})
    doc.units=data.get("units",doc.units)
    seen_atoms=set()
    for a in atom_data:
        aid=AtomId(int(a["id"]))
        if aid.value<0 or aid in seen_atoms:
            raise ValueError("duplicate/negative AtomId in project")
        seen_atoms.add(aid)
        doc.topology.add_atom(int(a["atomic_num"]),
            formal_charge=int(a.get("formal_charge",0)),
            aromatic=bool(a.get("aromatic",False)),atom_id=aid)
        atom=doc.topology.get_atom(aid)
        atom.implicit_h=int(a.get("implicit_h",0))
        atom.color=_rgb(a.get("color"))
        atom.scale=_scale(a.get("scale",1.0))
        atom.properties=_atom_properties(a.get("properties",{}))
    seen_bonds=set()
    for b in bond_data:
        bid=BondId(int(b["id"]))
        if bid.value<0 or bid in seen_bonds:
            raise ValueError("duplicate/negative BondId")
        seen_bonds.add(bid)
        a=AtomId(int(b["begin"])); c=AtomId(int(b["end"]))
        if doc.topology.bond_between(a,c) is not None:
            raise ValueError("two bonds share same endpoints")
        doc.topology.add_bond(a,c,order=int(b["order"]),
                              aromatic=bool(b.get("aromatic",False)),bond_id=bid)
        bond=doc.topology.get_bond(bid)
        bond.color=_rgb(b.get("color"))
        bond.width_scale=_scale(b.get("width_scale",1.0))
        bond.properties=b.get("properties",{})
    coords=data.get("coordinates",{})
    frames=coords.get("frames",[])
    if not isinstance(frames,list):
        raise ValueError("invalid coordinate frame list")
    if frames:
        store=doc.ensure_coordinates()
        for fr in frames:
            array=np.asarray(fr["coords"],dtype=np.float32)
            if array.shape!=(doc.num_atoms,3) or not np.all(np.isfinite(array)):
                raise ValueError("invalid frame shape/values")
            store.add_frame(array,energy=fr.get("energy"),source=fr.get("source","mforge"))
        current=int(coords.get("current_index",0))
        store.current_index=current
    layout=data.get("coords_2d",[])
    if not isinstance(layout,list):
        raise ValueError("invalid 2D layout list")
    for value in layout:
        aid=AtomId(int(value[0]))
        if aid not in seen_atoms or aid in doc.coords_2d:
            raise ValueError("2D layout AtomId mismatch")
        xy=(float(value[1]),float(value[2]))
        if not all(math.isfinite(x) for x in xy):
            raise ValueError("2D layout contains non-finite numbers")
        doc.coords_2d[aid]=xy
    counters=data.get("id_counter")
    if counters is not None:
        if (int(counters["next_atom"])<=max([x.value for x in seen_atoms],default=-1)
            or int(counters["next_bond"])<=max([x.value for x in seen_bonds],default=-1)):
            raise ValueError("ID counter would reuse prior persistent identifiers")
        doc.topology._id_counter.load_state_dict(
            {"next_atom":int(counters["next_atom"]),
             "next_bond":int(counters["next_bond"])})
    errors=doc.check_invariants()
    if errors:raise ValueError("project failed structural invariants: "+"; ".join(errors))
    doc.status=DocumentStatus(data.get("status",manifest.get("status","draft")))
    if doc.document_id!=manifest["document_id"]:
        raise ValueError("document identity mismatch")
    return doc

