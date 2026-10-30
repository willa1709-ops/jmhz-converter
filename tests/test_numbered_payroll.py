from __future__ import annotations

from decimal import Decimal, localcontext
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from zipfile import ZipFile

from lxml import etree
import pytest

from app.core.models import SourceRow, SourceTable
from app.core.packages import build_package, install_package, load_package, canonical_json
from app.core.payroll import load_numbered_profile, prepare_payroll
from app.core.payroll_conversion import prepare_numbered_conversion
from app.core.periods import Period, RevisionRegistry, SubmissionContext

ROOT = Path(__file__).parents[1]
OIC = "1234567890"  # Synthetic structural keys only, not verified personal identifiers.
RC = "900101/1234"


def profile():
    return load_numbered_profile((ROOT / "config/payroll/numbered.template.json").read_text(encoding="utf-8"))


def values(**changes):
    result = {"internal_number": "0002", "period": "26-09", "oic": OIC, "rc": RC,
              "form_id": "00000000-0000-4000-8000-000000000001", "id_ppv": "1", "activity_code": "11",
              "p100": "100.10", "p110": "0,20", "p120": "0.01", "p190": "100.29", "p200": "0"}
    result.update(changes)
    return result


def source(*rows):
    return SourceTable(tuple(rows[0]) if rows else tuple(values()), tuple(SourceRow(i + 2, row) for i, row in enumerate(rows)))


def context(period="26-09", revision=0):
    return SubmissionContext(Period.parse(period), revision)


def test_totals_are_exact_and_only_within_the_same_row():
    first = values()
    second = values(internal_number="10", p100="200", p110="3", p120="8", p190="195")
    with localcontext() as c:
        c.prec = 4  # External context must not degrade the payroll computation.
        result = prepare_payroll(source(first, second), profile(), context())
    assert not result.issues
    assert [r.calculations["row_total"] for r in result.rows] == [Decimal("100.29"), Decimal("195")]
    assert [r.primary_pp for r in result.rows] == [True, False]
    assert result.rows[0].metadata["internal_number"] == "0002"
    assert not result.submission_ready


def test_numbered_column_names_are_configurable_and_leading_item_zeros_are_significant():
    p = profile()
    p["items"]["001"] = p["items"].pop("100")
    p["calculations"]["row_total"]["args"][0]["args"][0] = {"item": "001"}
    p["items"]["001"]["column"] = "vlastni_castka"
    row = values()
    row["vlastni_castka"] = row.pop("p100")
    result = prepare_payroll(source(row), p, context())
    assert not result.issues
    assert result.rows[0].calculations["row_total"] == Decimal("100.29")


@pytest.mark.parametrize("overrides,code", [({"p100": ""}, "calculation_input"), ({"p100": "NaN"}, "calculation_input"),
                                           ({"p190": ""}, "control_input"), ({"p190": "100.28"}, "control_mismatch")])
def test_missing_or_invalid_inputs_and_control_totals(overrides, code):
    result = prepare_payroll(source(values(**overrides)), profile(), context())
    assert any(i.code == code and i.row == 2 for i in result.issues)
    if code == "calculation_input":
        assert result.rows[0].calculations["row_total"] is None


def test_subtraction_can_be_negative_and_tolerance_is_explicit():
    p = profile()
    p["controls"][0]["tolerance"] = "0.01"
    result = prepare_payroll(source(values(p100="1", p110="2", p120="5", p190="-2.01")), p, context())
    assert not result.issues
    assert result.rows[0].calculations["row_total"] == Decimal("-2")


def test_calculation_dependencies_and_cycles_or_executable_expressions():
    p = profile()
    p["calculations"]["second"] = {"op": "add", "args": [{"calculation": "row_total"}, {"item": "200"}]}
    assert prepare_payroll(source(values()), p, context()).rows[0].calculations["second"] == Decimal("100.29")
    p["calculations"]["row_total"] = {"calculation": "second"}
    with pytest.raises(ValueError):
        load_numbered_profile(json.dumps(p))
    p = profile()
    p["calculations"]["row_total"] = {"op": "eval", "expression": "__import__('os')"}
    with pytest.raises(ValueError):
        load_numbered_profile(json.dumps(p))


def test_identifier_columns_cannot_be_used_as_money_or_control_values():
    p = profile()
    p["items"]["100"]["column"] = "oic"
    with pytest.raises(ValueError):
        load_numbered_profile(json.dumps(p))
    p = profile()
    p["items"]["190"]["column"] = "rc"
    with pytest.raises(ValueError):
        load_numbered_profile(json.dumps(p))


