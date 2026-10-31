from pathlib import Path
import shutil

import pytest

from app.core.backups import create_backup, restore_backup
from app.core.organizations import OrganizationWorkspace
from app.core.submission_plans import record_plan, history
from test_monthly_packet import workspace_case, employer_case


def test_organization_snapshot_restores_data_totals_xml_and_lineage_without_mixing(tmp_path):
    source, org, other, data, imported, draft = workspace_case(tmp_path / "source")
    record_plan(source, org.id, imported.id, draft, 0)
    archive = tmp_path / "private.zip"
    report = create_backup(source, org.id, archive)
    assert report["encryption"] == "none"
    restored = OrganizationWorkspace(tmp_path / "restored")
    restored_org = restore_backup(restored, archive, report["sha256"])
    assert restored_org == org
    assert restored.get_import(org.id, imported.id).source == imported.source
    assert restored.draft_bytes(org.id, imported.id, draft) == source.draft_bytes(org.id, imported.id, draft)
    assert history(restored, org.id, imported.period)[0]["mode"] == "R"
    assert [o.id for o in restored.organizations()] == [org.id]
    with pytest.raises(ValueError):
        restored.get_import(other.id, imported.id)
    with pytest.raises(ValueError):
        restore_backup(restored, archive, report["sha256"])
    with pytest.raises(ValueError):
        create_backup(source, org.id, archive)


def test_changed_archive_or_wrong_hash_never_creates_an_organization(tmp_path):
    source, org, _, _, _, _ = workspace_case(tmp_path / "source")
    archive = tmp_path / "private.zip"
    pin = create_backup(source, org.id, archive)["sha256"]
    restored = OrganizationWorkspace(tmp_path / "restored")
    with pytest.raises(ValueError):
        restore_backup(restored, archive, "0" * 64)
    with archive.open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError):
        restore_backup(restored, archive, pin)
    assert not restored.organizations()


def test_backup_preserves_old_offline_definitions_and_relocates_only_storage_paths(tmp_path):
    from app.core.packages import build_package, install_package
    from app.core.models import SourceRow, SourceTable
    from test_employee_xml import case, OFFICIAL
    data = case()
    workspace = OrganizationWorkspace(tmp_path / "source")
    org = workspace.register("Synthetic", "00000001", "0000000001")
    archive = tmp_path / "defs.zip"
    monthly, employer = employer_case(2026)
    pin = build_package(data[0], archive, "synthetic", "1", OFFICIAL, employee_profile=data[1], monthly_profile=monthly)["manifest_sha256"]
    package = install_package(archive, workspace.root / "definition-packages", pin)
    workspace.set_profile(package_directory=package.directory, approved_sha256=pin)
    imported = workspace.import_table(org.id, data[3].period, SourceTable(tuple(data[2]), (SourceRow(2, data[2]),)))
    backup = tmp_path / "backup.zip"
    report = create_backup(workspace, org.id, backup)
    restored = OrganizationWorkspace(tmp_path / "restored")
    restore_backup(restored, backup, report["sha256"])
    shutil.rmtree(workspace.root)  # Recovery must not depend on the original absolute paths.
    copied = restored.get_import(org.id, imported.id)
    assert copied.definition["sha256"] == pin and copied.profile == imported.profile
    assert str(restored.root) in copied.definition["directory"]
    assert not restored.analyze(org.id, imported.id).payroll.issues
    employer_id = restored.import_employer_table(org.id, imported.id, employer, monthly)
    _, result = restored.prepare_monthly_draft(org.id, imported.id, employer_id, data[1], data[4], OFFICIAL)
    assert result.xsd_valid  # Uses the recovered, pinned XSD/profile set.
