"""Application-owned files and Qt settings stay on the project drive."""
import os
import tempfile
from pathlib import Path

def data_dir() -> Path:
    root = Path(os.environ.get("MOLFORGE_DATA_DIR", str(Path(__file__).resolve().parents[1] / "user_data"))).resolve()
    if os.name == "nt" and root.drive.upper() not in ("D:", "E:"):
        raise ValueError("MOLFORGE_DATA_DIR must be on D: or E:")
    root.mkdir(parents=True, exist_ok=True)
    return root

def configure_runtime() -> Path:
    root = data_dir()
    for name in ("temp", "cache", "settings", "logs", "autosave"):
        (root / name).mkdir(exist_ok=True)
    os.environ["TEMP"] = os.environ["TMP"] = str(root / "temp")
    os.environ["MPLCONFIGDIR"] = str(root / "cache")
    tempfile.tempdir = str(root / "temp")
    try:
        from PyQt6.QtCore import QSettings, QCoreApplication, Qt
        if QCoreApplication.instance() is None:
            QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        for scope in (QSettings.Scope.UserScope, QSettings.Scope.SystemScope):
            QSettings.setPath(QSettings.Format.IniFormat, scope, str(root / "settings"))
    except ImportError:
        pass
    return root