@pytest.mark.parametrize("rows", [
    [values(), values(internal_number="10", rc="910101/1234")],
    [values(), values(internal_number="10", oic="0987654321")],
    [values(), values(internal_number="10", rc=""), values(internal_number="20", oic=""),
     values(internal_number="30", oic="0987654321")],
])
def test_conflicting_identity_component_never_gets_guessed_primary(rows):
    result = prepare_payroll(source(*rows), profile(), context())
    assert all(r.primary_pp is None and r.person_group is None for r in result.rows)
    assert {i.row for i in result.issues if i.code == "identity_conflict"} == {r.number for r in result.rows}
    serialized = json.dumps(result.safe_report()) + repr(result)
    for row in rows:
        for key in ["oic", "rc"]:
            if row[key]:
                assert row[key] not in serialized


def test_rc_only_and_mixed_identifier_completeness_are_supported_without_cross_person_merges():
    rows = [values(oic="", rc=RC), values(internal_number="10", oic="", rc=RC.replace("/", "")),
            values(internal_number="30", oic="0987654321", rc="")]
    result = prepare_payroll(source(*rows), profile(), context())
    assert not result.issues
    assert result.rows[0].person_group == result.rows[1].person_group != result.rows[2].person_group
    assert [r.primary_pp for r in result.rows] == [True, False, True]


def test_consistent_oic_rc_bridge_and_primary_recomputed_for_next_period():
    result = prepare_payroll(source(values(internal_number="10"), values(oic=""),
                                    values(internal_number="30", rc="")), profile(), context())
    assert not result.issues
    assert len({r.person_group for r in result.rows}) == 1
    assert [r.primary_pp for r in result.rows] == [False, True, False]
    following = prepare_payroll(source(values(internal_number="10", period="26-10"),
                                        values(internal_number="30", period="26-10", rc="")), profile(), context("26-10", 2))
    assert not following.issues
    assert [r.primary_pp for r in following.rows] == [True, False]


@pytest.mark.parametrize("overrides,code", [({"oic": "", "rc": ""}, "missing_identity"),
                                          ({"oic": "bad"}, "identity_format"),
                                          ({"internal_number": "PP1"}, "invalid_internal_number")])
def test_identity_missing_or_invalid_blocks_linked_group(overrides, code):
    result = prepare_payroll(source(values(**overrides)), profile(), context())
    assert any(i.code == code for i in result.issues)
    assert result.rows[0].primary_pp is None


def test_primary_uses_numeric_text_order_and_refuses_equal_numeric_minima():
    result = prepare_payroll(source(values(internal_number="00010"), values(internal_number="2")), profile(), context())
    assert [r.primary_pp for r in result.rows] == [False, True]
    ambiguous = prepare_payroll(source(values(internal_number="001"), values(internal_number="1")), profile(), context())
    assert any(i.code == "ambiguous_primary" for i in ambiguous.issues)
    assert all(r.primary_pp is None for r in ambiguous.rows)
    duplicate = prepare_payroll(source(values(), values()), profile(), context())
    assert all(r.primary_pp is None for r in duplicate.rows)


def test_numeric_xlsx_identifier_is_not_used_for_pairing():
    row = values()
    table = SourceTable(tuple(row), (SourceRow(2, row, frozenset({"oic"})),))
    result = prepare_payroll(table, profile(), context())
    assert any(i.code == "numeric_identifier" for i in result.issues)
    assert result.rows[0].primary_pp is None


def test_period_policy_changes_and_revision_registry_do_not_create_or_store_guids(tmp_path):
    assert Period.parse("26-09") == Period.parse("2026-09")
    assert Period.parse("26-09", 1900) == Period(1926, 9)
    result = prepare_payroll(source(values(period="26-10")), profile(), context())
    assert any(i.code == "period_mismatch" for i in result.issues)
    db_path = tmp_path / "history.sqlite3"
    registry = RevisionRegistry(db_path)
    fingerprint = hashlib.sha256(b"synthetic definitions").hexdigest()
    registry.record("employer_a", context(), fingerprint)
    registry.record("employer_a", context(revision=1), fingerprint)
    for revision in [0, 1, 3]:
        with pytest.raises(ValueError):
            registry.record("employer_a", context(revision=revision), fingerprint)
    registry.record("employer_a", context("26-10"), fingerprint)
    registry.record("employer_b", context(), fingerprint)
    with sqlite3.connect(db_path) as db:
        dump = "\n".join(db.iterdump())
        assert len(db.execute("SELECT * FROM revisions").fetchall()) == 4
    assert OIC not in dump and RC not in dump and "guid" not in dump.lower()
    for invalid in [-1, True, 1.5]:
        with pytest.raises(ValueError):
            SubmissionContext(Period(2026, 9), invalid)


