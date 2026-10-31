"""Offline target-native Windows test build. No cross-build/acceptance is claimed."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import tempfile

from wheel_inventory import verify, lock_text, digest
from windows_policy import requirements, check_wheels, check_installed, audit_binaries

REPO = Path(__file__).resolve().parents[1]
CORE_TESTS = ["test_conversion_core.py", "test_numbered_payroll.py", "test_organizations.py", "test_employee_xml.py",
              "test_monthly_packet.py", "test_backup_restore.py", "test_qt_workflow.py", "test_packaging_tools.py",
              "test_preview_acceptance.py"]


def command(args, env=None, cwd=None, timeout=None):
    subprocess.run([str(v) for v in args], check=True, cwd=str(cwd or REPO), env=env, timeout=timeout)


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
        raise ValueError("Build/test the Win7 candidate on Win7 SP1.")
    if not legacy and (win.major != 10 or win.build < 22000):
        raise ValueError("Use Windows 11 for this test build.")
    # Reject dirty/source-tree output before installing anything or creating output.
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(REPO), text=True).strip()
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=normal"], cwd=str(REPO)):
        raise ValueError("Use a clean source checkout without untracked inputs.")
    try:
        args.output.relative_to(REPO)
    except ValueError:
        pass
    else:
        raise ValueError("Use an output directory outside the source checkout.")
    if args.output.exists():
        raise ValueError("Use a new output directory. Existing builds are never removed.")
    folder = "windows7" if legacy else "windows11"
    required = requirements(REPO / "packaging" / folder / "requirements-candidate.txt")
    manifest = verify(args.wheelhouse, args.wheel_manifest, args.approved_sha256)
    check_wheels(manifest, required, legacy)
    check_installed(required, before=True)
    args.output.mkdir(parents=True)
    lock = args.output / "requirements-hashed.lock"
    lock.write_text(lock_text(manifest), encoding="utf-8")
    pip_wheels = [w for w in manifest["wheels"] if w["name"].lower() == "pip"]
    bootstrap = args.output / "pip-bootstrap.lock"
    bootstrap.write_text(lock_text({"wheels": pip_wheels}), encoding="utf-8")
    env = dict(os.environ)
    env["PIP_CONFIG_FILE"] = os.devnull
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["QT_QPA_PLATFORM"] = "offscreen"
    for dependencies in (bootstrap, lock):
        command([sys.executable, "-m", "pip", "install", "--force-reinstall", "--no-deps", "--no-index", "--find-links", args.wheelhouse,
                 "--require-hashes", "-r", dependencies], env)
    check_installed(required)
    command([sys.executable, "-m", "pip", "check"], env)
    command([sys.executable, "-m", "pytest", "-q"] + (["tests/" + name for name in CORE_TESTS] if legacy else []), env)
    resources = args.output / "resources"
    command([sys.executable, "-m", "app.core.stage_resources", resources], env)
    command([sys.executable, "-c", "from app.platforms.preview import stage_preview; import sys; stage_preview(sys.argv[1])", resources / "config/preview"], env)
    env["JMHZ_STAGE_DIR"] = str(resources)
    env["SOURCE_DATE_EPOCH"] = subprocess.check_output(["git", "show", "-s", "--format=%ct", "HEAD"], cwd=str(REPO), text=True).strip()
    env["PYTHONHASHSEED"] = "0"
    name = "JMHZ-Converter-Win7-x86" if legacy else "JMHZ-Converter-Win11-x64"
    spec = REPO / "packaging" / folder / (name + ".spec")
    command([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", args.output / "dist",
             "--workpath", args.output / "work", spec], env)
    artifact = args.output / "dist" / name
    executable = artifact / (name + ".exe")
    if not executable.is_file():
        raise ValueError("The target-named EXE was not produced.")
    binary_audit = audit_binaries(artifact, legacy)
    if not any(p.name.lower() == "qwindows.dll" for p in artifact.rglob("*.dll")):
        raise ValueError("The real Windows platform plugin is missing.")
    # Test the copied EXE away from source, from an unrelated cwd. No source PYTHONPATH.
    with tempfile.TemporaryDirectory(prefix="jmhz-frozen-acceptance-") as temporary:
        target = Path(temporary) / "TEST žluťoučká cesta" / name
        target.parent.mkdir()
        shutil.copytree(artifact, target)
        run_env = dict(env)
        run_env.pop("PYTHONPATH", None)
        run_env.pop("PYTHONHOME", None)
        frozen_report = Path(temporary) / "frozen-test.json"
        command([target / executable.name, "--self-test", "--report", frozen_report], run_env, Path(temporary), timeout=300)
        smoke = json.loads(frozen_report.read_text(encoding="utf-8"))
        if smoke.get("status") != "passed" or smoke.get("frozen") is not True or smoke.get("qt_binding") != ("PySide2" if legacy else "PySide6"):
            raise ValueError("Copied EXE synthetic acceptance failed.")
    # Only these explicit non-runtime files go next to EXE. No source DB or docs archive.
    shutil.copytree(resources / "config/preview", artifact / "synthetic-data")
    shutil.copyfile(REPO / "docs/first-run-windows.md", artifact / "CTETE-NEJDRIVE.md")
    shutil.copyfile(REPO / "docs/windows-acceptance.md", artifact / "windows-acceptance.md")
    (artifact / "Spustit-ukazku.cmd").write_bytes((
        '@echo off\r\nsetlocal\r\nset "JMHZ_DEMO_DIR=%LOCALAPPDATA%\\JMHZ-Converter-Preview\\%RANDOM%-%RANDOM%"\r\n'
        'start "" /wait "%~dp0' + executable.name + '" --demo --demo-directory "%JMHZ_DEMO_DIR%"\r\n'
        'if errorlevel 1 echo Testovaci ukazku se nepodarilo spustit.\r\n').encode("ascii"))
    report = {"status": "test_build_not_accepted", "windows": platform.platform(), "python": sys.version,
              "bits": struct.calcsize("P") * 8, "source_commit": revision, "wheel_manifest_sha256": args.approved_sha256,
              "versions": required, "static_pe_checks": binary_audit, "copied_exe_self_test": smoke,
              "target_acceptance": "required_on_clean_machine_without_python", "final_export": "blocked"}
    (artifact / "build-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    sums = [digest(p) + "  " + p.relative_to(artifact).as_posix() for p in sorted(artifact.rglob("*")) if p.is_file()]
    inventory = artifact / "SHA256SUMS.txt"
    inventory.write_text("\n".join(sums) + "\n", encoding="utf-8")
    from verify_distribution import verify as verify_dist
    verify_dist(artifact, digest(inventory))
    archive = Path(shutil.make_archive(str(args.output / name), "zip", root_dir=artifact.parent, base_dir=name))
    print("Test distribution created; clean-target acceptance is still required:", archive)
    print("ZIP SHA-256:", digest(archive))
    print("Independent inventory SHA-256:", digest(inventory))


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
