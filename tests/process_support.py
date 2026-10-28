"""Launch the actual interpreter, rather than a Windows venv redirector.

Tests must kill the service process itself, not just a launcher. Preserve the
test environment's package path when launching its underlying interpreter.
"""
import os
from pathlib import Path
import subprocess
import sys
import sysconfig


def spawn_module(module, arguments=(), *, env=None):
    environment = dict(os.environ if env is None else env)
    environment.pop("__PYVENV_LAUNCHER__", None)
    environment.pop("PYTHONHOME", None)
    environment["PYTHONPATH"] = os.pathsep.join([sysconfig.get_path("purelib"), str(Path.cwd())])
    return subprocess.Popen([getattr(sys, "_base_executable", sys.executable), "-B", "-m", module, *arguments],
                            env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
