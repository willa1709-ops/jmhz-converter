from __future__ import annotations

import json
from pathlib import Path

from lxml import etree
import pytest

from app.core.models import SourceRow, SourceTable
from app.core.monthly_xml import prepare_monthly_xml
from app.core.organizations import OrganizationWorkspace
from app.core.submission_plans import history, record_plan
from test_employee_xml import case, OFFICIAL

ROOT = Path(__file__).parents[1]


def employer_case(year, variable_symbol="0000000001", ico="00000001"):
    profile = json.loads((ROOT / "config/conversion/monthly-{}.json".format(year)).read_text())
    values = {c: "" for c in [r['column'] for r in profile['fields'].values()]}
    values.update(period="{}-09".format(year), employer_ico=ico, employer_variable_symbol=variable_symbol)
    for path, ref in profile["fields"].items():
        if path.startswith("PVPOJ/") or path in {"souhrn/danUdajeMesic/danZalohaPoSleve", "souhrn/kolektivniSmlouvy/kolektivniSmlouva/typKolektSmlouvy"}:
            values[ref["column"]] = "0"  # Explicit synthetic source facts, never application defaults.
    return profile, SourceTable(tuple(values), (SourceRow(2, values),))


def prepare(data, source, monthly):
    numbered, profile, row, context, parameters = data
    return prepare_monthly_xml(SourceTable(tuple(row), (SourceRow(2, row),)), numbered, profile, context, parameters, source, monthly, OFFICIAL)


@pytest.mark.parametrize("year", [2026, 2027])
@pytest.mark.parametrize("kind,zero", [("HPP", False), ("DPC", False), ("DPP", False), ("HPP", True), ("DPP", True)])
def test_all_three_packet_parts_validate_against_real_xsd(year, kind, zero):
    data = case(year, kind, zero)
    monthly, source = employer_case(year)
    result = prepare(data, source, monthly)
    assert result.xsd_valid, result.issues
    root = etree.fromstring(result.draft_xml)
    assert [etree.QName(n).localname for n in root] == ["hlavicka", "souhrn", "PVPOJ", "formulareOsob" if year == 2026 else "formulareZamestnani"]
    assert result.review_issues and not result.submission_ready


@pytest.mark.parametrize("year", [2026, 2027])
def test_foreign_alternative_is_preserved_in_full_packet(year):
    data = case(year)
    data[2].update(oic="", rc="", registration_status="pending_oic")
    profile, source = employer_case(year)
    result = prepare(data, source, profile)
    assert result.xsd_valid, result.issues
    assert etree.fromstring(result.draft_xml).xpath("//*[local-name()='prijmeni']/text()") == ["Fixture"]
    assert not result.submission_ready


@pytest.mark.parametrize("path,value,code", [("PVPOJ/pojistne/pojistneCelkem", "1", "control_13"),
    ("PVPOJ/pojistneUhrada", "1", "control_4"), ("PVPOJ/pojistne/pojistneZamestnavateleCelkem", "1", "control_11"),
    ("PVPOJ/pojistne/pojistneZamestnance", "", "employer_xsd_required")])
def test_supplied_totals_are_checked_not_guessed(path, value, code):
    data = case()
    profile, source = employer_case(2026)
    source.rows[0].values[profile["fields"][path]["column"]] = value
    result = prepare(data, source, profile)
    assert not result.draft_xml and any(i.code == code for i in result.issues)


def test_missing_optional_money_is_not_silently_zero():
    profile, source = employer_case(2026)
    for path, ref in profile["fields"].items():
        if path.startswith("PVPOJ/slevaZamestnavatele/"):
            source.rows[0].values[ref["column"]] = ""
    result = prepare(case(), source, profile)
    assert result.xsd_valid
    assert any(i.code == "control_4_incomplete" for i in result.review_issues)


def test_explicit_catalog_sum_can_replace_unknown_native_summary_item_and_check_control():
    data = case()
    profile, source = employer_case(2026)
    path = "PVPOJ/pojistne/pojistneZamestnance"
    profile["fields"][path] = {"control_sum": "12", "compare_column": "payroll_control"}
    source.rows[0].values["payroll_control"] = "0"
    source = SourceTable(source.columns + ("payroll_control",), source.rows)
    result = prepare(data, source, profile)
    assert result.xsd_valid, result.issues
    assert "12" in result.evidence["derived_control_ids"]
    source.rows[0].values["payroll_control"] = "1"
    assert any(i.code == "derived_control_mismatch" for i in prepare(data, source, profile).issues)
    data[2]["target_10370"] = ""
    assert any(i.code == "documented_sum_missing_data" for i in prepare(data, source, profile).issues)


