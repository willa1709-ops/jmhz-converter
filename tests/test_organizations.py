from __future__ import annotations

import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from app.core.models import SourceRow, SourceTable
from app.core.organizations import OrganizationWorkspace
from app.core.payroll import load_numbered_profile, prepare_payroll
from app.core.periods import Period, SubmissionContext
from app.core.schemas import IdentityValidator
from app.core.workforce import assess_workforce

ROOT = Path(__file__).parents[1]
OFFICIAL = ROOT / "schemas/official"
OIC = "1234567890"  # Synthetic structural keys, not identity verification.
RC = "900101/1234"


def profile(workforce=True):
    p = load_numbered_profile((ROOT / "config/payroll/numbered.template.json").read_text(encoding="utf-8"))
    if workforce:
        for name in ("employment_type", "given_name", "surname", "birth_date", "employment_start", "employment_end",
                     "registration_status", "work_performed", "absence_reason"):
            p["metadata"][name] = {"column": name}
        p["metadata"]["income_amount"] = {"item": "190"}
    return p


def values(**changes):
    row = {"internal_number": "0002", "period": "26-09", "oic": OIC, "rc": RC,
           "form_id": "00000000-0000-4000-8000-000000000001", "id_ppv": "1", "activity_code": "11",
           "p100": "100", "p110": "10", "p120": "5", "p190": "105", "p200": "0",
           "employment_type": "HPP", "given_name": "Synthetic", "surname": "Fixture", "birth_date": "1990-01-01",
           "employment_start": "2020-01-01", "employment_end": "", "registration_status": "registered",
           "work_performed": "yes", "absence_reason": ""}
    row.update(changes)
    return row


def source(*rows):
    return SourceTable(tuple(rows[0]), tuple(SourceRow(i + 2, r) for i, r in enumerate(rows)))


def assess(table, p=None, bundle="jmhz-1.5.0.3"):
    p = p or profile()
    payroll = prepare_payroll(table, p, SubmissionContext(Period(2026, 9), 0))
    assessments, issues = assess_workforce(table, payroll, p, OFFICIAL, bundle)
    return payroll, assessments, issues


@pytest.fixture
def workspace(tmp_path):
    work = OrganizationWorkspace(tmp_path / "workspace")
    a = work.register("Synthetic A", "00000001", "0000000001", {"dic": "synthetic"})
    b = work.register("Synthetic B", "00000002", "0000000002")
    work.set_profile(profile())
    return work, a, b


def test_foreign_employee_without_rc_uses_real_oic_and_is_retained():
    payroll, records, issues = assess(source(values(rc="")))
    assert not payroll.issues and not issues
    assert records[0].identity_mode == "oic" and records[0].retained
    assert payroll.rows[0].primary_pp is True


@pytest.mark.parametrize("bundle", ["jmhz-1.4.3.6", "jmhz-1.5.0.3"])
def test_waiting_for_oic_uses_real_alternative_type_but_does_not_guess_person_groups(bundle):
    table = source(values(oic="", rc="", registration_status="pending_oic"))
    payroll, records, issues = assess(table, bundle=bundle)
    assert records[0].identity_mode == "alternative_xsd_valid"
    assert records[0].retained and records[0].alternative["given_name"] == "Synthetic"
    assert payroll.rows[0].primary_pp is None
    assert any(i.code == "alternative_pairing_unresolved" for i in issues)
    assert payroll.rows[0].metadata["oic"] is None
    assert not payroll.submission_ready
    alternative = IdentityValidator(OFFICIAL, bundle)
    assert alternative.alternative(table.rows[0].values).xsd_valid
    assert not alternative.alternative(dict(table.rows[0].values, activity_code="INVALID")).xsd_valid


def test_missing_alternative_data_requests_exact_fields_or_registration_without_pii():
    _, records, issues = assess(source(values(oic="", rc="", birth_date="", registration_status="pending_oic")))
    assert "birth_date" in records[0].required_fields
    assert any(i.field == "birth_date" and i.code == "alternative_identity_required" for i in issues)
    _, _, missing = assess(source(values(oic="", rc="", registration_status="not_registered")))
    assert any(i.code == "registration_or_identity_required" for i in missing)
    assert OIC not in repr(issues) and RC not in repr(issues) and "Fixture" not in repr(issues)


def test_missing_ppv_and_inconsistent_registration_are_concrete_blockers():
    _, records, issues = assess(source(values(id_ppv="")))
    assert "id_ppv" in records[0].required_fields
    assert any(i.code == "ppv_required" for i in issues)
    _, _, pending = assess(source(values(registration_status="pending_oic")))
    assert any(i.code == "registration_status_conflict" for i in pending)


