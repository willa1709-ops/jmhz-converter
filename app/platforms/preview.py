"""Bundled synthetic acceptance, never reads the user's default workspace."""
import hashlib
import json
from pathlib import Path
import platform
import shutil
import sys
import tempfile
from decimal import Decimal

from app.core.resources import default_preview_root, default_official_root
from app.core.payroll import strict_json
from app.core.packages import safe_relative, build_package, install_package
from app.core.organizations import OrganizationWorkspace
from app.core.periods import Period
from app.core.input import read_csv


def require(condition):
    if not condition:
        raise ValueError("Synthetic acceptance assertion failed.")


def load_suite():
    root = default_preview_root()
    manifest = strict_json((root / "manifest.json").read_text(encoding="utf-8"))
    require(manifest["format_version"] == 1 and manifest["data_classification"] == "synthetic_only_not_for_submission")
    require({p.name for p in root.iterdir()} == set(manifest["files"]) | {"manifest.json"})
    for name, expected in manifest["files"].items():
        path = root / safe_relative(name)
        require(path.parent == root and path.suffix in {".csv", ".json"} and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == expected)
    return root, manifest


def stage_preview(destination):
    """Copy only the exact hash-checked synthetic file inventory into the build."""
    root, manifest = load_suite()
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for name in list(manifest["files"]) + ["manifest.json"]:
        shutil.copyfile(root / name, destination / name)


def read_json(root, path):
    return strict_json((root / safe_relative(path)).read_text(encoding="utf-8"))


def seed_workspace(directory):
    """Explicit --demo only: new directory, immutable synthetic imports/history."""
    root, suite = load_suite()
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    workspace = OrganizationWorkspace(directory)
    organizations = {o["key"]: workspace.register(o["name"], o["ico"], o["variable_symbol"]) for o in suite["organizations"]}
    entries = []
    for case in suite["cases"]:
        profiles = suite["profiles"][str(case["year"])]
        profile = read_json(root, profiles["numbered"])
        workspace.set_profile(profile)
        org = organizations[case["organization"]]
        imported = workspace.import_file(org.id, Period.parse(case["period"]), root / case["csv"], "cp1250", ";")
        analysis = workspace.analyze(org.id, imported.id)
        require(all(i.code == "zero_income_methodology_review" for i in analysis.issues) and len(analysis.payroll.rows) == case["pp_count"])
        require(Decimal(analysis.totals["row_total"]["known_sum"]) == Decimal(case["row_total"]))
        if not analysis.issues:
            workspace.record_version(org.id, imported.id, analysis.index, 0)
        monthly = read_json(root, profiles["monthly"])
        eid = workspace.import_employer_table(org.id, imported.id, read_csv(root / case["employer_csv"], "cp1250", ";"), monthly)
        draft_id, result = workspace.prepare_monthly_draft(org.id, imported.id, eid, read_json(root, profiles["employee"]), read_json(root, case["parameters"]), default_official_root())
        require(result.xsd_valid and draft_id and not result.submission_ready)
        entries.append((case, org, imported, draft_id))
    # Profiles remain shared for future imports; historic imports retain snapshots.
    workspace.set_profile(read_json(root, suite["profiles"]["2026"]["numbered"]))
    return workspace, entries


def exercise_gui(workspace, entries):
    from app.ui.qt_compat import QtCore, QtWidgets, QT_API, dispose_window
    from app.platforms.qt_startup import configure_qt
    from app.ui.organizations_window import OrganizationsWindow
    configure_qt(QtCore, QtWidgets, QT_API)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setApplicationName("JMHZ Converter")
    window = OrganizationsWindow(workspace.root)
    try:
        case, org, imported, _ = entries[0]
        window.period.setText(case["period"])
        window.refresh()
        window.select_organization(org.id)
        require(window.organizations.rowCount() == 2 and window.imported.id == imported.id)
        window.check()
        require(window.rows.rowCount() == case["pp_count"] and window.analysis is not None)
        root, suite = load_suite()
        profiles = suite["profiles"][str(case["year"])]
        window.prepare_monthly_paths(root / profiles["employee"], root / profiles["monthly"], root / case["employer_csv"], root / case["parameters"])
        require(window.draft_id is not None and "PVPOJ" in window.draft.toPlainText())
        window.show()
        app.processEvents()
        window.resize(1024, 720)
        app.processEvents()
        require(window.minimumSizeHint().width() <= 1024)
        other = workspace.organizations()[1]
        window.select_organization(other.id)
        require(window.draft_id is None and window.draft.toPlainText() == "")
        return True
    finally:
        dispose_window(window)


