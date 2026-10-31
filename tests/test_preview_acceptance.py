"""Synthetic acceptance is also bundled into both EXEs; no real payroll data."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from app.core.resources import default_official_root, default_preview_root
from app.core.stage_resources import stage_schemas
from app.platforms.preview import seed_workspace, load_suite, exercise_gui

ROOT = Path(__file__).parents[1]


def test_synthetic_gui_overview_history_counts_xml_and_zero_review(tmp_path):
    workspace, entries = seed_workspace(tmp_path / "data")
    assert len(entries) == 5
    first, org, imported, draft = entries[0]
    rows = workspace.analyze(org.id, imported.id).payroll.rows
    assert [r.metadata["internal_number"] for r in rows] == ["0002", "0010", "0020"]
    assert [r.primary_pp for r in rows[:2]] == [True, False]
    assert rows[2].metadata["income_amount"] == "0"
    overview = workspace.overview(imported.period)
    assert [v["pp_count"] for v in overview] == [3, 2]
    assert overview[0]["error_count"] > 0  # Zero-income methodology stays open.
    assert overview[0]["last_revision"] is None and overview[1]["last_revision"] == 0
    assert len(workspace.draft_history(org.id, imported.id)) == 1
    exercise_gui(workspace, entries)
    with pytest.raises(FileExistsError):
        seed_workspace(tmp_path / "data")  # Does not overwrite a demo or real workspace.


def test_source_and_frozen_resource_layouts_ignore_working_directory(tmp_path, monkeypatch):
    source_official, source_preview = default_official_root(), default_preview_root()
    monkeypatch.chdir(tmp_path)
    assert default_official_root() == source_official
    staged = tmp_path / "runtime"
    stage_schemas(source_official, staged / "schemas/official")
    shutil.copytree(source_preview, staged / "config/preview")
    monkeypatch.setattr(sys, "_MEIPASS", str(staged), raising=False)
    assert default_official_root() == staged / "schemas/official"
    workspace, entries = seed_workspace(tmp_path / "frozen-data")
    assert len(entries) == 5 and len(workspace.organizations()) == 2
    (staged / "config/preview/a-2026-09-pp.csv").write_bytes(b"changed")
    with pytest.raises(ValueError):
        load_suite()


def test_command_line_self_test_from_foreign_cwd_and_no_report_overwrite(tmp_path):
    env = dict(os.environ, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM="offscreen")
    report = tmp_path / "report.json"
    args = [sys.executable, "-m", "app", "--self-test", "--report", str(report)]
    result = subprocess.run(args, cwd=str(tmp_path), env=env, capture_output=True, timeout=90)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["status"] == "passed" and data["frozen"] is False
    assert "final_export_blocked" in data["checks"]
    assert data["qt_binding"] in {"PySide2", "PySide6"}
    original = report.read_bytes()
    assert subprocess.run(args, cwd=str(tmp_path), env=env, capture_output=True, timeout=30).returncode == 2
    assert report.read_bytes() == original
    assert not (tmp_path / "workspace").exists()  # AppData/default DB is not used.


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "packaging" / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_platform_sets_reject_extra_qt_and_wrong_architecture():
    policy = module("windows_policy")
    for folder, legacy in (("windows7", True), ("windows11", False)):
        required = policy.requirements(ROOT / "packaging" / folder / "requirements-candidate.txt")
        manifest = json.loads((ROOT / "packaging" / folder / "wheels-candidate.json").read_text())
        policy.check_wheels(manifest, required, legacy)
        changed = json.loads(json.dumps(manifest))
        changed["wheels"].append({"name": "PySide6" if legacy else "PySide2", "version": "0", "filename": "unapproved-any.whl"})
        with pytest.raises(ValueError):
            policy.check_wheels(changed, required, legacy)
        changed = json.loads(json.dumps(manifest))
        next(w for w in changed["wheels"] if w["name"].lower() == "lxml")["filename"] = "lxml-linux_x86_64.whl"
        with pytest.raises(ValueError):
            policy.check_wheels(changed, required, legacy)


def test_distribution_inventory_detects_missing_altered_extra_and_unsafe_files(tmp_path):
    spec = importlib.util.spec_from_file_location("wheel_inventory", ROOT / "packaging/wheel_inventory.py")
    wheels = importlib.util.module_from_spec(spec); spec.loader.exec_module(wheels)
    sys.modules["wheel_inventory"] = wheels
    verifier = module("verify_distribution")
    payload = tmp_path / "payload.txt"; payload.write_bytes(b"synthetic")
    manifest = tmp_path / "SHA256SUMS.txt"
    manifest.write_text(wheels.digest(payload) + "  payload.txt\n", encoding="utf-8")
    pin = wheels.digest(manifest)
    verifier.verify(tmp_path, pin)
    extra = tmp_path / "unexpected.db"; extra.write_bytes(b"not allowed")
    with pytest.raises(ValueError):
        verifier.verify(tmp_path, pin)
    extra.unlink();payload.write_bytes(b"changed")
    with pytest.raises(ValueError):
        verifier.verify(tmp_path, pin)
    manifest.write_text('0' * 64 + '  ../escape\n', encoding="utf-8")
    with pytest.raises(ValueError):
        verifier.verify(tmp_path, wheels.digest(manifest))


@pytest.mark.parametrize("folder,legacy", [("windows7", True), ("windows11", False)])
def test_tracked_specs_collect_only_explicit_data_and_exclude_other_qt(tmp_path, monkeypatch, folder, legacy):
    staged = tmp_path / "resources"
    (staged / "schemas/official").mkdir(parents=True)
    (staged / "schemas/official/manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("JMHZ_STAGE_DIR", str(staged))
    captured = {}
    native = ["PySide2/Qt5Core.dll", "PySide2/Qt5Bluetooth.dll", "vccorlib140.dll", "d3dcompiler_47.dll", "libEGL.dll",
              "PySide2/plugins/platforms/qwindows.dll", "PySide2/plugins/platforms/qdirect2d.dll"]
    def analysis(*args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(pure=[], scripts=[], binaries=[(n, "reviewed-source", "BINARY") for n in native], datas=kwargs["datas"])
    namespace = {"SPECPATH": str(ROOT / "packaging" / folder), "Analysis": analysis,
                 "PYZ": lambda *a, **kw: None, "EXE": lambda *a, **kw: kw,
                 "COLLECT": lambda *a, **kw: captured.update(collected=a[1])}
    spec = next((ROOT / "packaging" / folder).glob("*.spec"))
    exec(compile(spec.read_text(encoding="utf-8"), str(spec), "exec"), namespace)
    assert ("PySide6" if legacy else "PySide2") in captured["excludes"]
    assert {target for source, target in captured["datas"]} == {"schemas/official", "config/preview"}
    assert all(str(staged) in source for source, target in captured["datas"])
    if legacy:
        assert {entry[0] for entry in captured["collected"]} == {"PySide2/Qt5Core.dll", "PySide2/plugins/platforms/qwindows.dll"}