def test_installed_packages_are_pinned_immutable_and_preserve_older_versions(tmp_path):
    first, second, collision = [tmp_path / n for n in ["first.zip", "second.zip", "collision.zip"]]
    pin = build_package(profile(), first, "payroll", "1.0")["manifest_sha256"]
    installed = install_package(first, tmp_path / "store", pin)
    assert installed.profile == profile()
    assert install_package(first, tmp_path / "store", pin).directory == installed.directory
    changed = profile()
    changed["profile_version"] = "2.0"
    pin2 = build_package(changed, second, "payroll", "2.0")["manifest_sha256"]
    installed2 = install_package(second, tmp_path / "store", pin2)
    assert installed.directory.exists() and installed2.directory.exists()
    conflicting_pin = build_package(changed, collision, "payroll", "1.0")["manifest_sha256"]
    with pytest.raises(ValueError):
        install_package(collision, tmp_path / "store", conflicting_pin)
    assert load_package(installed.directory, pin).profile == profile()
    with pytest.raises(ValueError):
        install_package(first, tmp_path / "unapproved", "0" * 64)
    assert not (tmp_path / "unapproved").exists()


def rewrite_zip(path, mutate):
    with ZipFile(path) as z:
        files = {n: z.read(n) for n in z.namelist()}
    mutate(files)
    data = BytesIO()
    with ZipFile(data, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    path.write_bytes(data.getvalue())


def test_package_tampering_extra_code_and_unsupported_logic_are_rejected(tmp_path):
    path = tmp_path / "definitions.zip"
    pin = build_package(profile(), path, "payroll", "1")["manifest_sha256"]
    rewrite_zip(path, lambda f: f.update({"surprise.py": b"raise Exception('never execute')"}))
    with pytest.raises(ValueError):
        install_package(path, tmp_path / "store", pin)
    assert not (tmp_path / "store").exists()
    path2 = tmp_path / "logic.zip"
    build_package(profile(), path2, "payroll", "2")
    def future_logic(files):
        manifest = json.loads(files["manifest.json"])
        manifest["logic_api"] = 2
        files["manifest.json"] = canonical_json(manifest)
    rewrite_zip(path2, future_logic)
    with ZipFile(path2) as z:
        pin2 = hashlib.sha256(z.read("manifest.json")).hexdigest()
    with pytest.raises(ValueError):
        install_package(path2, tmp_path / "store", pin2)
    path3 = tmp_path / "valid.zip"
    pin3 = build_package(profile(), path3, "payroll", "3")["manifest_sha256"]
    installed = install_package(path3, tmp_path / "store", pin3)
    (installed.directory / "profiles/numbered.json").write_text("{}")
    with pytest.raises(ValueError):
        load_package(installed.directory, pin3)
    with pytest.raises(ValueError):
        _ = installed.profile


@pytest.mark.parametrize("name", ["../escape.json", "profiles/../escape.json", "C:/escape.json", "profiles/CON.json"])
def test_package_rejects_unsafe_archive_paths_before_writing(tmp_path, name):
    path = tmp_path / "unsafe.zip"
    pin = build_package(profile(), path, "payroll", "1")["manifest_sha256"]
    rewrite_zip(path, lambda f: f.update({name: b"{}"}))
    with pytest.raises(ValueError):
        install_package(path, tmp_path / "store", pin)
    assert not (tmp_path / "store").exists()


def test_profile_duplicate_json_keys_unknown_controls_and_long_precision_are_rejected():
    text = json.dumps(profile()).replace('"format_version": 1', '"format_version": 1, "format_version": 1')
    with pytest.raises(ValueError):
        load_numbered_profile(text)
    p = profile()
    p["controls"][0]["item"] = []
    with pytest.raises(ValueError):
        load_numbered_profile(json.dumps(p))
    result = prepare_payroll(source(values(p100="0.123456789")), profile(), context())
    assert any(i.code == "calculation_input" for i in result.issues)


@pytest.mark.parametrize("year", [2026, 2027])
def test_external_package_and_numbered_items_feed_existing_jiny_prijem_with_primary_flags(tmp_path, year):
    conversion = json.loads((ROOT / "config/conversion/jiny-prijem-{}.json".format(year)).read_text(encoding="utf-8"))
    bindings = json.loads((ROOT / "config/payroll/jiny-prijem-2027.bindings.json").read_text())
    if year == 2026:
        del bindings["tax_income_10555"]
    package_path = tmp_path / "full.zip"
    pin = build_package(profile(), package_path, "with-xsd", "1", ROOT / "schemas/official", conversion, bindings)["manifest_sha256"]
    installed = install_package(package_path, tmp_path / "store", pin)
    period = "{}-09".format(year)
    rows = source(values(internal_number="10", period=period, p100="100", p110="10", p120="5", p190="105"),
                  values(internal_number="0002", period=period, id_ppv="2", form_id="00000000-0000-4000-8000-000000000002", p100="200", p110="0", p120="0", p190="200"))
    header = {"submission_id": "00000000-0000-4000-8000-000000000003", "employer_variable_symbol": "0000000000", "year": year, "month": 9, "filled_at": "2026-10-30T12:00:00"}
    result = prepare_numbered_conversion(rows, installed.profile, context(period, 1), conversion, bindings, header, installed.directory / "schemas/official")
    assert not result.payroll.issues and result.conversion.xsd_valid
    assert result.conversion.submission_ready is False
    root = etree.fromstring(result.conversion.draft_xml)
    assert root.xpath("//*[local-name()='primarniPpv']/text()") == ["false", "true"]
    assert root.xpath("string(/*/*[local-name()='hlavicka']/*[local-name()='typPodani'])") == "R"
    assert root.xpath("string(/*/*[local-name()='hlavicka']/*[local-name()='idPodani'])") == header["submission_id"]


def test_safe_cli_diagnostics_and_explicit_revision_recording(tmp_path):
    row = values(oic=OIC, rc="910101/1234")
    csv = tmp_path / "synthetic.csv"
    csv.write_text(";".join(row) + "\n" + ";".join(row.values()) + "\n", encoding="utf-8")
    p = tmp_path / "profile.json"
    p.write_text(json.dumps(profile()), encoding="utf-8")
    command = [sys.executable, "-m", "app.core.payroll", str(csv), "--profile", str(p), "--period", "26-09", "--revision", "0", "--record-revision", str(tmp_path / "jobs.sqlite3"), "--scope", "employer_a"]
    completed = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert OIC not in completed.stdout + completed.stderr and row["rc"] not in completed.stdout + completed.stderr
    assert json.loads(completed.stdout)["internal_revision"] == 0
    repeated = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True)
    assert repeated.returncode == 2
    assert OIC not in repeated.stderr and row["rc"] not in repeated.stderr