def test_selected_approved_package_supplies_identity_xsd_and_is_rechecked_on_use(workspace, tmp_path):
    from app.core.packages import build_package, install_package
    work, a, _ = workspace
    archive = tmp_path / "definitions.zip"
    pin = build_package(profile(), archive, "working-workforce", "1", OFFICIAL)["manifest_sha256"]
    package = install_package(archive, work.root / "definition-packages", pin)
    work.set_profile(package_directory=package.directory, approved_sha256=pin)
    imported = work.import_table(a.id, Period(2026, 9), source(values(oic="", rc="", registration_status="pending_oic")))
    # The unrelated root argument must not replace the selected package's XSD.
    checked = work.analyze(a.id, imported.id, tmp_path / "unrelated", "jmhz-1.5.0.3")
    assert checked.assessments[0].identity_mode == "alternative_xsd_valid"
    assert checked.report["validation_evidence"]["xsd_dependency_hashes"]
    assert checked.report["validation_evidence"]["bundle_id"] == "jmhz-1.5.0.3"
    numbered = package.directory / package.manifest["entry_points"]["numbered_profile"]
    numbered.write_text("{}")
    with pytest.raises(ValueError):
        work.analyze(a.id, imported.id, OFFICIAL, "jmhz-1.5.0.3")


def test_shipped_workforce_package_matches_template_and_preserves_old_package(tmp_path):
    from app.core.packages import install_package
    pin = "541b7563f0146a4edcba889ac6aa1e9a3c83d48088f5c4df095729a9d72dbfab"
    package = install_package(ROOT / "definition-packages/working-workforce-1.0.zip", tmp_path / "store", pin)
    assert package.profile == load_numbered_profile((ROOT / "config/payroll/workforce.template.json").read_text())
    assert (ROOT / "definition-packages/working-payroll-2027-1.0.zip").exists()


@pytest.mark.parametrize("kind,reason", [("HPP", "sickness"), ("HPP", "parental"), ("DPP", "not_worked"), ("DPČ", "not_worked")])
def test_zero_income_registered_employment_is_retained_with_conditional_documented_path(kind, reason):
    payroll, records, issues = assess(source(values(employment_type=kind, p100="0", p110="0", p120="0", p190="0", work_performed="no", absence_reason=reason)))
    assert len(payroll.rows) == 1 and not payroll.issues
    assert records[0].income_state == "zero"
    assert records[0].reporting_decision == "include_zero_registered_no_work_candidate"
    assert records[0].retained
    assert any(i.code == "zero_income_methodology_review" for i in issues)


@pytest.mark.parametrize("mode,state", [("zero", "zero"), ("blank", "blank"), ("none", "absent_value"), ("missing_value", "absent_value"), ("missing_column", "absent_column")])
def test_zero_blank_and_absent_values_remain_distinct_without_removing_rows(mode, state):
    row = values(p190="0" if mode == "zero" else "")
    if mode == "none":
        row["p190"] = None
    if mode == "missing_value":
        row.pop("p190")
    table = SourceTable(tuple(values()) if mode != "missing_column" else tuple(k for k in values() if k != "p190"), (SourceRow(2, row),))
    payroll, records, issues = assess(table)
    assert len(payroll.rows) == 1 and records[0].retained
    assert payroll.rows[0].item_states["190"] == state
    assert records[0].income_state == state
    if mode != "zero":
        assert records[0].reporting_decision == "income_data_required"
        assert any(i.code == "income_unknown" for i in issues)


def test_unworked_or_ended_employment_is_not_silently_excluded_or_inferred():
    _, records, _ = assess(source(values(p190="0", employment_end="2026-08-31", work_performed="no")))
    assert records[0].reporting_decision == "zero_income_review_required" and records[0].retained


