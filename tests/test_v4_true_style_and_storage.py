"""Genuine v4 RDKit/Domain + VTK 9.x batched-glyph tests.

No Qt substitute: native Qt interactions must still be verified on Windows 10.
Run from source root: python -m unittest discover -s tests -p test_v4_true_style_and_storage.py -v
"""
from __future__ import annotations
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
import zipfile

import numpy as np
try:
    import vtk
except ImportError:
    vtk = None

from molforge.application.builtin_commands import (
    SetAtomStyleCommand, SetBondStyleCommand, SetAtomChargeCommand,
)
from molforge.application.command_bus import CommandBus
from molforge.domain.document import MoleculeDocument
from molforge.domain.ids import AtomId,BondId
from molforge.io.mforge_storage import save_mforge,load_mforge
from molforge.rendering.glyph_scene import prepare_instances,GlyphMoleculeScene
from molforge.rendering.contracts import RenderSnapshot,RepresentationMode
from molforge.rendering.vtk_backend import VtkRendererBackend


def make_doc():
    doc=MoleculeDocument(name="CO-N")
    a=doc.topology.add_atom(6)
    b=doc.topology.add_atom(8)
    c=doc.topology.add_atom(7)
    x=doc.topology.add_bond(a,b,order=1)
    y=doc.topology.add_bond(b,c,order=2)
    doc.ensure_coordinates().add_frame(np.array(
       [[0,0,0],[1.5,0,0],[2.5,1,0]],dtype=np.float32),
       source="test_coordinates")
    doc.coords_2d[a]=(10.,20.)
    doc.coords_2d[b]=(11.,20.)
    doc.coords_2d[c]=(12.,21.)
    return doc,(a,b,c),(x,y)


