"""Spouštět také samostatně na Pythonu 3.8; žádný import Qt či moderních modelů."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path, PureWindowsPath
import subprocess
import sys

from lxml import etree
import pytest

from app.core.conversion import FinalExportBlocked, export_final, prepare_conversion
from app.core.input import read_csv
from app.core.mapping import integer_amount, load_profile
from app.core.models import SourceRow, SourceTable
from app.core.schemas import decode_local_schema_url, is_below, registered_validator
from app.core.resources import default_official_root
from app.core.stage_resources import stage_schemas

ROOT = Path(__file__).parents[1]
OFFICIAL = ROOT / "schemas/official"


def case(year=2027):
    profile = load_profile((ROOT / "config/conversion/jiny-prijem-{}.json".format(year)).read_text(encoding="utf-8"))
    # Synthetic test values only. Passing XSD does NOT prove actual IDs or methodology.
    values = {"form_id": "00000000-0000-4000-8000-000000000002", "period": "{}-01".format(year),
              "activity_code": "11", "ik_mpsv": "0000000000", "id_ppv": "000001",
              "tax_income_10535": "123,00", "tax_income_10555": "0"}
    header = {"submission_id": "00000000-0000-4000-8000-000000000001", "employer_variable_symbol": "0000000000",
              "year": year, "month": 1, "filled_at": "2026-10-30T12:00:00"}
    source = SourceTable(tuple(values), (SourceRow(2, values),))
    return source, profile, header


@pytest.mark.parametrize("year", [2026, 2027])
def test_real_employee_form_generation_and_official_xsd(year):
    source, profile, header = case(year)
    result = prepare_conversion(source, profile, header, OFFICIAL)
    assert result.xsd_valid and not result.issues
    assert result.totals["tax_income_10535"] == Decimal("123")
    assert result.methodological_validation == "incomplete" and not result.submission_ready
    validator = registered_validator(OFFICIAL, profile["bundle_id"])
    assert validator.validate(result.draft_xml).xsd_valid
    root = etree.fromstring(result.draft_xml)
    ns = root.nsmap[None]
    form = "http://schemas.cssz.cz/JMHZ/form/{}".format("2027" if year == 2027 else "1.0")
    assert root.get("verze") == ("1.5.0.3" if year == 2027 else "1.4.3")
    assert [etree.QName(c).localname for c in root] == ["hlavicka", "formulareZamestnani" if year == 2027 else "formulareOsob"]
    assert root.xpath("string(.//f:identifikace/f:idPpv)", namespaces={"f": form}) == "000001"
    assert root.xpath("string(.//f:jinyPrijem/f:prijem/f:dan/f:{})".format("prijem" if year == 2027 else "zakladDane"), namespaces={"f": form}) == "123"
    assert "WORKING DRAFT" in result.draft_xml.decode()
    # Schema-required submission header must not be omitted.
    root.remove(root.find("{" + ns + "}hlavicka"))
    assert not validator.validate(etree.tostring(root)).xsd_valid


@pytest.mark.parametrize("field", ["form_id", "period", "activity_code", "ik_mpsv", "id_ppv", "tax_income_10535", "tax_income_10555"])
def test_missing_values_do_not_generate_fake_zero_or_partial_xml(field):
    source, profile, header = case()
    source.rows[0].values[field] = ""
    result = prepare_conversion(source, profile, header, OFFICIAL)
    assert result.draft_xml is None and not result.xsd_valid
    assert any(i.field == field and i.code == "missing_value" and i.row == 2 for i in result.issues)


@pytest.mark.parametrize("field", ["submission_id", "employer_variable_symbol", "year", "month", "filled_at"])
def test_required_header_parameters(field):
    source, profile, header = case()
    del header[field]
    result = prepare_conversion(source, profile, header, OFFICIAL)
    assert result.draft_xml is None
    assert any(i.field == field and i.code == "missing_header" and i.row is None for i in result.issues)


@pytest.mark.parametrize("field,value,code", [("activity_code", "1", "unsupported_scenario"),
                                            ("period", "2026-01", "period_mismatch"),
                                            ("id_ppv", "9" * 23, "xsd_invalid")])
def test_unsupported_scenario_mismatched_period_and_real_xsd_length(field, value, code):
    source, profile, header = case()
    source.rows[0].values[field] = value
    result = prepare_conversion(source, profile, header, OFFICIAL)
    assert result.draft_xml is None
    assert any(i.code == code and i.row == 2 for i in result.issues)
    if field == "id_ppv":
        assert value not in " ".join(i.message for i in result.issues)


def test_profile_column_mapping_xlsx_identifier_protection_and_duplicates():
    source, profile, header = case()
    profile["columns"]["ik_mpsv"] = "payroll_identifier"
    values = dict(source.rows[0].values)
    values["payroll_identifier"] = values.pop("ik_mpsv")
    mapped = SourceTable(tuple(values), (SourceRow(2, values),))
    assert prepare_conversion(mapped, profile, header, OFFICIAL).xsd_valid
    numeric = SourceTable(tuple(values), (SourceRow(2, values, frozenset({"payroll_identifier"})),))
    assert any(i.code == "numeric_identifier" for i in prepare_conversion(numeric, profile, header, OFFICIAL).issues)
    duplicate = SourceTable(tuple(values), (SourceRow(2, values), SourceRow(3, dict(values))))
    assert any(i.code == "duplicate_source_record" and i.row == 3 for i in prepare_conversion(duplicate, profile, header, OFFICIAL).issues)


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "1e2", "1,20", "-1", "100000000000000", ""])
def test_integer_amounts_are_decimal_exact_and_never_implicitly_rounded(raw):
    with pytest.raises(ValueError):
        integer_amount(raw)


def test_explicit_zero_precision_totals_and_packet_count():
    source, profile, header = case()
    first = dict(source.rows[0].values, tax_income_10535="99999999999999")
    second = dict(first, form_id="00000000-0000-4000-8000-000000000003", id_ppv="000002", tax_income_10535="1")
    result = prepare_conversion(SourceTable(tuple(first), (SourceRow(2, first), SourceRow(3, second))), profile, header, OFFICIAL)
    assert result.xsd_valid
    assert result.totals["tax_income_10535"] == Decimal("100000000000000")
    assert result.totals["tax_income_10555"] == Decimal(0)
    oversized = SourceTable(source.columns, (source.rows[0],) * 1501)
    assert any(i.code == "packet_limit" for i in prepare_conversion(oversized, profile, header, OFFICIAL).issues)


def test_2027_xsd_requires_both_income_elements_when_dan_is_present():
    source, profile, header = case()
    result = prepare_conversion(source, profile, header, OFFICIAL)
    root = etree.fromstring(result.draft_xml)
    node = root.find(".//{http://schemas.cssz.cz/JMHZ/form/2027}prijemPar6")
    node.getparent().remove(node)
    assert not registered_validator(OFFICIAL, profile["bundle_id"]).validate(etree.tostring(root)).xsd_valid


def test_final_export_cannot_be_enabled_by_a_result_flag(tmp_path):
    source, profile, header = case()
    result = prepare_conversion(source, profile, header, OFFICIAL)
    target = tmp_path / "final.xml"
    for candidate in [result, replace(result, submission_ready=True)]:
        with pytest.raises(FinalExportBlocked):
            export_final(candidate, target)
    assert not target.exists()


def test_cli_csv_to_working_xml_and_fail_closed_output(tmp_path):
    source, profile, header = case()
    profile["columns"]["tax_income_10535"] = "příjem"
    row = dict(source.rows[0].values)
    row["příjem"] = row.pop("tax_income_10535")
    csv = tmp_path / "synthetic.csv"
    csv.write_bytes((";".join(row) + "\n" + ";".join(row.values()) + "\n").encode("cp1250"))
    assert read_csv(csv).rows[0].values["id_ppv"] == "000001"
    profile_path, params_path = tmp_path / "profile.json", tmp_path / "parameters.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    params_path.write_text(json.dumps(header), encoding="utf-8")
    output = tmp_path / "synthetic.draft.xml"
    command = [sys.executable, "-m", "app.core", str(csv), "--profile", str(profile_path), "--parameters", str(params_path),
               "--official-root", str(OFFICIAL), "--draft-output", str(output)]
    process = subprocess.run(command, capture_output=True, text=True, cwd=str(ROOT))
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout)["submission_ready"] is False
    assert "000000000002" not in process.stdout
    data = output.read_bytes()
    assert registered_validator(OFFICIAL, profile["bundle_id"]).validate(data).xsd_valid
    assert subprocess.run(command, capture_output=True, cwd=str(ROOT)).returncode == 2
    assert output.read_bytes() == data
    command[-1] = str(tmp_path / "final.xml")
    assert subprocess.run(command, capture_output=True, cwd=str(ROOT)).returncode == 2
    assert not (tmp_path / "final.xml").exists()


def test_core_import_is_independent_of_qt_and_modern_strenum_models():
    code = "import sys; import app.core.conversion; assert 'app.models' not in sys.modules; assert not any(x.startswith(('PySide6','PySide2')) for x in sys.modules)"
    assert subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), capture_output=True).returncode == 0


def test_windows_file_uri_decoding_and_boundary_without_a_windows_host():
    assert decode_local_schema_url("file:///C:/JMHZ%20Data/typy.xsd", windows=True) == "C:\\JMHZ Data\\typy.xsd"
    assert decode_local_schema_url("C:\\JMHZ\\types.xsd", windows=True) == "C:\\JMHZ\\types.xsd"
    assert is_below(PureWindowsPath("C:/data/schema.xsd"), PureWindowsPath("C:/data"))
    assert not is_below(PureWindowsPath("C:/outside/schema.xsd"), PureWindowsPath("C:/data"))
    for url in ["https://example.invalid/types.xsd", "file://server/share/types.xsd", "\\\\server\\share\\types.xsd",
                "file:////server/share/types.xsd", "%5C%5Cserver%5Cshare%5Ctypes.xsd"]:
        with pytest.raises(ValueError):
            decode_local_schema_url(url, windows=True)


def test_shared_xlsx_reader_converts_without_modern_models(tmp_path):
    from openpyxl import Workbook
    from app.core.input import read_xlsx
    source, profile, header = case()
    book = Workbook()
    sheet = book.active
    sheet.append(list(source.columns))
    values = dict(source.rows[0].values, tax_income_10535=123)
    sheet.append([values[c] for c in source.columns])
    path = tmp_path / "synthetic.xlsx"
    book.save(path)
    table = read_xlsx(path)
    result = prepare_conversion(table, profile, header, OFFICIAL)
    assert result.xsd_valid and result.totals["tax_income_10535"] == Decimal(123)
    profile_file, params_file = tmp_path / "profile.json", tmp_path / "params.json"
    profile_file.write_text(json.dumps(profile), encoding="utf-8")
    params_file.write_text(json.dumps(header), encoding="utf-8")
    command = [sys.executable, "-m", "app.core", str(path), "--profile", str(profile_file), "--parameters", str(params_file), "--official-root", str(OFFICIAL)]
    assert subprocess.run(command, cwd=str(ROOT), capture_output=True).returncode == 0
    sheet.cell(2, list(source.columns).index("ik_mpsv") + 1, 1)
    book.save(path)
    assert any(i.code == "numeric_identifier" for i in prepare_conversion(read_xlsx(path), profile, header, OFFICIAL).issues)


def test_resource_lookup_is_independent_of_cwd_and_supports_frozen_layout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert default_official_root() == OFFICIAL
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert default_official_root() == tmp_path / "schemas" / "official"


def test_malformed_profile_and_unknown_header_options_are_not_silently_ignored():
    source, profile, header = case()
    invalid = dict(profile, bundle_id=[])
    with pytest.raises(ValueError):
        load_profile(json.dumps(invalid))
    header["typPodani"] = "O"
    result = prepare_conversion(source, profile, header, OFFICIAL)
    assert result.draft_xml is None
    assert any(i.code == "invalid_header" for i in result.issues)


def test_staged_runtime_is_self_contained_and_generates_both_versions(tmp_path):
    destination = tmp_path / "runtime" / "schemas" / "official"
    stage_schemas(OFFICIAL, destination)
    files = list(destination.rglob("*"))
    assert all(p.suffix in {".json", ".xsd"} for p in files if p.is_file())
    for year in [2026, 2027]:
        source, profile, header = case(year)
        result = prepare_conversion(source, profile, header, destination)
        assert result.xsd_valid and not result.submission_ready
    with pytest.raises(ValueError):
        stage_schemas(OFFICIAL, destination)


def test_resource_staging_rejects_roundtrip_traversal_in_manifest(tmp_path):
    import hashlib
    source = tmp_path / "official"
    source.mkdir()
    content = b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>'
    (source / "schema.xsd").write_bytes(content)
    # Resolves back inside the SOURCE, but is not safe relative to another destination.
    manifest = {"format_version": 1, "documents": [{"kind": "xsd", "file": "../official/schema.xsd", "sha256": hashlib.sha256(content).hexdigest()}]}
    (source / "manifest.json").write_text(json.dumps(manifest))
    destination = tmp_path / "runtime" / "official"
    with pytest.raises(ValueError):
        stage_schemas(source, destination)
    assert not destination.exists()
