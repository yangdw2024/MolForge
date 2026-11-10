"""
MolForge v7.0 正式启动脚本
==========================
与 main.run_application 共享统一启动链，支持全局崩溃日志与 `--welcome` / `--mode 2d|3d|split` 参数。
双击 run_molforge.bat 即调用此脚本。
"""
import sys, os, faulthandler, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from molforge.runtime import configure_runtime
_crash = configure_runtime() / "logs" / "crash.log"
try:
    _fp = open(_crash, "a", encoding="utf-8", buffering=1)
    faulthandler.enable(file=_fp, all_threads=True)
except Exception:
    _fp = None


def _excepthook(t, e, tb):
    msg = "".join(traceback.format_exception(t, e, tb))
    if _fp:
        _fp.write("\n===== UI EXCEPTION =====\n" + msg)
    sys.stderr.write(msg)


sys.excepthook = _excepthook

from main import run_application


def main():
    sys.exit(run_application(sys.argv, default_mode="welcome"))


if __name__ == "__main__":
    main()
