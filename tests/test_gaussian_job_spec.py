"""
tests/test_gaussian_job_spec.py - P1 GaussianJobSpec 校验、空结构拦截、奇偶性检查与 CalChem 引擎测试
"""
from __future__ import annotations

import unittest

from molforge.application.calculators.gaussian_job_spec import GaussianJobSpec
from molforge.application.calculators.registry import _all_engines
from molforge.domain.document import MoleculeDocument
from molforge.io.rdkit_adapter import create_sample_molecule


class TestGaussianJobSpecAndEngines(unittest.TestCase):
    def test_empty_document_rejected_on_submission(self):
        empty_doc = MoleculeDocument("empty")
        spec = GaussianJobSpec.default_spec(empty_doc)
        errs = spec.validate(empty_doc, for_submission=True)
        self.assertGreater(len(errs), 0)
        self.assertIn("为空", errs[0])

    def test_valid_caffeine_gjf_generation_and_spin_parity_check(self):
        doc = create_sample_molecule("咖啡因")
        spec = GaussianJobSpec.default_spec(doc)
        spec.job_type = "Opt+Freq"
        spec.theory_family = "DFT"
        spec.functional_or_method = "B3LYP"
        spec.basis_set = "def2SVP"
        spec.solvation_model = "SMD"
        spec.solvent = "Chloroform"

        errs = spec.validate(doc, for_submission=True)
        self.assertEqual(errs, [])

        gjf = spec.generate_gjf(doc)
        self.assertIn("%mem=12GB", gjf)
        self.assertIn("%nprocshared=8", gjf)
        self.assertIn("#p B3LYP/def2SVP Opt Freq EmpiricalDispersion=GD3BJ", gjf)
        self.assertIn("SCRF=(SMD,Solvent=Chloroform)", gjf)

        # 咖啡因是闭壳层偶数电子分子，若强行设置 multiplicity=2 (charge=0)，必须报错拦截
        spec.multiplicity = 2
        parity_errs = spec.validate(doc, for_submission=True)
        self.assertGreater(len(parity_errs), 0)
        self.assertIn("奇偶性冲突", parity_errs[0])

    def test_calchem_engine_is_registered(self):
        names = [e.name for e in _all_engines()]
        self.assertIn("CalChem", names)