def test_same_employee_numbers_and_person_keys_are_isolated_by_organization(workspace):
    work, a, b = workspace
    month = Period(2026, 9)
    imported_a = work.import_table(a.id, month, source(values(given_name="OrgASentinel"), values(internal_number="10", id_ppv="2")))
    imported_b = work.import_table(b.id, month, source(values(internal_number="10", given_name="OrgBSentinel")))
    result_a, result_b = work.analyze(a.id, imported_a.id), work.analyze(b.id, imported_b.id)
    assert not result_a.issues and not result_b.issues
    assert [r.primary_pp for r in result_a.payroll.rows] == [True, False]
    assert result_b.payroll.rows[0].primary_pp is True
    assert work.employment_uuid(a.id, "10") != work.employment_uuid(b.id, "10")
    assert result_a.report["rows"][0]["person_group"] != result_b.report["rows"][0]["person_group"]
    with pytest.raises(ValueError):
        work.get_import(b.id, imported_a.id)
    with pytest.raises(ValueError):
        work.analyze(b.id, imported_a.id)
    with pytest.raises(ValueError):
        work.analysis_snapshot(b.id, imported_a.id, result_a.index)
    stored = work.analysis_snapshot(a.id, imported_a.id, result_a.index)
    assert stored["calculations"]["2"]["row_total"] == "105"
    assert stored["totals"]["row_total"]["known_sum"] == "210"
    assert len(work.analysis_history(a.id, imported_a.id)) == 1
    path_a = work.organization_directory(a.id) / "workspace.sqlite3"
    path_b = work.organization_directory(b.id) / "workspace.sqlite3"
    assert b"OrgASentinel" not in path_b.read_bytes() and b"OrgBSentinel" not in path_a.read_bytes()
    assert b"OrgASentinel" not in work.registry.read_bytes()
    safe = json.dumps(result_a.report) + repr(result_a)
    for private in [OIC, RC, "OrgASentinel", "1990-01-01"]:
        assert private not in safe


def test_reimport_and_versions_preserve_history_and_restart_per_org_and_month(workspace):
    work, a, b = workspace
    month = Period(2026, 9)
    first = work.import_table(a.id, month, source(values()))
    analysis = work.analyze(a.id, first.id)
    work.record_version(a.id, first.id, analysis.index, 0)
    second = work.import_table(a.id, month, source(values(p100="101", p190="106")))
    assert second.id != first.id and second.import_index == 1
    assert work.get_import(a.id, first.id).source.rows[0].values["p100"] == "100"
    with pytest.raises(ValueError):
        work.record_version(a.id, first.id, analysis.index, 1)
    current = work.analyze(a.id, second.id)
    with pytest.raises(ValueError):
        work.record_version(a.id, second.id, current.index, 2)
    work.record_version(a.id, second.id, current.index, 1)
    for org, period, text in [(b, month, "26-09"), (a, Period(2026, 10), "26-10")]:
        imported = work.import_table(org.id, period, source(values(period=text)))
        checked = work.analyze(org.id, imported.id)
        work.record_version(org.id, imported.id, checked.index, 0)
    assert [v["revision_index"] for v in work.history(a.id, month)["versions"]] == [0, 1]
    assert [v["revision_index"] for v in work.history(b.id, month)["versions"]] == [0]
    reopened = OrganizationWorkspace(work.root)
    overview = {r["organization"].id: r for r in reopened.overview(month)}
    assert overview[a.id]["last_revision"] == 1 and overview[b.id]["last_revision"] == 0
    assert overview[a.id]["error_count"] == 0 and overview[a.id]["pp_count"] == 1


def test_profiles_can_be_shared_overridden_and_snapshotted_without_rewriting_history(workspace):
    work, a, b = workspace
    original = work.import_table(a.id, Period(2026, 9), source(values()))
    changed = profile()
    changed["profile_version"] = "2"
    changed["items"]["100"]["column"] = "renamed"
    work.set_profile(changed, a.id)
    row = values()
    row["renamed"] = row.pop("p100")
    overridden = work.import_table(a.id, Period(2026, 9), source(row))
    assert overridden.profile["profile_version"] == "2"
    assert work.profile(b.id)[0]["profile_version"] == "1.0"
    assert not work.analyze(a.id, original.id).issues
    assert not work.analyze(a.id, overridden.id).issues
    work.clear_profile_override(a.id)
    assert work.profile(a.id)[0]["profile_version"] == "1.0"


def test_employer_and_period_mismatches_rejected_before_storage(workspace):
    work, a, _ = workspace
    p = profile()
    p["metadata"]["employer_ico"] = {"column": "employer_ico"}
    p["metadata"]["employer_variable_symbol"] = {"column": "employer_vs"}
    work.set_profile(p)
    for row in [values(employer_ico="00000002", employer_vs=a.variable_symbol),
                values(employer_ico=a.ico, employer_vs="0000000002"),
                values(period="26-10", employer_ico=a.ico, employer_vs=a.variable_symbol)]:
        with pytest.raises(ValueError):
            work.import_table(a.id, Period(2026, 9), source(row))
    assert not work.history(a.id, Period(2026, 9))["imports"]


