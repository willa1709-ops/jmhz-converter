"""All amounts/identities are explicitly synthetic test input, not payroll definitions."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json

from lxml import etree
import pytest

from app.core.employee_schema import EmployeeContract
from app.core.employee_xml import prepare_employee_xml, load_employee_profile
from app.core.models import SourceRow, SourceTable
from app.core.payroll import load_numbered_profile
from app.core.periods import Period, SubmissionContext

ROOT = Path(__file__).parents[1]
OFFICIAL = ROOT / "schemas/official"
OIC, RC = "1234567890", "900101/1234"
BUNDLES = {2026: "jmhz-1.4.3.6", 2027: "jmhz-1.5.0.3"}


def case(year=2026, kind="HPP", zero=False):
    contract = EmployeeContract(OFFICIAL, BUNDLES[year])
    numbered = load_numbered_profile((ROOT / "config/payroll/numbered.template.json").read_text())
    numbered["controls"] = []
    numbered["calculations"] = {}
    # A financial item ID is intentionally unrelated to the JMHZ ID; its real number is unknown.
    numbered["items"] = {"987": {"column": "source_income"}}
    for key in ["employment_type", "given_name", "surname", "birth_date", "employment_start", "employment_end",
                "registration_status", "work_performed", "employment_detail", "eldp_segments"]:
        numbered["metadata"][key] = {"column": key}
    numbered["metadata"]["income_amount"] = {"item": "987"}
    profile = {"format_version": 1, "scenario": "bezPriznaku", "bundle_id": BUNDLES[year], "status": "working_unverified", "fields": {}}
    row = {"internal_number": "0002", "period": "{}-09".format(year), "oic": OIC, "rc": RC,
           "form_id": "00000000-0000-4000-8000-000000000001", "id_ppv": "1", "activity_code": {"HPP": "1", "DPC": "A", "DPP": "T"}[kind],
           "employment_type": kind, "given_name": "Synthetic", "surname": "Fixture", "birth_date": "1990-01-01",
           "employment_start": "2020-01-01", "employment_end": "", "registration_status": "registered", "work_performed": "no" if zero else "yes",
           "employment_detail": "1", "eldp_segments": "1", "source_income": "0" if zero else "100"}
    # Explicit fixture values covering required XSD members and the documented zero form.
    values = {"10286": "100", "10419": "false", "10344": "100", "10116": "false", "10482": "0", "10371": "0",
              "10354": "{}-09-01".format(year), "10355": "{}-09-30".format(year), "10356": "0",
              "10229": "Synthetic", "10230": "554782", "10231": "CZ", "10232": "false", "10247": "false", "10251": "false",
              "10259": "160", "10260": "160", "10261": "40", "10265": "30", "10268": "160", "10328": "100", "10345": "0",
              "10490": "false", "10546": "false", "10372": "false", "10535": "100", "10481": "0", "10370": "0"}
    if year == 2027:
        values.update({"10555": "0", "10579": "false"})
    if zero:
        for key in ["10286", "10344", "10259", "10260", "10261", "10265", "10268", "10328", "10535"]:
            values[key] = "0"
        values.update({"10319": "false", "10320": "false"})
    for id, value in values.items():
        matches = [p for p in contract.fields.values() if id in p.ids]
        assert len(matches) == 1, (id, matches)
        path = matches[0].path
        profile["fields"][path] = {"column": "target_" + id}
        if "/souhrnDataZec/" in path:
            profile["fields"][path]["on"] = "primary"
        row["target_" + id] = value
    context = SubmissionContext(Period(year, 9), 0)
    parameters = {"submission_id": "00000000-0000-4000-8000-000000000002", "employer_variable_symbol": "0000000001",
                  "year": year, "month": 9, "filled_at": "{}-10-01T12:00:00".format(year)}
    return numbered, profile, row, context, parameters


def run_case(case_data, rows=None):
    numbered, profile, row, context, parameters = case_data
    rows = rows or [row]
    table = SourceTable(tuple(row), tuple(SourceRow(i + 2, r) for i, r in enumerate(rows)))
    return prepare_employee_xml(table, numbered, profile, context, parameters, OFFICIAL)


@pytest.mark.parametrize("year", [2026, 2027])
@pytest.mark.parametrize("kind", ["HPP", "DPC", "DPP"])
def test_regular_employees_generate_real_bez_priznaku_for_both_versions(year, kind):
    result = run_case(case(year, kind))
    assert not result.issues, result.issues
    assert result.xsd_valid and result.draft_xml
    root = etree.fromstring(result.draft_xml)
    assert len(root.xpath("//*[local-name()='bezPriznaku']")) == 1
    assert root.xpath("//*[local-name()='primarniPpv']/text()") == ["true"]
    assert root.xpath("//*[local-name()='typPodani']/text()") == ["R"]
    assert not result.submission_ready and result.methodological_validation == "partial"
    assert result.review_issues


@pytest.mark.parametrize("year", [2026, 2027])
@pytest.mark.parametrize("kind", ["HPP", "DPC", "DPP"])
def test_registered_whole_month_no_work_no_income_uses_documented_values(year, kind):
    result = run_case(case(year, kind, True))
    assert not result.issues, result.issues
    assert result.xsd_valid and result.draft_xml
    assert result.record_count == 1 and not result.submission_ready


@pytest.mark.parametrize("change,code", [({"target_10354": "2026-08-31"}, "control_299"),
    ({"target_10355": "2026-09-01", "target_10354": "2026-09-20"}, "control_43"),
    ({"target_10355": "2026-10-02"}, "control_44"),
    ({"target_10356": "31"}, "control_58"), ({"target_10328": ""}, "xsd_required"),
    ({"target_10328": "NaN"}, "field_format"), ({"employment_detail": "3"}, "specific_group_unconfirmed"),
    ({"eldp_segments": "2"}, "segment_scope"), ({"activity_code": "11"}, "unsupported_activity")])
def test_actual_required_values_methodological_checks_and_supported_scope(change, code):
    data = case()
    data[2].update(change)
    result = run_case(data)
    assert not result.draft_xml and not result.xsd_valid
    assert any(i.code == code for i in result.issues), result.issues


@pytest.mark.parametrize("change", [{"work_performed": "yes"}, {"employment_start": "2026-09-02"},
                                   {"registration_status": "unknown"}, {"source_income": ""}])
def test_zero_alone_does_not_authorize_zero_reporting(change):
    data = case(zero=True)
    data[2].update(change)
    result = run_case(data)
    assert result.issues and result.draft_xml is None


@pytest.mark.parametrize("year", [2026, 2027])
def test_foreign_employee_without_rc_and_alternative_without_oic(year):
    data = case(year)
    data[2]["rc"] = ""
    assert run_case(data).xsd_valid
    data[2].update(oic="", registration_status="pending_oic")
    result = run_case(data)
    assert result.xsd_valid and not result.issues, result.issues
    root = etree.fromstring(result.draft_xml)
    assert not root.xpath("//*[local-name()='ikMpsv']")
    assert root.xpath("//*[local-name()='prijmeni']/text()") == ["Fixture"]
    assert not root.xpath("//*[local-name()='primarniPpv']")
    assert any(i.code == "primary_unresolved" for i in result.review_issues)
    assert OIC not in json.dumps(result.safe_report()) and RC not in repr(result)
    data[2]["birth_date"] = ""
    assert run_case(data).draft_xml is None


def test_two_pp_preserve_row_amounts_and_summary_only_on_the_primary():
    data = case()
    second = dict(data[2], internal_number="10", id_ppv="2", form_id="00000000-0000-4000-8000-000000000003", target_10328="200")
    result = run_case(data, [data[2], second])
    assert result.xsd_valid, result.issues
    root = etree.fromstring(result.draft_xml)
    assert root.xpath("//*[local-name()='primarniPpv']/text()") == ["true", "false"]
    assert len(root.xpath("//*[local-name()='souhrnDataZec']")) == 1
    assert root.xpath("//*[local-name()='mzdaZuctovana']/text()") == ["100", "200"]


def test_profile_rejects_guessed_elements_and_identifier_as_payroll_data():
    numbered, profile, _, _, _ = case()
    contract = EmployeeContract(OFFICIAL, profile["bundle_id"])
    invalid = deepcopy(profile)
    invalid["fields"]["bezPriznaku/madeUpElement"] = {"column": "anything"}
    with pytest.raises(ValueError):
        load_employee_profile(json.dumps(invalid), numbered, contract)
    invalid = deepcopy(profile)
    invalid["fields"]["bezPriznaku/mzda/mzdaZuctovana"] = {"column": "oic"}
    with pytest.raises(ValueError):
        load_employee_profile(json.dumps(invalid), numbered, contract)


@pytest.mark.parametrize("parent,child,control", [("10328", "10329", "267"), ("10268", "10269", "282")])
def test_zero_total_forbids_even_explicit_zero_breakdown(parent, child, control):
    data = case()
    contract = EmployeeContract(OFFICIAL, data[1]["bundle_id"])
    path = next(p.path for p in contract.fields.values() if child in p.ids)
    data[1]["fields"][path] = {"column": "forbidden_breakdown"}
    data[2].update({"target_" + parent: "0", "forbidden_breakdown": "0"})
    result = run_case(data)
    assert any(i.code == "control_" + control for i in result.issues)


def test_numbered_item_and_exact_row_calculation_feed_the_actual_xml():
    data = case()
    data[0]["items"].update({"988": {"column": "bonus"}, "989": {"column": "deduction"}})
    data[0]["calculations"]["exact_pay"] = {"op": "subtract", "args": [{"op": "add", "args": [{"item": "987"}, {"item": "988"}]}, {"item": "989"}]}
    data[1]["fields"]["bezPriznaku/mzda/mzdaZuctovana"] = {"calculation": "exact_pay"}
    data[2].update(source_income="100.10", bonus="0.20", deduction="0.30")
    result = run_case(data)
    assert result.xsd_valid, result.issues
    assert etree.fromstring(result.draft_xml).xpath("//*[local-name()='mzdaZuctovana']/text()") == ["100"]


def test_official_row_base_breakdown_and_hours_checks():
    data = case()
    contract = EmployeeContract(OFFICIAL, data[1]["bundle_id"])
    for id, value in [("10477", "100"), ("10478", "33"), ("10479", "33"), ("10480", "34")]:
        path = next(p.path for p in contract.fields.values() if id in p.ids)
        data[1]["fields"][path] = {"column": "checked_" + id}
        data[2]["checked_" + id] = value
    assert run_case(data).xsd_valid
    data[2]["checked_10480"] = "33"
    assert any(i.code == "control_216" for i in run_case(data).issues)
    for id, value in [("10275", "5"), ("10276", "2"), ("10279", "3")]:
        path = next(p.path for p in contract.fields.values() if id in p.ids)
        data[1]["fields"][path] = {"column": "checked_" + id}
        data[2]["checked_" + id] = value
    assert any(i.code == "control_23" for i in run_case(data).issues)


def test_organization_history_package_and_cli_keep_employee_xml_isolated(tmp_path):
    import subprocess
    import sys
    from app.core.organizations import OrganizationWorkspace
    from app.core.packages import build_package, install_package
    numbered, profile, row, context, parameters = case(2027)
    workspace = OrganizationWorkspace(tmp_path / "workspace")
    org = workspace.register("Synthetic A", "00000001", parameters["employer_variable_symbol"])
    other = workspace.register("Synthetic B", "00000002", "0000000002")
    archive = tmp_path / "employees.zip"
    pin = build_package(numbered, archive, "synthetic-employees", "1", OFFICIAL, employee_profile=profile)["manifest_sha256"]
    package = install_package(archive, workspace.root / "definition-packages", pin)
    workspace.set_profile(package_directory=package.directory, approved_sha256=pin)
    imported = workspace.import_table(org.id, context.period, SourceTable(tuple(row), (SourceRow(2, row),)))
    with pytest.raises(ValueError):
        workspace.prepare_employee_draft(other.id, imported.id, profile, parameters, OFFICIAL)
    with pytest.raises(ValueError):
        workspace.prepare_employee_draft(org.id, imported.id, profile, dict(parameters, employer_variable_symbol=other.variable_symbol), OFFICIAL)
    identity, result = workspace.prepare_employee_draft(org.id, imported.id, profile, parameters, tmp_path / "unused_root")
    assert identity and result.xsd_valid
    assert workspace.draft_validation(org.id, imported.id, identity)["submission_ready"] is False
    assert workspace.overview(context.period)[0]["error_count"] > 0  # Open XML methodology must not look approved.
    checks = workspace.analysis_history(org.id, imported.id)
    snapshot = workspace.analysis_snapshot(org.id, imported.id, checks[-1]["analysis_index"])
    assert snapshot["employee_validation"]["xsd_valid"]
    with pytest.raises(ValueError):
        workspace.record_version(org.id, imported.id, checks[-1]["analysis_index"], 0)
    with pytest.raises(ValueError):
        workspace.draft_validation(other.id, imported.id, identity)
    params = tmp_path / "params.json"
    params.write_text(json.dumps(parameters))
    completed = subprocess.run([sys.executable, "-m", "app.core.employee_xml", "--workspace", str(workspace.root), "--organization", org.id,
        "--import-id", imported.id, "--parameters", str(params), "--write-draft"], cwd=str(ROOT), capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["draft_written"]
    assert OIC not in completed.stdout + completed.stderr and RC not in completed.stdout + completed.stderr
    assert len(list(workspace.organization_directory(org.id).glob("drafts/*.draft.xml"))) == 1
    assert not list(workspace.organization_directory(other.id).glob("drafts/*.draft.xml"))