def test_cli_uses_external_xsd_package_for_a_draft_but_never_final_export(tmp_path):
    from app.core.conversion import export_final, FinalExportBlocked
    package_path = tmp_path / "package.zip"
    conversion = json.loads((ROOT / "config/conversion/jiny-prijem-2027.json").read_text())
    bindings = json.loads((ROOT / "config/payroll/jiny-prijem-2027.bindings.json").read_text())
    pin = build_package(profile(), package_path, "working", "1", ROOT / "schemas/official", conversion, bindings)["manifest_sha256"]
    installed = install_package(package_path, tmp_path / "store", pin)
    row = values(period="27-09", p100="100", p110="10", p120="5", p190="105")
    csv = tmp_path / "synthetic.csv"
    csv.write_text(";".join(row) + "\n" + ";".join(row.values()) + "\n", encoding="utf-8")
    params = tmp_path / "params.json"
    params.write_text(json.dumps({"submission_id": "00000000-0000-4000-8000-000000000002", "employer_variable_symbol": "0000000000", "year": 2027, "month": 9, "filled_at": "2026-10-30T12:00:00"}))
    draft = tmp_path / "output.draft.xml"
    completed = subprocess.run([sys.executable, "-m", "app.core.payroll", str(csv), "--package", str(installed.directory),
        "--trusted-manifest-sha256", pin, "--period", "27-09", "--revision", "0", "--parameters", str(params), "--draft-output", str(draft)],
        cwd=str(ROOT), capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["xsd_valid"] and report["submission_ready"] is False
    assert draft.exists() and OIC not in completed.stdout + completed.stderr and RC not in completed.stdout + completed.stderr
    with pytest.raises(FinalExportBlocked):
        export_final(None, tmp_path / "final.xml")
    assert not (tmp_path / "final.xml").exists()