def test_full_packet_retains_multiple_pp_without_summing_person_data_by_guess():
    data = case(2027)
    data[2].update(target_10286="300", target_10344="300")
    second = dict(data[2], internal_number="10", id_ppv="2", form_id="00000000-0000-4000-8000-000000000003", source_income="200", target_10328="200", target_10535="200")
    monthly, employer = employer_case(2027)
    result = prepare_monthly_xml(SourceTable(tuple(data[2]), (SourceRow(2, data[2]), SourceRow(3, second))), data[0], data[1], data[3], data[4], employer, monthly, OFFICIAL)
    assert result.xsd_valid, result.issues
    root = etree.fromstring(result.draft_xml)
    assert root.xpath("//*[local-name()='primarniPpv']/text()") == ["true", "false"]
    assert len(root.xpath("//*[local-name()='souhrnDataZec']")) == 1


def test_guid_claims_cannot_be_reused_by_another_organization(tmp_path):
    work, org, other, data, imported, identity = workspace_case(tmp_path)
    record_plan(work, org.id, imported.id, identity, 0)
    other_import = work.import_table(other.id, imported.period, imported.source)
    profile, source = employer_case(2027, other.variable_symbol, other.ico)
    employer = work.import_employer_table(other.id, other_import.id, source, profile)
    draft, result = work.prepare_monthly_draft(other.id, other_import.id, employer, data[1], dict(data[4], employer_variable_symbol=other.variable_symbol), OFFICIAL)
    assert result.xsd_valid
    with pytest.raises(ValueError):
        record_plan(work, other.id, other_import.id, draft, 0)


def workspace_case(tmp_path):
    data = case(2027)
    workspace = OrganizationWorkspace(tmp_path)
    org = workspace.register("Synthetic A", "00000001", "0000000001")
    other = workspace.register("Synthetic B", "00000002", "0000000002")
    workspace.set_profile(data[0])
    source = SourceTable(tuple(data[2]), (SourceRow(2, data[2]),))
    imported = workspace.import_table(org.id, data[3].period, source)
    monthly, employer = employer_case(2027)
    eid = workspace.import_employer_table(org.id, imported.id, employer, monthly)
    identity, result = workspace.prepare_monthly_draft(org.id, imported.id, eid, data[1], data[4], OFFICIAL)
    assert result.xsd_valid, result.issues
    return workspace, org, other, data, imported, identity


def test_organization_employer_imports_and_lineage_stay_separate(tmp_path):
    work, org, other, data, imported, identity = workspace_case(tmp_path)
    plan = record_plan(work, org.id, imported.id, identity, 0)
    assert history(work, org.id, imported.period)[0]["mode"] == "R"
    # An input reimport is neither a new official GUID nor an automatic correction.
    repeated = work.import_table(org.id, imported.period, imported.source)
    monthly, employer = employer_case(2027)
    eid = work.import_employer_table(org.id, repeated.id, employer, monthly)
    new_draft, _ = work.prepare_monthly_draft(org.id, repeated.id, eid, data[1], data[4], OFFICIAL)
    correction = record_plan(work, org.id, repeated.id, new_draft, 1, "O", plan, "employer_initiated")
    assert correction != plan
    assert history(work, org.id, imported.period)[1]["mode"] == "O"
    assert etree.fromstring(work.draft_bytes(org.id, repeated.id, new_draft)).xpath("//*[local-name()='typPodani']/text()") == ["R"]
    assert not history(work, other.id, imported.period)
    with pytest.raises(ValueError):
        work.prepare_monthly_draft(other.id, imported.id, eid, data[1], data[4], OFFICIAL)
    with pytest.raises(ValueError):
        record_plan(work, org.id, repeated.id, new_draft, 2, "R")
    with pytest.raises(ValueError):
        record_plan(work, org.id, repeated.id, new_draft, 2, "O", plan, "rejected_component")


def test_employer_csv_scope_and_cp1250_contract(tmp_path):
    from app.core.input import read_csv
    work, org, other, data, imported, _ = workspace_case(tmp_path)
    p, source = employer_case(2027)
    values = source.rows[0].values
    values["poznámka"] = "Příliš žluťoučký – DOS"
    path = tmp_path / "dos.csv"
    path.write_bytes((";".join(values) + "\r\n" + ";".join(values.values()) + "\r\n").encode("cp1250"))
    parsed = read_csv(path, "cp1250", ";")
    assert parsed.rows[0].values["poznámka"] == values["poznámka"]
    work.import_employer_table(org.id, imported.id, parsed, p)
    parsed.rows[0].values["employer_variable_symbol"] = other.variable_symbol
    with pytest.raises(ValueError):
        work.import_employer_table(org.id, imported.id, parsed, p)