class GeometryArrays(unittest.TestCase):
    def setUp(self):
        self.doc,self.a,self.b=make_doc()
        self.xyz=np.array([[0,0,0],[1.5,0,0],[2.5,1,0]],dtype=np.float32)
        self.z=np.array([6,8,7],dtype=np.int32)

    def buffers(self,**kwargs):
        return prepare_instances(self.xyz,self.z,list(self.a),
            [(0,1,1),(1,2,2)],list(self.b),**kwargs)

    def test_per_atom_radius_changes_one_instance(self):
        base=self.buffers()
        target=self.buffers(atom_scales={self.a[1]:2.0})
        self.assertAlmostEqual(float(target.atom_radii[1]),float(base.atom_radii[1]*2),places=5)
        self.assertEqual(float(target.atom_radii[0]),float(base.atom_radii[0]))
        self.assertEqual(float(target.atom_radii[2]),float(base.atom_radii[2]))

    def test_per_atom_custom_rgb_is_real(self):
        base=self.buffers()
        target=self.buffers(atom_colors={self.a[1]:(1.0,0.0,0.0)})
        self.assertEqual(tuple(map(int,target.atom_rgb[1])),(255,0,0))
        self.assertTrue(np.array_equal(base.atom_rgb[0],target.atom_rgb[0]))
        self.assertTrue(np.array_equal(base.atom_rgb[2],target.atom_rgb[2]))

    def test_selection_does_not_mask_custom_color(self):
        red=self.buffers(atom_colors={self.a[1]:(1,0,0)},selected_atoms={self.a[1]})
        blue=self.buffers(atom_colors={self.a[1]:(0,0,1)},selected_atoms={self.a[1]})
        self.assertFalse(np.array_equal(red.atom_rgb[1],blue.atom_rgb[1]))
        self.assertTrue(np.array_equal(red.atom_rgb[0],blue.atom_rgb[0]))

    def test_single_bond_width_modifies_only_its_instances(self):
        base=self.buffers()
        target=self.buffers(bond_widths={self.b[1]:2.0})
        first=target.bond_source_indices==0
        second=target.bond_source_indices==1
        self.assertTrue(np.allclose(base.bond_scales[first],target.bond_scales[first]))
        self.assertTrue(np.allclose(target.bond_scales[second,1:],
                                    base.bond_scales[second,1:]*2))

    def test_single_bond_color_not_global(self):
        base=self.buffers()
        target=self.buffers(bond_colors={self.b[1]:(0,1,0)})
        self.assertTrue(np.array_equal(base.bond_rgb[0],target.bond_rgb[0]))
        self.assertEqual(tuple(map(int,target.bond_rgb[1])),(0,255,0))
        self.assertEqual(tuple(map(int,target.bond_rgb[2])),(0,255,0))

    def test_global_multiplicative_scale(self):
        base=self.buffers(atom_scales={self.a[1]:1.5},bond_widths={self.b[1]:2.0})
        global2=self.buffers(atom_scales={self.a[1]:1.5},bond_widths={self.b[1]:2.0},
                              global_atom_scale=2.0,global_bond_scale=2.0)
        self.assertTrue(np.allclose(global2.atom_radii,base.atom_radii*2))
        self.assertTrue(np.allclose(global2.bond_scales[:,1:],base.bond_scales[:,1:]*2))

    def test_degenerate_bond_does_not_draw_invalid_cylinder(self):
        xyz=self.xyz.copy();xyz[1]=xyz[0]
        out=prepare_instances(xyz,self.z,list(self.a),[(0,1,1)],list(self.b[:1]))
        self.assertEqual(len(out.bond_positions),0)
        self.assertTrue(np.isfinite(out.atom_positions).all())

    def test_order_and_aromatic_lane_counts(self):
        for order,expected in [(1,1),(2,2),(3,3),(4,2)]:
            with self.subTest(order=order):
                out=prepare_instances(self.xyz,self.z,list(self.a),[(0,1,order)],
                                      [self.b[0]])
                self.assertEqual(len(out.bond_positions),expected)
                self.assertEqual(len(out.bond_scales),expected)

    def test_zero_atoms_and_zero_bonds(self):
        out=prepare_instances(np.empty((0,3)),np.empty((0,),int),[],[])
        self.assertEqual(out.atom_positions.shape,(0,3))
        self.assertEqual(out.atom_rgb.shape,(0,3))
        self.assertEqual(out.bond_scales.shape,(0,3))

    def test_invalid_inputs_fail_early(self):
        cases=[
          dict(coordinates=np.array([[np.nan,0,0],[0,0,0],[1,1,1]])),
          dict(atomic_numbers=np.array([0,8,7])),
          dict(atom_ids=[self.a[0],self.a[0],self.a[2]]),
          dict(bond_ids=[self.b[0]]),
          dict(atom_scales={self.a[1]:float("nan")}),
          dict(atom_colors={self.a[1]:(-1,0,1)}),
          dict(bond_widths={self.b[1]:float("inf")}),
          dict(bond_colors={self.b[1]:(0,1,100)}),
        ]
        for override in cases:
            with self.subTest(override=override):
                kw={"coordinates":self.xyz,"atomic_numbers":self.z,
                    "atom_ids":list(self.a),"bonds":[(0,1,1),(1,2,2)],
                    "bond_ids":list(self.b)}
                kw.update(override)
                with self.assertRaises(ValueError):prepare_instances(**kw)

    @unittest.skipIf(vtk is None, "VTK C++ runtime not installed in sandbox")
    def test_vtk_two_persistent_glyph_actors_and_arrays(self):
        ren=vtk.vtkRenderer()
        scene=GlyphMoleculeScene(ren)
        count=ren.GetActors().GetNumberOfItems()
        self.assertEqual(count,2)
        b=self.buffers(bond_widths={self.b[1]:2},atom_scales={self.a[1]:2})
        scene.update(b)
        self.assertEqual(scene.atoms.GetNumberOfPoints(),3)
        self.assertEqual(scene.bonds.GetNumberOfPoints(),3)
        self.assertAlmostEqual(scene.atoms.GetPointData().GetArray("mf_atom_radius").GetTuple1(1),
                               float(b.atom_radii[1]),places=5)
        self.assertEqual(scene.bond_mapper.GetScaleMode(),2)
        self.assertEqual(scene.bond_mapper.GetOrientationMode(),0)
        scene.update(self.buffers())
        self.assertEqual(ren.GetActors().GetNumberOfItems(),count)

    @unittest.skipIf(vtk is None, "VTK C++ runtime not installed in sandbox")
    def test_real_backend_batched_glyphs_and_optional_glow(self):
        class Viewer:
            def __init__(self):self.renderer=vtk.vtkRenderer()
            def set_background(self,**kwargs):pass
            def enable_anti_aliasing(self,*args):pass
            def reset_camera(self):self.renderer.ResetCamera()
            def render(self):pass
            @property
            def camera(self):return self.renderer.GetActiveCamera()
        v=Viewer();be=VtkRendererBackend();be.attach(v)
        # GUI-dependent deferred drawing deliberately disabled in headless test.
        be.render=lambda:None
        snap=RenderSnapshot(
           atom_ids=list(self.a),atomic_numbers=self.z,bonds=[(0,1,1),(1,2,2)],
           bond_ids=list(self.b),coordinates=self.xyz,
           atom_scales={self.a[1]:2.0},bond_widths={self.b[1]:2.0},
           atom_colors={self.a[1]:(1,0,0)},bond_colors={self.b[1]:(0,1,0)},
           selected_atoms={self.a[1]})
        be.set_snapshot(snap)
        self.assertIsNotNone(be._atom_glyph_mapper)
        self.assertTrue(be._atom_actor.GetVisibility())
        from molforge.domain.elements import get_element
        expected=get_element(int(self.z[1])).vdw_radius * .25 * 2.
        self.assertAlmostEqual(float(be._atom_radii.GetValue(1)),expected,places=3)
        self.assertTrue(all(not layer[3].GetVisibility() for layer in be._glow_layers))
        be.set_mode(RepresentationMode.CPK)
        self.assertFalse(be._bond_actor.GetVisibility())
        be.set_mode(RepresentationMode.BALL_AND_STICK)
        self.assertTrue(be._bond_actor.GetVisibility())
        before=v.renderer.GetActors().GetNumberOfItems()
        be.set_snapshot(snap,reset_cam=False)
        self.assertEqual(v.renderer.GetActors().GetNumberOfItems(),before)


