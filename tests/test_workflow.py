from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.calculations import decimal_value, total
from app.definitions import Artifact, compare_definitions
from app.importers import read_csv, read_xlsx
from app.mapping import DRAFT_VERSION, Profile, evaluate, map_dataset
from app.models import Dataset, Row, Severity
from app.storage import Store
from app.validation import validate
from app.xml import ExportBlocked, generate_final_xml, parse_local_xml, validate_local_xsd


@pytest.mark.parametrize("encoding", ["utf-8-sig", "cp1250"])
@pytest.mark.parametrize("delimiter", [";", ",", "\t", "|"])
def test_csv_encodings_delimiters(tmp_path, encoding, delimiter):
    path = tmp_path / "data.csv"
    path.write_bytes((f"employee_id{delimiter}name\n00001{delimiter}Žluťoučký\n").encode(encoding))
    data = read_csv(path)
    assert data.rows[0].values == {"employee_id": "00001", "name": "Žluťoučký"}
    assert data.rows[0].number == 2


@pytest.mark.parametrize("text", ["id;id\na;b\n", "id; \na;b\n", "id;name\na;b;c\n", "", "id;name\n"])
def test_bad_csv(tmp_path, text):
    path = tmp_path / "bad.csv"
    path.write_text(text)
    with pytest.raises(ValueError):
        read_csv(path, delimiter=";")


def test_csv_quoted_decimal_and_multiline(tmp_path):
    path = tmp_path / "quoted.csv"
    path.write_text('id,amount,note\n0001,"10,25","first\nsecond"\n0002,2.00,last\n')
    data = read_csv(path, delimiter=",")
    assert [r.number for r in data.rows] == [2, 4]
    assert decimal_value(data.rows[0].values["amount"]) == Decimal("10.25")


def test_xlsx_text_and_reject_numeric_ids_and_formulas(tmp_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["employee_id", "income"])
    sheet.append(["00001", "10,25"])
    path = tmp_path / "test.xlsx"
    workbook.save(path)
    assert read_xlsx(path).rows[0].values["employee_id"] == "00001"
    sheet["A2"] = 1
    sheet["B2"] = 10.25
    workbook.save(path)
    source = read_xlsx(path)
    assert source.rows[0].values["income"] == "10.25"
    mapped, findings = map_dataset(source, Profile.default())
    assert any(f.field == "employee_id" and f.severity == Severity.ERROR for f in findings)
    assert mapped.rows[0].values["employee_id"] == ""
    sheet["A2"] = "=1+2"
    workbook.save(path)
    with pytest.raises(ValueError, match="vzorce"):
        read_xlsx(path)


def test_numeric_xlsx_id_cannot_be_hidden_in_mapping(tmp_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["export_id", "amount"])
    sheet.append([1, 0.1])
    path = tmp_path / "data.xlsx"
    workbook.save(path)
    profile = Profile("draft", DRAFT_VERSION, {
        "employee_id": {"op": "concat", "args": [{"op": "constant", "value": "000"}, {"op": "column", "name": "export_id"}]},
        "income": {"op": "column", "name": "amount"},
    })
    mapped, findings = map_dataset(read_xlsx(path), profile)
    assert mapped.rows[0].values["income"] == "0.1"
    assert any(f.field == "employee_id" for f in findings)


def test_mapping_operations_and_profile_roundtrip(tmp_path):
    column = lambda n: {"op": "column", "name": n}
    constant = lambda v: {"op": "constant", "value": v}
    add = {"op": "add", "args": [column("a"), column("b")]}
    expr = {"op": "round", "arg": add}
    assert evaluate(expr, {"a": "0,10", "b": "0.205"}) == "0.31"
    assert evaluate({"op": "concat", "args": [constant("00"), constant("1")]}, {}) == "001"
    conditional = {"op": "if_equal", "left": column("x"), "right": constant("yes"),
                   "then": constant("A"), "else": constant("B")}
    assert evaluate(conditional, {"x": "no"}) == "B"
    assert evaluate({"op": "lookup", "arg": column("x"), "table": {"yes": "A"}}, {"x": "yes"}) == "A"
    profile = Profile("example", DRAFT_VERSION, {"income": expr})
    path = tmp_path / "profile.json"
    profile.save(path)
    assert Profile.loads(path.read_text()) == profile
    with pytest.raises(ValueError):
        evaluate({"op": "eval", "value": "__import__('os')"}, {})
    with pytest.raises(ValueError):
        Profile.loads('{"name":"x"}')
    missing, errors = map_dataset(Dataset(("a",), (Row(2, {"a": "1"}),)), profile)
    assert errors[0].row == 2
    assert errors[0].severity == Severity.ERROR
    assert missing.rows[0].values["income"] == ""