def self_test():
    from app.core.backups import create_backup, restore_backup
    from app.core.conversion import FinalExportBlocked, export_final
    from app.ui.qt_compat import QT_API, QtCore
    import lxml
    import openpyxl
    report = {"status": "failed", "data": "synthetic_only", "final_export": "blocked",
              "windows_acceptance": "manual_target_review_required", "frozen": bool(getattr(sys, "frozen", False)),
              "os": platform.platform(), "python": platform.python_version(), "qt_binding": QT_API, "checks": []}
    report["versions"] = {"qt": QtCore.qVersion(), "binding": __import__(QT_API).__version__,
                          "lxml": lxml.__version__, "openpyxl": openpyxl.__version__}
    def passed(name):
        report["checks"].append(name)
    with tempfile.TemporaryDirectory(prefix="jmhz-synthetic-") as directory:
        temporary = Path(directory)
        workspace, entries = seed_workspace(temporary / "source")
        passed("cp1250_numbered_csv_decimal_all_monthly_xsd_both_versions")
        passed("hpp_dpc_dpp_zero_income_foreign_without_rc_multiple_pp")
        first, org, imported, draft_id = next(e for e in entries if e[0]["id"] == "b-2026-09")
        root, suite = load_suite()
        profiles = suite["profiles"]["2026"]
        # External definitions are real passive offline packages, not embedded paths.
        packages = []
        for version in ("1", "2"):
            archive = temporary / ("definitions-" + version + ".zip")
            pin = build_package(read_json(root, profiles["numbered"]), archive, "synthetic-preview", version,
                default_official_root(), employee_profile=read_json(root, profiles["employee"]), monthly_profile=read_json(root, profiles["monthly"]))["manifest_sha256"]
            packages.append(install_package(archive, workspace.root / "definition-packages", pin))
        workspace.set_profile(package_directory=packages[0].directory, approved_sha256=packages[0].manifest_sha256)
        repeated = workspace.import_file(org.id, imported.period, root / first["csv"], "cp1250", ";")
        checked = workspace.analyze(org.id, repeated.id)
        workspace.record_version(org.id, repeated.id, checked.index, 1)
        eid = workspace.import_employer_table(org.id, repeated.id, read_csv(root / first["employer_csv"], "cp1250", ";"), read_json(root, profiles["monthly"]))
        repeated_draft, result = workspace.prepare_monthly_draft(org.id, repeated.id, eid, read_json(root, profiles["employee"]), read_json(root, first["parameters"]), default_official_root())
        require(result.xsd_valid)
        workspace.set_profile(package_directory=packages[1].directory, approved_sha256=packages[1].manifest_sha256)
        require(workspace.get_import(org.id, imported.id).source == imported.source and packages[0].directory.exists())
        require(len(workspace.history(org.id, imported.period)["versions"]) == 2)
        passed("reimport_immutable_history_revisions_offline_definitions_versions")
        negative_org = entries[0][1]
        broken = workspace.import_file(negative_org.id, entries[0][2].period, root / suite["negative_csv"], "cp1250", ";")
        require(workspace.analyze(negative_org.id, broken.id).issues)
        passed("intentional_control_mismatch_and_missing_value")
        pending_case, pending_org, _, _ = next(e for e in entries if e[0]["id"] == "b-2027-09")
        p = suite["profiles"]["2027"]
        workspace.set_profile(read_json(root, p["numbered"]))
        pending = workspace.import_file(pending_org.id, Period.parse(pending_case["period"]), root / suite["pending_oic_csv"], "cp1250", ";")
        eid = workspace.import_employer_table(pending_org.id, pending.id, read_csv(root / pending_case["employer_csv"], "cp1250", ";"), read_json(root, p["monthly"]))
        _, pending_result = workspace.prepare_monthly_draft(pending_org.id, pending.id, eid, read_json(root, p["employee"]), read_json(root, pending_case["parameters"]), default_official_root())
        require(pending_result.xsd_valid and any(i.code == "primary_unresolved" for i in pending_result.review_issues))
        passed("pending_oic_alternative_keeps_methodological_review")
        other = next(o for o in workspace.organizations() if o.id != org.id)
        try:
            workspace.get_import(other.id, imported.id)
        except ValueError:
            passed("organization_isolation")
        else:
            require(False)
        archive = temporary / "synthetic-backup.zip"
        backup = create_backup(workspace, org.id, archive)
        restored = OrganizationWorkspace(temporary / "restored")
        restore_backup(restored, archive, backup["sha256"])
        require(len(restored.organizations()) == 1)
        require(restored.draft_bytes(org.id, repeated.id, repeated_draft) == workspace.draft_bytes(org.id, repeated.id, repeated_draft))
        passed("unencrypted_organization_backup_restore")
        # GUI gets its own clean seed so the deliberate invalid import does not mask it.
        gui_workspace, gui_entries = seed_workspace(temporary / "gui")
        exercise_gui(gui_workspace, gui_entries)
        passed("qt_gui_overview_import_counts_checks_xml_context_reset_shutdown")
        try:
            export_final(None, temporary / "forbidden.xml")
        except FinalExportBlocked:
            passed("final_export_blocked")
        else:
            require(False)
    report["status"] = "passed"
    return report
