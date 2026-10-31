import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("jmhz_wheel_inventory", ROOT / "packaging/wheel_inventory.py")
wheels = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wheels)


def test_reviewed_wheelhouse_hashes_lock_and_unsafe_metadata(tmp_path):
    directory = tmp_path / "wheels"
    directory.mkdir()
    wheel = directory / "synthetic-1-py3-none-any.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("synthetic-1.dist-info/METADATA", "Metadata-Version: 2.1\nName: synthetic\nVersion: 1\n")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(wheels.inventory(directory)), encoding="utf-8")
    pin = wheels.digest(manifest)
    checked = wheels.verify(directory, manifest, pin)
    assert "synthetic==1 --hash=sha256:" in wheels.lock_text(checked)
    with pytest.raises(ValueError):
        wheels.verify(directory, manifest, "0" * 64)
    with ZipFile(wheel, "w") as archive:
        archive.writestr("synthetic-1.dist-info/METADATA", "Name: unsafe --option\nVersion: 1\n")
    with pytest.raises(ValueError):
        wheels.inventory(directory)


@pytest.mark.skipif(os.name == "nt", reason="This negative test verifies refusal of a Linux cross-build.")
def test_linux_builder_refuses_to_claim_a_windows_exe(tmp_path):
    output = tmp_path / "output"
    completed = subprocess.run([sys.executable, str(ROOT / "packaging/build_windows.py"), "--variant", "win7-x86",
        "--wheelhouse", str(tmp_path), "--wheel-manifest", str(tmp_path / "missing.json"), "--approved-sha256", "0" * 64,
        "--output", str(output)], capture_output=True, text=True)
    assert completed.returncode == 2
    assert "No accepted EXE is claimed" in completed.stderr
    assert not output.exists()
