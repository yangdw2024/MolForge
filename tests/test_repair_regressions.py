"""Regression counterexamples for the 2026-11-03 repair (no external network/GPU)."""
from pathlib import Path
import json,os,tempfile,unittest,subprocess
from molforge.runtime import configure_runtime
configure_runtime()
from molforge.domain.document import MoleculeDocument
from molforge.application.command_bus import CommandBus
from molforge.application.builtin_commands import AddAtomCommand,DeleteAtomCommand
from molforge.ai.mcp_bridge import MolForgeMCPBridge
from molforge.io.mforge_storage import save_mforge,load_mforge
from molforge.workflows.scientific_workflows import read_fchk_geometry,BOHR_TO_ANGSTROM
class RepairTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def test_empty_project_roundtrip_windows_flush(self):
        doc=MoleculeDocument('empty');bus=CommandBus(doc);bus.execute(AddAtomCommand(6,0,0,0));bus.undo()
        save_mforge(doc,self.root/'empty.mforge');restored=load_mforge(self.root/'empty.mforge')
        self.assertEqual(restored.num_atoms,0);self.assertEqual(restored.document_id,doc.document_id)
    def test_fchk_bohr_conversion(self):
        f=self.root/'sample.fchk';f.write_text('Atomic numbers                         I   N= 1\n6\nCurrent cartesian coordinates          R   N= 3\n1.0 2.0 3.0\n',encoding='ascii')
        import numpy as np
        z,xyz=read_fchk_geometry(f)
        np.testing.assert_allclose(xyz,[[BOHR_TO_ANGSTROM,2*BOHR_TO_ANGSTROM,3*BOHR_TO_ANGSTROM]])
    def test_bridge_bad_arguments_are_errors(self):
        d=MoleculeDocument('test');b=MolForgeMCPBridge(d,CommandBus(d))
        for args in ({},{'near_atom':0,'atomic_num':6},{'near_atom':1,'atomic_num':999},[],{'x':1}):
            self.assertFalse(b.dispatch('add_atom',args).get('ok',True))
    def test_bridge_indices_match_stable_viewport_labels(self):
        d=MoleculeDocument('test');bus=CommandBus(d)
        for i in range(3):bus.execute(AddAtomCommand(6,i,0,0))
        ids=list(d.topology.atom_ids);bus.execute(DeleteAtomCommand(ids[0]));b=MolForgeMCPBridge(d,bus)
        rows=b.dispatch('list_atoms',{})['atoms']
        self.assertEqual([r['index'] for r in rows],[x.value+1 for x in d.topology.atom_ids])
        self.assertIsNone(b._aid_at_1based(ids[0].value+1))
        self.assertEqual(b._aid_at_1based(ids[1].value+1),ids[1])
    def test_bulk_delete_one_undo_restores_entire_molecule(self):
        import numpy as np
        from molforge.io.rdkit_adapter import create_instant_caffeine_document
        from molforge.application.selection_commands import DeleteSelectionCommand
        d=create_instant_caffeine_document();bus=CommandBus(d)
        ids=list(d.topology.atom_ids);bond_ids=list(d.topology.bond_ids)
        coords=d.coordinates.current.coords.copy()
        result=bus.execute(DeleteSelectionCommand(ids,bond_ids))
        self.assertTrue(result.success);self.assertEqual(d.num_atoms,0)
        self.assertTrue(bus.undo().success)
        self.assertEqual(list(d.topology.atom_ids),ids)
        self.assertEqual(set(d.topology.bond_ids),set(bond_ids))
        np.testing.assert_allclose(d.coordinates.current.coords,coords)
        self.assertTrue(bus.redo().success);self.assertEqual(d.num_atoms,0)

    @unittest.skipUnless(os.name=='nt','Windows wrapper')
    def test_gromacs_nonzero_exit_and_recursive_include(self):
        from molforge.workflows.gromacs_submit import build_gromacs_job
        g=self.root/'engine.cmd';g.write_text('@exit /b 7\n')
        (self.root/'input.gro').write_text('test\n0\n1 1 1\n')
        (self.root/'topol.top').write_text('#include "molecule.itp"\n')
        (self.root/'molecule.itp').write_text('; test\n')
        job=build_gromacs_job(self.root/'job',self.root/'input.gro',self.root/'topol.top',gmx_path=str(g))
        self.assertTrue((self.root/'job'/'molecule.itp').is_file())
        p=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',job['wrapper']],capture_output=True)
        self.assertEqual(p.returncode,7);self.assertNotIn(b'finished',p.stdout)
if __name__=='__main__':unittest.main()