class RealDocumentStyleUndo(unittest.TestCase):
    def setUp(self):
        self.doc,self.a,self.b=make_doc()
        self.bus=CommandBus(self.doc)

    def test_atom_style_undo_redo_and_2d_coordinates_unchanged(self):
        old=dict(self.doc.coords_2d)
        r=self.bus.execute(SetAtomStyleCommand(self.a[1],scale=2,color=(1,0,0)))
        self.assertTrue(r.success)
        self.assertEqual(self.doc.topology.get_atom(self.a[1]).scale,2)
        self.assertEqual(self.doc.topology.get_atom(self.a[1]).color,(1.,0.,0.))
        self.assertEqual(self.doc.coords_2d,old)
        self.bus.undo()
        self.assertEqual(self.doc.topology.get_atom(self.a[1]).scale,1)
        self.assertIsNone(self.doc.topology.get_atom(self.a[1]).color)
        self.assertEqual(self.doc.coords_2d,old)
        self.bus.redo()
        self.assertEqual(self.doc.topology.get_atom(self.a[1]).scale,2)
        self.assertEqual(self.doc.coords_2d,old)

    def test_bond_style_undo_redo(self):
        self.bus.execute(SetBondStyleCommand(self.b[1],width_scale=1.8,color=(0,1,0)))
        self.assertEqual(self.doc.topology.get_bond(self.b[0]).width_scale,1.)
        self.assertEqual(self.doc.topology.get_bond(self.b[1]).width_scale,1.8)
        self.assertEqual(self.doc.topology.get_bond(self.b[1]).color,(0.,1.,0.))
        self.bus.undo()
        self.assertIsNone(self.doc.topology.get_bond(self.b[1]).color)
        self.bus.redo()
        self.assertEqual(self.doc.topology.get_bond(self.b[1]).width_scale,1.8)

    def test_formal_charge_command_replaces_ui_direct_assignment(self):
        self.bus.execute(SetAtomChargeCommand(self.a[1],-1))
        self.assertEqual(self.doc.topology.get_atom(self.a[1]).formal_charge,-1)
        self.bus.undo()
        self.assertEqual(self.doc.topology.get_atom(self.a[1]).formal_charge,0)

    def test_invalid_style_does_not_modify_doc(self):
        initial=self.doc.revision
        for bad in [float("nan"),float("inf"),-1,99]:
            with self.assertRaises(ValueError):SetAtomStyleCommand(self.a[0],scale=bad)
        for bad in [(-1,0,0),(1,2,3)]:
            with self.assertRaises(ValueError):SetBondStyleCommand(self.b[0],color=bad)
        self.assertEqual(self.doc.revision,initial)


