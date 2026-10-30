import json
from pathlib import Path
import subprocess
import sys

import pytest

from app.definitions.catalog import register, verify
from app.definitions.library import DefinitionLibrary


def test_register_and_verify_separate_origin_and_technical_validation(tmp_path):
    path = tmp_path / "synthetic.xsd"
    path.write_text('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:element name="test" type="xs:string"/></xs:schema>')
    record = register(tmp_path, path, "https://example.invalid/test.xsd", "synthetic-1", "xsd")
    assert record["technical_status"] == "standalone_xsd_valid"
    assert record["origin_review"]["status"] == "unverified"
    assert record["origin_review"]["reviewer"] is None
    assert verify(tmp_path) == []
    assert register(tmp_path, path, record["source_url"], "synthetic-1", "xsd") == record
    assert len(json.loads((tmp_path / "manifest.json").read_text())["documents"]) == 1
    path.write_text("changed")
    assert len(verify(tmp_path)) == 1
    path.unlink()
    assert len(verify(tmp_path)) == 1


def test_register_dependency_xsd_does_not_claim_full_validation(tmp_path):
    path = tmp_path / "dependency.xsd"
    path.write_text('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:include schemaLocation="https://example.invalid/not-downloaded.xsd"/></xs:schema>')
    record = register(tmp_path, path, "https://example.invalid/dependency.xsd", "synthetic-1", "xsd")
    assert record["technical_status"] == "dependencies_unchecked"
    assert record["status"] == "unverified"


def test_codelist_and_methodology_retained_and_compared_as_data(tmp_path):
    library = DefinitionLibrary(tmp_path / "library.sqlite3")
    code = tmp_path / "codes.csv"
    code.write_text("code;label\n01;Synthetic A\n", encoding="utf-8")
    old = library.import_document(code, "https://example.invalid/codes.csv", "v1", "codelist")
    code.write_text("code;label\n01;Synthetic B\n", encoding="utf-8")
    new = library.import_document(code, "https://example.invalid/codes.csv", "v2", "codelist")
    assert library.get(old).artifact.technical_status == "csv_parsed"
    assert library.compare(old, new)
    method = tmp_path / "method.json"
    method.write_text('{"synthetic_note":"__import__(not_executed)"}')
    method_id = library.import_document(method, "https://example.invalid/method.json", "v1", "methodology")
    assert library.get(method_id).artifact.technical_status == "json_parsed"
    assert library.get(method_id).snapshot["interpretation"] == "not_implemented"
    with pytest.raises(ValueError, match="stejného typu"):
        library.compare(new, method_id)
    pdf = tmp_path / "method.pdf"
    pdf.write_bytes(b"%PDF-1.7\nsynthetic placeholder, not a valid PDF document")
    pdf_id = library.import_document(pdf, "https://example.invalid/method.pdf", "v1", "methodology")
    assert library.get(pdf_id).artifact.technical_status == "retained_only"


def test_catalog_rejects_escape_and_preserves_unknown_manifest(tmp_path):
    root = tmp_path / "official"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("synthetic")
    with pytest.raises(ValueError):
        register(root, outside, "https://example.invalid/a.txt", "v", "methodology")
    link = root / "linked.txt"
    link.symlink_to(outside)
    with pytest.raises(ValueError):
        register(root, link, "https://example.invalid/a.txt", "v", "methodology")
    path = root / "inside.txt"
    path.write_text("synthetic")
    manifest = root / "manifest.json"
    manifest.write_text('{"format_version":99,"documents":[]}')
    before = manifest.read_bytes()
    with pytest.raises(ValueError):
        register(root, path, "https://example.invalid/a.txt", "v", "methodology")
    assert manifest.read_bytes() == before


def test_catalog_cli_register_and_verify(tmp_path):
    path = tmp_path / "synthetic.txt"
    path.write_text("synthetic methodology")
    base = [sys.executable, "-m", "app.definitions.catalog", "--root", str(tmp_path)]
    result = subprocess.run(base + ["register", str(path), "--source", "https://example.invalid/method.txt", "--version", "synthetic-1", "--kind", "methodology"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["technical_status"] == "text_decoded"
    assert subprocess.run(base + ["verify"], capture_output=True).returncode == 0
    path.write_text("changed")
    assert subprocess.run(base + ["verify"], capture_output=True).returncode == 1