def test_copied_database_with_another_owner_is_rejected(workspace):
    work, a, b = workspace
    imported = work.import_table(a.id, Period(2026, 9), source(values()))
    shutil.copyfile(work.organization_directory(a.id) / "workspace.sqlite3", work.organization_directory(b.id) / "workspace.sqlite3")
    with pytest.raises(ValueError):
        work.get_import(b.id, imported.id)


def test_additive_database_upgrade_preserves_old_imports_and_checks(workspace):
    work, a, _ = workspace
    imported = work.import_table(a.id, Period(2026, 9), source(values()))
    checked = work.analyze(a.id, imported.id)
    path = work.organization_directory(a.id) / "workspace.sqlite3"
    # Recreate the first workspace layout, which did not cache counts or row calculations.
    with sqlite3.connect(str(path)) as db:
        old_import = db.execute("SELECT id,organization_id,period,import_index,created_at,source_sha256,profile,definition,source FROM imports").fetchone()
        old_check = db.execute("SELECT import_id,analysis_index,created_at,error_count,report,totals FROM analyses").fetchone()
    path.unlink()
    with sqlite3.connect(str(path)) as db:
        db.execute("CREATE TABLE owner (organization_id TEXT PRIMARY KEY)")
        db.execute("INSERT INTO owner VALUES (?)", (a.id,))
        db.execute("CREATE TABLE imports (id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, period TEXT NOT NULL, import_index INTEGER NOT NULL, created_at TEXT NOT NULL, source_sha256 TEXT NOT NULL, profile TEXT NOT NULL, definition TEXT NOT NULL, source TEXT NOT NULL, UNIQUE(organization_id,period,import_index))")
        db.execute("CREATE TABLE analyses (import_id TEXT NOT NULL REFERENCES imports(id), analysis_index INTEGER NOT NULL, created_at TEXT NOT NULL, error_count INTEGER NOT NULL, report TEXT NOT NULL, totals TEXT NOT NULL, PRIMARY KEY(import_id,analysis_index))")
        db.execute("INSERT INTO imports VALUES (?,?,?,?,?,?,?,?,?)", old_import)
        db.execute("INSERT INTO analyses VALUES (?,?,?,?,?,?)", old_check)
    reopened = OrganizationWorkspace(work.root)
    assert reopened.get_import(a.id, imported.id).source == imported.source
    assert reopened.overview(Period(2026, 9))[0]["pp_count"] == 1
    snapshot = reopened.analysis_snapshot(a.id, imported.id, checked.index)
    assert snapshot["totals"]["row_total"]["known_sum"] == "105"
    assert snapshot["calculations"] == {}  # Unknown older detail is not fabricated.
    refreshed = reopened.analyze(a.id, imported.id)
    reopened.record_version(a.id, imported.id, refreshed.index, 0)
    assert len(reopened.history(a.id, imported.period)["versions"]) == 1


def test_org_xml_checks_employer_and_keeps_private_artifacts_in_scoped_storage(workspace):
    work, a, b = workspace
    work.set_profile(profile(False))
    conversion = json.loads((ROOT / "config/conversion/jiny-prijem-2027.json").read_text())
    bindings = json.loads((ROOT / "config/payroll/jiny-prijem-2027.bindings.json").read_text())
    imported = work.import_table(a.id, Period(2027, 9), source(values(period="27-09")))
    parameters = {"submission_id": "00000000-0000-4000-8000-000000000002", "employer_variable_symbol": a.variable_symbol,
                  "year": 2027, "month": 9, "filled_at": "2026-10-30T12:00:00"}
    with pytest.raises(ValueError):
        work.prepare_draft(a.id, imported.id, conversion, bindings, dict(parameters, employer_variable_symbol=b.variable_symbol), OFFICIAL)
    identity, result = work.prepare_draft(a.id, imported.id, conversion, bindings, parameters, OFFICIAL)
    assert result.xsd_valid and not result.submission_ready
    assert len(work.draft_history(a.id, imported.id)) == 1
    with pytest.raises(ValueError):
        work.draft_bytes(b.id, imported.id, identity)
    output = work.write_draft(a.id, imported.id, identity)
    assert a.id in str(output) and b.id not in str(output)
    assert output.read_bytes() == result.draft_xml
    with pytest.raises(FileExistsError):
        work.write_draft(a.id, imported.id, identity)
    assert not list(work.organization_directory(b.id).glob("drafts/*"))
    # A declared HPP must never be exported by relabelling it as jinyPrijem.
    work.set_profile(profile())
    hpp = work.import_table(a.id, Period(2027, 9), source(values(period="27-09")))
    with pytest.raises(ValueError, match="HPP/DPP"):
        work.prepare_draft(a.id, hpp.id, conversion, bindings, parameters, OFFICIAL)