class ProjectPersistence(unittest.TestCase):
    def setUp(self):
        self.doc,self.a,self.b=make_doc()
        self.bus=CommandBus(self.doc)
        self.bus.execute(SetAtomStyleCommand(self.a[1],scale=2.3,color=(.2,.3,.9)))
        self.bus.execute(SetBondStyleCommand(self.b[1],width_scale=1.7,color=(.8,.5,.1)))

    def test_real_atom_bond_style_and_2d_3d_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"test.mforge"
            save_mforge(self.doc,p)
            other=load_mforge(p)
            self.assertEqual(list(other.topology.atom_ids),list(self.doc.topology.atom_ids))
            self.assertEqual(list(other.topology.bond_ids),list(self.doc.topology.bond_ids))
            self.assertEqual(other.topology.get_atom(self.a[1]).color,(.2,.3,.9))
            self.assertEqual(other.topology.get_atom(self.a[1]).scale,2.3)
            self.assertEqual(other.topology.get_bond(self.b[1]).width_scale,1.7)
            self.assertEqual(other.topology.get_bond(self.b[1]).color,(.8,.5,.1))
            self.assertEqual(other.coords_2d,self.doc.coords_2d)
            np.testing.assert_array_equal(other.coordinates.current.coords,self.doc.coordinates.current.coords)
            self.assertEqual(other.document_id,self.doc.document_id)
            self.assertEqual(other.revision,self.doc.revision)
            self.assertEqual(other.num_atoms,3)
            self.assertEqual(other.num_bonds,2)

    def test_id_counter_after_load_does_not_reuse_deleted_ids(self):
        self.doc.topology.remove_bond(self.b[0])
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"test.mforge"
            save_mforge(self.doc,p)
            recovered=load_mforge(p)
            new_bond=recovered.topology.add_bond(self.a[0],self.a[1])
            self.assertNotIn(new_bond,self.b)

    def test_failed_save_keeps_original_file(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"test.mforge"
            save_mforge(self.doc,p);old=p.read_bytes()
            self.doc.properties["cannot_serialize"]=object()
            with self.assertRaises(TypeError):save_mforge(self.doc,p)
            self.assertEqual(old,p.read_bytes())

    def test_checksum_tampered_file_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"good.mforge";bad=Path(td)/"bad.mforge"
            save_mforge(self.doc,p)
            with zipfile.ZipFile(p) as z:
                m=json.loads(z.read("manifest.json"))
                d=json.loads(z.read("document.json"))
            d["name"]="tampered"
            with zipfile.ZipFile(bad,"w") as z:
                z.writestr("manifest.json",json.dumps(m))
                z.writestr("document.json",json.dumps(d))
            with self.assertRaisesRegex(ValueError,"checksum"):load_mforge(bad)

    def test_zip_traversal_not_extracted(self):
        with tempfile.TemporaryDirectory() as td:
            bad=Path(td)/"bad.mforge"
            with zipfile.ZipFile(bad,"w") as z:
                z.writestr("../evil.txt","not executed")
                z.writestr("manifest.json",'{"format":"mforge","version":"1.1"}')
                z.writestr("document.json","{}")
            with self.assertRaises(ValueError):load_mforge(bad)
            self.assertFalse((Path(td)/"evil.txt").exists())

    def test_legacy_v1_0_simple_valid_file_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"new.mforge";legacy=Path(td)/"legacy.mforge"
            save_mforge(self.doc,p)
            with zipfile.ZipFile(p) as z:
                manifest=json.loads(z.read("manifest.json"))
                document=z.read("document.json")
            manifest["version"]="1.0"
            manifest.pop("document_sha256",None)
            with zipfile.ZipFile(legacy,"w") as z:
                z.writestr("manifest.json",json.dumps(manifest))
                z.writestr("document.json",document)
            doc=load_mforge(legacy)
            self.assertEqual(doc.num_bonds,2)

    def test_load_invalid_atom_id_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"test.mforge";bad=Path(td)/"bad.mforge"
            save_mforge(self.doc,p)
            with zipfile.ZipFile(p) as z:
                manifest=json.loads(z.read("manifest.json"))
                content=json.loads(z.read("document.json"))
            content["topology"]["atoms"][1]["id"]=content["topology"]["atoms"][0]["id"]
            newdata=json.dumps(content,separators=(",",":")).encode()
            import hashlib
            manifest["document_sha256"]=hashlib.sha256(newdata).hexdigest()
            with zipfile.ZipFile(bad,"w") as z:
                z.writestr("manifest.json",json.dumps(manifest))
                z.writestr("document.json",newdata)
            with self.assertRaises(ValueError):load_mforge(bad)



class V6InteractiveAndScienceSuite(unittest.TestCase):
    def setUp(self):
        self.doc, self.a, self.b = make_doc()
        self.bus = CommandBus(self.doc)

    def test_p0_1_multi_atom_batch_drag_single_undo_redo(self):
        from molforge.application.builtin_commands import MoveAtomsBatch3DCommand
        orig_coords = self.doc.coordinates.current.coords.copy()
        delta = np.array([1.5, -2.0, 0.5], dtype=np.float32)
        moves = {
            self.a[0]: (orig_coords[0], orig_coords[0] + delta),
            self.a[1]: (orig_coords[1], orig_coords[1] + delta),
        }
        r = self.bus.execute(MoveAtomsBatch3DCommand(moves))
        self.assertTrue(r.success)
        cur = self.doc.coordinates.current.coords
        np.testing.assert_allclose(cur[0], orig_coords[0] + delta, atol=1e-5)
        np.testing.assert_allclose(cur[1], orig_coords[1] + delta, atol=1e-5)
        np.testing.assert_allclose(cur[2], orig_coords[2], atol=1e-5)  # Unselected atom untouched!
        # Single Ctrl+Z restores ALL moved atoms at once!
        self.bus.undo()
        np.testing.assert_allclose(self.doc.coordinates.current.coords, orig_coords, atol=1e-5)
        # Single Ctrl+Y redoes ALL moved atoms at once!
        self.bus.redo()
        np.testing.assert_allclose(self.doc.coordinates.current.coords[0], orig_coords[0] + delta, atol=1e-5)
        np.testing.assert_allclose(self.doc.coordinates.current.coords[1], orig_coords[1] + delta, atol=1e-5)

    def test_p0_2_vtk_backend_multi_coord_update_and_lod(self):
        be = VtkRendererBackend()
        snap = RenderSnapshot(
            atom_ids=list(self.a),
            atomic_numbers=np.array([6, 8, 7], dtype=np.int32),
            bonds=[(0, 1, 1), (1, 2, 2)],
            bond_ids=list(self.b),
            coordinates=self.doc.coordinates.current.coords.copy(),
        )
        be.set_snapshot(snap)
        be.begin_interactive_lod()
        self.assertTrue(be._in_interactive_lod)
        be.update_multi_atoms_coords({
            self.a[0]: np.array([10.0, 0.0, 0.0]),
            self.a[1]: np.array([11.5, 0.0, 0.0]),
        })
        np.testing.assert_allclose(be._coordinates[0], [10.0, 0.0, 0.0], atol=1e-5)
        np.testing.assert_allclose(be._coordinates[1], [11.5, 0.0, 0.0], atol=1e-5)
        be.end_interactive_lod()
        self.assertFalse(be._in_interactive_lod)

    def test_p0_3_modify_bond_length_command_and_undo(self):
        from molforge.application.builtin_commands import ModifyBondLength3DCommand
        orig = self.doc.coordinates.current.coords.copy()
        r = self.bus.execute(ModifyBondLength3DCommand(self.b[0], 1.95))
        self.assertTrue(r.success)
        c = self.doc.coordinates.current.coords
        new_len = float(np.linalg.norm(c[1] - c[0]))
        self.assertAlmostEqual(new_len, 1.95, places=4)
        self.bus.undo()
        np.testing.assert_allclose(self.doc.coordinates.current.coords, orig, atol=1e-5)

    def test_p1_1_append_molecule_paste_and_undo(self):
        from molforge.application.builtin_commands import AppendMoleculeCommand
        other, _, _ = make_doc()
        r = self.bus.execute(AppendMoleculeCommand(other))
        self.assertTrue(r.success)
        self.assertEqual(self.doc.num_atoms, 6)
        self.assertEqual(self.doc.num_bonds, 4)
        self.bus.undo()
        self.assertEqual(self.doc.num_atoms, 3)
        self.assertEqual(self.doc.num_bonds, 2)

    def test_p3_1_xtb_or_forcefield_optimization(self):
        from molforge.io.calculators import run_xtb_optimization
        res = run_xtb_optimization(self.doc)
        self.assertTrue(res["success"])
        self.assertEqual(res["coords"].shape, (3, 3))
        self.assertTrue(np.all(np.isfinite(res["coords"])))

    def test_p3_3_frontier_orbital_homo_lumo_cube_generation(self):
        from molforge.io.cube_reader import generate_frontier_orbital_cube
        for kind in ("HOMO", "LUMO"):
            cube = generate_frontier_orbital_cube(self.doc, orbital_type=kind, grid_res=24)
            self.assertEqual(cube.dims, (24, 24, 24))
            self.assertGreater(float(cube.values.max()), 0.05)
            self.assertLess(float(cube.values.min()), -0.05)

    def test_p2_and_p4_preset_ic_smiles_and_bio_loaders(self):
        from molforge.io.rdkit_adapter import SAMPLE_MOLECULES, load_molecule_document
        self.assertEqual(SAMPLE_MOLECULES["IC 端基 (1,3-茚满酮型)"], "O=C1CC(=C(C#N)C#N)c2ccccc12")
        self.assertEqual(SAMPLE_MOLECULES["IC 端基 (受体)"], "O=C1CC(=C(C#N)C#N)c2ccccc12")
        for bio_file in ("samples/bio/1CRN.pdb", "samples/bio/1CRN.cif", "samples/bio/4HHB.pdb"):
            if Path(bio_file).exists():
                d, _ = load_molecule_document(bio_file)
                self.assertGreater(d.num_atoms, 300)



class V72BugfixesAndV73WorkflowsSuite(unittest.TestCase):
    def test_v7_2_p0_bug4_delete_atom_with_hydrogens_and_undo(self):
        from molforge.io.rdkit_adapter import create_instant_caffeine_document
        from molforge.application.builtin_commands import DeleteAtomCommand
        from molforge.application.command_bus import CommandBus

        doc = create_instant_caffeine_document()
        self.assertEqual(doc.num_atoms, 24)
        heavy_ids = [
            aid for aid in doc.topology.all_atom_ids()
            if doc.topology.get_atom(aid).element != 1
        ]
        self.assertEqual(len(heavy_ids), 14)
        methyl_c = None
        for aid in heavy_ids:
            h_neighbors = [
                nb for nb in doc.topology.adjacent_atoms(aid)
                if doc.topology.get_atom(nb).element == 1
            ]
            if len(h_neighbors) == 3:
                methyl_c = aid
                break
        self.assertIsNotNone(methyl_c)
        bus = CommandBus(doc)
        res = bus.execute(DeleteAtomCommand(atom_id=methyl_c))
        self.assertTrue(res.success, getattr(res, "message", ""))
        self.assertEqual(doc.num_atoms, 20)
        bus.undo()
        self.assertEqual(doc.num_atoms, 24)

    def test_v7_2_p0_bug1_to_4_editor2d_fit_view_marquee_implicit_h_and_delete(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        src = (root / "molforge" / "ui" / "editor2d_widget.py").read_text(encoding="utf-8")
        self.assertIn("🗑️ 删除选中", src)
        self.assertIn("attached_h", src)
        self.assertIn("self._pan_x = -center_x * self.BASE_PX_PER_ANGSTROM * self._zoom", src)

    def test_v7_2_p1_bug5_to_8_export_autosave_axes_and_atom_numbers(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        tabs_src = (root / "molforge" / "ui" / "shells" / "document_tabs.py").read_text(encoding="utf-8")
        self.assertIn("install_export_menu", tabs_src)
        self.assertIn("export_xyz_file", tabs_src)
        self.assertIn("export_mol_sdf_file", tabs_src)
        self.assertIn("export_image_file", tabs_src)
        self.assertIn("_run_autosave", tabs_src)
        self.assertIn("_confirm_save_if_modified", tabs_src)

        r3d_src = (root / "molforge" / "ui" / "render3d_widget.py").read_text(encoding="utf-8")
        self.assertIn("🧭 坐标轴", r3d_src)
        self.assertIn("🔢 原子编号", r3d_src)

        vtk_src = (root / "molforge" / "rendering" / "vtk_backend.py").read_text(encoding="utf-8")
        self.assertIn("self.show_axes: bool = True", vtk_src)

    def test_v7_3_all_8_workflows_and_catalog_docs(self):
        import json
        import tempfile
        from pathlib import Path
        from molforge.io.rdkit_adapter import create_instant_caffeine_document
        from molforge.application.calculators.qc_input_generator import extract_xyz_lines
        from molforge.workflows import (
            esp_surface,
            homo_lumo_plot,
            osc_energy_diagram,
            reorganization_energy,
            dipole_analysis,
            planarity_analysis,
            md_rdf_analysis,
            igmh_interaction,
        )

        root = Path(__file__).resolve().parents[1]
        self.assertTrue((root / "docs" / "WORKFLOWS_CATALOG.md").exists())
        self.assertTrue((root / "docs" / "CHANGES_v7_3.md").exists())
        self.assertGreater(len((root / "docs" / "WORKFLOWS_CATALOG.md").read_text(encoding="utf-8")), 2000)

        doc = create_instant_caffeine_document()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            xyz_lines = extract_xyz_lines(doc)
            xyz_file = tmp / "caffeine.xyz"
            xyz_file.write_text(f"{len(xyz_lines)}\nCaffeine\n" + "\n".join(xyz_lines) + "\n", encoding="utf-8")

            # 1. Reorganization Energy 4-point gjf bundle + log calculation
            gjf_dir = reorganization_energy.generate_four_point_gjf_bundle(doc, tmp, carrier_type="electron")
            self.assertEqual(len(list(gjf_dir.glob("*.gjf"))), 4)

            logs = []
            energies = [-100.1000, -99.8950, -100.0950, -99.8900]
            for idx_e, e_val in enumerate(energies, 1):
                lp = tmp / f"pt{idx_e}.log"
                lp.write_text(f" SCF Done:  E(RB3LYP) =  {e_val:.8f}     A.U. after   12 cycles\n", encoding="utf-8")
                logs.append(lp)
            reorg_dir = reorganization_energy.run_reorganization_energy_workflow(logs, tmp, v_da_ev=0.025)
            reorg_data = json.loads((reorg_dir / "reorganization_energy.json").read_text(encoding="utf-8"))
            self.assertAlmostEqual(reorg_data["lambda_total_ev"], 0.010 * 27.211386, places=3)
            self.assertGreater(reorg_data["marcus_kinetics"]["marcus_rate_s_inv"], 1e9)

            # 2. SVD Planarity + PQR export
            plan_dir = planarity_analysis.run_planarity_workflow(xyz_file, tmp)
            self.assertTrue((plan_dir / "atom_plane_deviations.pqr").exists())
            self.assertTrue((plan_dir / "planarity.json").exists())

            # 3. MD RDF g(r) calculation + SVG export
            rdf_dir = md_rdf_analysis.run_md_rdf_workflow([xyz_file], tmp, r_max=8.0, n_bins=40)
            self.assertTrue((rdf_dir / "rdf_plot.svg").exists())
            self.assertTrue((rdf_dir / "rdf_curve.csv").exists())

            # 4. IGMH Gaussian input + Multiwfn script generation
            igmh_dir = igmh_interaction.run_igmh_workflow(xyz_file, tmp, frag1_range="1-12", frag2_range="13-24")
            self.assertTrue((igmh_dir / "caffeine-igmh.gjf").exists())
            self.assertTrue((igmh_dir / "igmh_multiwfn_stdin.txt").exists())
            self.assertTrue((igmh_dir / "render_igmh_vmd.tcl").exists())

            # 5. Verify callable entrypoints on esp_surface, homo_lumo_plot, osc_energy_diagram, dipole_analysis
            self.assertTrue(callable(esp_surface.run_esp_surface_workflow))
            self.assertTrue(callable(homo_lumo_plot.run_homo_lumo_workflow))
            self.assertTrue(callable(osc_energy_diagram.run_osc_energy_workflow))
            self.assertTrue(callable(dipole_analysis.run_dipole_workflow))


if __name__=="__main__":
    unittest.main()



class V7ResultsAndArchitectureSuite(unittest.TestCase):
    """MolForge v7.0 全功能 Results 平台 (79 模块 / 9 分类)、Stale 失效、引擎注册表与多系统测试。"""

    def test_v7_analysis_registry_79_modules_and_9_categories(self):
        from molforge.application.invalidation import AnalysisRegistry
        all_defs = AnalysisRegistry.all_definitions()
        self.assertEqual(len(all_defs), 79)
        by_cat = AnalysisRegistry.by_category()
        self.assertEqual(len(by_cat), 9)
        for expected_cat in ("基础结果", "波函数", "分子性质", "分子间作用", "光谱", "分子动力学", "OSC 专题", "药物化学", "分析工作流"):
            self.assertIn(expected_cat, by_cat)
            self.assertGreater(len(by_cat[expected_cat]), 0)

    def test_v7_descriptors_planarity_and_esp_quantitative_execution(self):
        from molforge.io.rdkit_adapter import create_instant_caffeine_document
        from molforge.application.invalidation import CapabilityResolver, AnalysisResultRepository
        doc = create_instant_caffeine_document()

        # 1. PROP-06 分子描述符与成药性
        res_prop = CapabilityResolver.execute_analysis("PROP-06", doc)
        self.assertAlmostEqual(res_prop.metrics["molecular_weight_da"], 194.19, delta=0.5)
        self.assertGreater(res_prop.metrics["tpsa_a2"], 40.0)
        self.assertIn("lipinski_ro5_violations", res_prop.metrics)

        # 2. PROP-01 分子平面性 SVD RMSD
        res_plan = CapabilityResolver.execute_analysis("PROP-01", doc)
        self.assertIn("planarity_rmsd_angstrom", res_plan.metrics)
        self.assertGreaterEqual(res_plan.metrics["planarity_rmsd_angstrom"], 0.0)
        self.assertGreater(len(res_plan.table_rows), 5)

        # Missing wavefunction is not a quantum ESP calculation.
        res_esp = CapabilityResolver.execute_analysis("WFN-01", doc)
        self.assertNotEqual(res_esp.status,"Ready")
        self.assertEqual(res_esp.metrics,{})
        self.assertTrue(res_esp.warnings)

        # 4. Stale 失效感知：当分子发生几何/拓扑变动后，已缓存的 AnalysisResult 自动标记为 Stale
        repo = AnalysisResultRepository.instance()
        self.assertFalse(repo.is_result_stale(res_esp.result_id, doc))
        doc.bump_revision()
        self.assertTrue(repo.is_result_stale(res_esp.result_id, doc))

    def test_v7_osc_frontier_noncovalent_spectra_and_md_pipeline(self):
        from molforge.io.rdkit_adapter import create_instant_caffeine_document
        from molforge.application.invalidation import CapabilityResolver
        from molforge.io.calculators import MultiwfnAdapter, GromacsAdapter, EngineToolRegistry
        doc = create_instant_caffeine_document()

        for key in ("OSC-01","OSC-04","INTER-04","SPEC-03","MD-03"):
            result=CapabilityResolver.execute_analysis(key,doc)
            self.assertNotEqual(result.status,"Ready")
            self.assertEqual(result.metrics,{})
            self.assertEqual(result.plot_y,())
            self.assertTrue(result.warnings)

        # Multiwfn ESP stdout parser verification
        sample_out = """
        Minimal value:   -38.45 kcal/mol   Maximal value:    42.10 kcal/mol
        Overall surface area:         215.60 Angstrom^2
        Positive surface area:        112.30 Angstrom^2
        Negative surface area:        103.30 Angstrom^2
        Overall variance (sigma^2_tot):  245.80 (kcal/mol)^2
        Positive variance:               110.20 (kcal/mol)^2
        Negative variance:               135.60 (kcal/mol)^2
        Balance of charges (nu):         0.2473
        Internal charge separation (Pi): 11.42 kcal/mol
        Molecular polarity index (MPI):  12.85 kcal/mol
        """
        parsed = MultiwfnAdapter.parse_esp_summary_text(sample_out)
        self.assertAlmostEqual(parsed["v_min_kcal"], -38.45)
        self.assertAlmostEqual(parsed["v_max_kcal"], 42.10)
        self.assertAlmostEqual(parsed["nu_balance"], 0.2473)
        self.assertAlmostEqual(parsed["mpi_index"], 12.85)

        tools = EngineToolRegistry.detect_all()
        for tid in ("gaussian", "xtb", "multiwfn", "gromacs", "vmd", "openbabel"):
            self.assertIn(tid, tools)


    def test_v7_1_caffeine_vs_benzene_distinct_mo_uv_ir_and_exact_tpsa_61_82(self):
        from molforge.io.rdkit_adapter import create_instant_caffeine_document, create_molecule_from_smiles
        from molforge.application.invalidation import CapabilityResolver
        from molforge.io.calculators import MultiwfnAdapter

        caffeine = create_instant_caffeine_document()
        benzene = create_molecule_from_smiles("c1ccccc1", name="benzene")

        # 1. Caffeine TPSA must equal RDKit/Ertl exact 61.82 Å² (never 85.70 Å²)
        res_caff_prop = CapabilityResolver.execute_analysis("PROP-06", caffeine)
        self.assertAlmostEqual(res_caff_prop.metrics["tpsa_a2"], 61.82, places=2)

        # Different structural inputs cannot substitute for missing quantum/trajectory data.
        for structure in (caffeine,benzene):
            for key in ("WFN-02","SPEC-03","SPEC-01","DRUG-03"):
                result=CapabilityResolver.execute_analysis(key,structure)
                self.assertNotEqual(result.status,"Ready")
                self.assertEqual(result.metrics,{})
                self.assertEqual(result.plot_y,())

        # 4. Non-existent .fchk path on WFN-01 must return Missing Data and empty metrics
        esp_missing = CapabilityResolver.execute_analysis("WFN-01", caffeine, external_file="/nonexistent/missing_file.fchk")
        self.assertEqual(esp_missing.status, "Missing Data")
        self.assertEqual(esp_missing.metrics, {})

        # 5. MultiwfnAdapter stdin script must use real newline characters (not literal backslash-n)
        stdin_script = MultiwfnAdapter.build_stdin_script("WFN-01")
        self.assertIn("\n", stdin_script)
        self.assertNotIn("\\n", stdin_script)

    def test_v7_1_standalone_studio_windows_do_not_wrap_molforge_window_and_fix_3_bugs(self):
        from pathlib import Path
        from molforge.ui.shells.studio_2d import Studio2DWindow, _compute_electron_count
        from molforge.ui.shells.studio_3d import Studio3DWindow
        from molforge.ui.shells.studio_split import StudioSplitWindow
        from molforge.io.rdkit_adapter import create_instant_caffeine_document

        # Verify Studio2DWindow / Studio3DWindow / StudioSplitWindow do not import or wrap MolForgeWindow
        for rel in ("molforge/ui/shells/studio_2d.py", "molforge/ui/shells/studio_3d.py", "molforge/ui/shells/studio_split.py"):
            src = Path(rel).read_text(encoding="utf-8")
            self.assertNotIn("from ..window import MolForgeWindow", src)
            self.assertNotIn("MolForgeWindow(", src)

        # Verify electron count calculation on Caffeine (C8H10N4O2: 24 atoms, 102 electrons, charge 0, spin 1)
        caff = create_instant_caffeine_document()
        n_atoms, n_elec, charge, spin = _compute_electron_count(caff)
        self.assertEqual((n_atoms, n_elec, charge, spin), (24, 102, 0, 1))

        # Verify the 3 fixed wiring paths in window.py and render3d_widget.py
        win_src = Path("molforge/ui/window.py").read_text(encoding="utf-8")
        self.assertIn("from .dialogs.gaussian_calculation_setup import GaussianCalculationSetupDialog", win_src)
        self.assertNotIn("gaussian_setup_dialog", win_src)
        self.assertIn("from .dialogs.element_fragments import ElementFragmentsDialog", win_src)
        self.assertNotIn("element_fragments_dialog", win_src)
        self.assertIn("InsertFragmentCommand", win_src)
        self.assertIn("self.workspace.view3d_real.set_multiview_layout(pane_count)", win_src)

        # Verify default startup mode in main.py and scripts/launch.py is "welcome"
        main_src = Path("main.py").read_text(encoding="utf-8")
        self.assertIn('default_mode: str = "welcome"', main_src)
