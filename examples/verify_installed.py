"""Run tests outside the checkout against a separately installed wheel.

Prepare a virtual environment and install .[test] there first. Then run:
python -m examples.verify_installed --python .venv-edge-test/Scripts/python.exe
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, help="Python in the clean environment containing installed sabz-edge")
    parser.add_argument("--output", default="validation/isolated-wheel-tests.txt")
    parser.add_argument("--pattern", default="test*.py")
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()
    if not 1 <= args.repeat <= 20:
        parser.error("repeat must be between 1 and 20")
    repo = Path(__file__).resolve().parents[1]
    python = Path(args.python).resolve()
    source = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (repo / "sabz_edge").glob("*.py")}
    with tempfile.TemporaryDirectory(prefix="sabz-wheel-check-") as directory:
        root = Path(directory)
        shutil.copytree(repo / "tests", root / "tests", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(repo / "examples", root / "examples", ignore=shutil.ignore_patterns("__pycache__"))
        if (repo / "firmware").is_dir():
            shutil.copytree(repo / "firmware", root / "firmware")
        probe_code = ("import sabz_edge,json,hashlib; from pathlib import Path; "
                      "r=Path(sabz_edge.__file__).parent; "
                      "print(json.dumps({'path':str(r),'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in r.glob('*.py')}}))")
        probe = subprocess.run([str(python), "-I", "-c", probe_code], cwd=root, capture_output=True, text=True, check=True)
        installed = json.loads(probe.stdout)
        if Path(installed["path"]).parent.name != "site-packages" or installed["files"] != source:
            raise RuntimeError("installed package differs from source; reinstall the wheel")
        print("Installed package hashes match; running tests outside checkout", flush=True)
        logs = []
        exit_code = 0
        for repetition in range(args.repeat):
            result = subprocess.run([str(python), "-I", "-B", "-m", "unittest", "discover", "-s", str(root / "tests"), "-p", args.pattern, "-v"],
                                    cwd=root, capture_output=True, text=True)
            logs.append(f"Run {repetition + 1}/{args.repeat}\n" + result.stdout + result.stderr)
            if result.returncode:
                exit_code = result.returncode
                break
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("Installed wheel verified against source SHA-256 hashes. Tests run outside checkout with Python -I.\n\n"
                          + "\n".join(logs), encoding="utf-8")
        print("\n".join(logs))
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
