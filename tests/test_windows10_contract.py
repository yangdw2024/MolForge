"""Platform policy tests, runnable on Linux for logic validation."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("windows10_diagnostics",
                                             ROOT/"scripts/windows10_diagnostics.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Win10SupportTests(unittest.TestCase):
    def test_windows_10_22h2_supported(self):
        self.assertTrue(module.win10_supported("Windows",10,0,19045,64)[0])
    def test_windows_10_1809_supported(self):
        self.assertTrue(module.win10_supported("Windows",10,0,17763,64)[0])
    def test_older_windows_10_rejected(self):
        self.assertFalse(module.win10_supported("Windows",10,0,17134,64)[0])
    def test_windows_11_rejected_even_if_nt_version_10(self):
        self.assertFalse(module.win10_supported("Windows",10,0,22621,64)[0])
    def test_32bit_rejected(self):
        self.assertFalse(module.win10_supported("Windows",10,0,19045,32)[0])
    def test_non_windows_cannot_claim_win10_pass(self):
        self.assertFalse(module.win10_supported("Linux",10,0,19045,64)[0])
    def test_launcher_no_personal_hardcoded_python_path(self):
        text=(ROOT/"run_molforge.bat").read_text(encoding="utf-8")
        self.assertNotIn("Trae_Gromacs",text)
        self.assertNotIn("YDW",text)
        self.assertIn("%~dp0",text)
        self.assertIn("MOLFORGE_PYTHON",text)

if __name__=="__main__":unittest.main()
