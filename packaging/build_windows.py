"""Offline test build, executed only on the corresponding real Windows target.

Requires a reviewed complete wheelhouse and external manifest SHA-256. No
environment is uploaded, no production export is enabled, no EXE is called accepted.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys

from wheel_inventory import verify, lock_text, digest

REPO = Path(__file__).resolve().parents[1]
CORE_TESTS = ["test_conversion_core.py", "test_numbered_payroll.py", "test_organizations.py", "test_employee_xml.py",
              "test_monthly_packet.py", "test_backup_restore.py", "test_qt_workflow.py", "test_packaging_tools.py"]


def command(args, env=None):
    subprocess.run([str(v) for v in args], check=True, cwd=str(REPO), env=env)


def build(args):
    if os.name != "nt":
        raise ValueError("This tool builds Windows EXE only on Windows. No cross-build is claimed.")
    legacy = args.variant == "win7-x86"
    expected_python = (3, 8, 10) if legacy else (3, 12, 10)
    if sys.version_info[:3] != expected_python or struct.calcsize("P") * 8 != (32 if legacy else 64):
        raise ValueError("Use the exact isolated Python and architecture from the acceptance guide.")
    if sys.prefix == sys.base_prefix:
        raise ValueError("Use a separate virtual environment, not global Python.")
    win = sys.getwindowsversion()
    if legacy and (win.major, win.minor, win.service_pack_major) != (6, 1, 1):
        raise ValueError("The Win7 candidate must be built/tested on Win7 SP1.")
    if not legacy and (win.major != 10 or win.build < 22000):
        raise ValueError("Use Windows 11 for this test build.")
    if args.output.exists():
        raise ValueError("Use a new output directory. Existing builds are never removed.")
    manifest = verify(args.wheelhouse, args.wheel_manifest, args.approved_sha256)
    args.output.mkdir(parents=True)
    lock = args.output / "requirements-hashed.lock"
    lock.write_text(lock_text(manifest), encoding="utf-8")
    pip_wheels = [w for w in manifest["wheels"] if w["name"].lower() == "pip" and w["version"] == "25.0.1"]
    if len(pip_wheels) != 1:
        raise ValueError("The reviewed wheelhouse must include the exact pip bootstrap.")
    bootstrap = args.output / "pip-bootstrap.lock"
    bootstrap.write_text(lock_text({"wheels": pip_wheels}), encoding="utf-8")
    command([sys.executable, "-m", "pip", "install", "--force-reinstall", "--no-index", "--find-links", args.wheelhouse, "--require-hashes", "-r", bootstrap])
    command([sys.executable, "-m", "pip", "install", "--force-reinstall", "--no-index", "--find-links", args.wheelhouse, "--require-hashes", "-r", lock])
    req = REPO / "packaging" / ("windows7" if legacy else "windows11") / "requirements-candidate.txt"
    for line in req.read_text(encoding="utf-8").splitlines():
        if "==" in line and not line.startswith("#"):
            name, version = line.strip().split("==")
            if importlib.metadata.version(name) != version:
                raise ValueError("Wheelhouse does not contain the exact top-level candidate versions.")
    command([sys.executable, "-m", "pip", "check"])
    command([sys.executable, "-m", "pytest", "-q"] + (["tests/" + name for name in CORE_TESTS] if legacy else []))
    resources = args.output / "resources"
    command([sys.executable, "-m", "app.core.stage_resources", resources])
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(REPO), text=True).strip()
    subprocess.run(["git", "diff", "--quiet", "HEAD"], cwd=str(REPO), check=True)
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=normal"], cwd=str(REPO)):
        raise ValueError("Use a clean source checkout without untracked inputs.")
    env = dict(os.environ)
    env["SOURCE_DATE_EPOCH"] = subprocess.check_output(["git", "show", "-s", "--format=%ct", "HEAD"], cwd=str(REPO), text=True).strip()
    env["PYTHONHASHSEED"] = "0"
    name = "JMHZ-Win7-x86" if legacy else "JMHZ-Win11-x64"
    opposite = "PySide6" if legacy else "PySide2"
    freeze = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed", "--name", name,
              "--paths", REPO, "--distpath", args.output / "dist", "--workpath", args.output / "work", "--specpath", args.output / "spec",
              "--exclude-module", opposite, "--add-data", str(resources / "schemas/official") + ";schemas/official"]
    if legacy:
        for module in ("app.ui.main_window", "app.ui.definitions_page", "app.models"):
            freeze.extend(["--exclude-module", module])
    command(freeze + [REPO / "app/__main__.py"], env)
    artifact = args.output / "dist" / name
    examples = artifact / "examples"
    examples.mkdir()
    for directory in (REPO / "config/conversion", REPO / "config/payroll"):
        shutil.copytree(directory, examples / directory.name)
    report = {"status": "test_build_not_accepted", "windows": platform.platform(), "python": sys.version,
              "bits": struct.calcsize("P") * 8, "source_commit": revision, "wheel_manifest_sha256": args.approved_sha256,
              "pip_freeze": subprocess.check_output([sys.executable, "-m", "pip", "freeze", "--all"], text=True).splitlines(),
              "target_acceptance": "required_on_clean_machine_without_python", "final_export": "blocked"}
    (artifact / "build-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    sums = [digest(p) + "  " + p.relative_to(artifact).as_posix() for p in sorted(artifact.rglob("*")) if p.is_file()]
    (artifact / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print("Test build created; clean-target acceptance is still required:", artifact)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", required=True, choices=["win7-x86", "win11-x64"])
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--wheel-manifest", type=Path, required=True)
    parser.add_argument("--approved-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    options.output = options.output.resolve()
    options.wheelhouse = options.wheelhouse.resolve()
    options.wheel_manifest = options.wheel_manifest.resolve()
    try:
        build(options)
    except Exception:
        parser.exit(2, "Windows test build failed; inspect command output and the exact acceptance prerequisites. No accepted EXE is claimed.\n")