def test_validation_duplicates_both_rows_and_period():
    values = {"employee_id": "001", "period": "2026-09", "income": "1.001", "social_base": "NaN"}
    data = Dataset(tuple(values), (Row(2, values), Row(3, values), Row(4, {"income": "-1", "period": "2026-13"})))
    findings = validate(data, "2026-09")
    assert {f.row for f in findings if "Duplicitní" in f.message} == {2, 3}
    assert any(f.field == "social_base" and f.row == 2 for f in findings)
    assert any(f.field == "period" and f.row == 4 for f in findings)
    assert any(f.severity == Severity.WARNING for f in findings)
    assert all(f.message and f.remedy for f in findings)


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "1e3", "1,000.00", "1 000", "", "9" * 31])
def test_invalid_amounts(bad):
    with pytest.raises(ValueError):
        decimal_value(bad)


def test_totals_exact_and_incomplete():
    rows = tuple(Row(i, {"income": v}) for i, v in enumerate(["0.1", "0,2", "", "bad"], 2))
    result = total(rows, "income")
    assert (result.value, result.missing, result.invalid) == (Decimal("0.3"), 1, 1)
    large = "9" * 27
    assert total((Row(2, {"income": large}), Row(3, {"income": "1"})), "income").value == Decimal("1" + "0" * 27)


def test_end_to_end_example():
    source = read_csv(Path(__file__).parents[1] / "config/example.csv")
    profile = Profile.loads((Path(__file__).parents[1] / "config/mapping.draft.json").read_text(encoding="utf-8"))
    mapped, findings = map_dataset(source, profile)
    assert not findings
    assert not any(f.severity == Severity.ERROR for f in validate(mapped, "2026-09"))
    assert total(mapped.rows, "income").value == Decimal("60000.30")
    with pytest.raises(ExportBlocked):
        generate_final_xml(mapped)


def test_definition_hash_diff_and_sqlite(tmp_path):
    path = tmp_path / "definition.txt"
    path.write_bytes(b"synthetic definition")
    artifact = Artifact.capture(path, "https://example.invalid/definition", "synthetic-1")
    assert artifact.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert artifact.status == "unverified"
    changes = compare_definitions({"fields": {"a": {"required": False}, "b": "text"}},
                                  {"fields": {"a": {"required": True}, "c": "decimal"}})
    assert {(c.path, c.kind) for c in changes} == {("/fields/a/required", "changed"), ("/fields/b", "removed"), ("/fields/c", "added")}
    store = Store(tmp_path / "config.sqlite3")
    profile = Profile("Robert's profile", DRAFT_VERSION, {})
    store.save_profile(profile)
    assert store.load_profile(profile.name) == profile
    store.save_artifact(artifact)
    with pytest.raises(ValueError):
        store.load_profile("absent")


def test_synthetic_xsd_validation_and_xxe_rejection():
    # Technical utility test ONLY; this schema is not JMHZ.
    xsd = b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:element name="synthetic" type="xs:decimal"/></xs:schema>'
    assert validate_local_xsd(b"<synthetic>12.50</synthetic>", xsd) == (True, ())
    valid, errors = validate_local_xsd(b"<synthetic>not a number</synthetic>", xsd)
    assert not valid and errors
    with pytest.raises(ValueError, match="DTD"):
        parse_local_xml(b'<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/passwd">]><x>&secret;</x>')
    remote = b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:include schemaLocation="https://example.invalid/schema.xsd"/></xs:schema>'
    with pytest.raises(Exception):
        validate_local_xsd(b"<synthetic/>", remote)
