from io import BytesIO
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys
from zipfile import ZipFile, ZipInfo

from lxml import etree
from openpyxl import Workbook
import pytest

from app.definitions.archives import extract_zip, zip_inventory
from app.definitions.catalog import register, verify
from app.definitions.intake import normalize_uploads, unpack_archives
from app.definitions.library import DefinitionLibrary
from app.definitions.workbooks import record_changes, table_records
from app.xml.bundle import BundleValidator

OFFICIAL = Path(__file__).parents[1] / "schemas/official"


def archive(members):
    stream = BytesIO()
    with ZipFile(stream, "w") as zipped:
        for name, content in members:
            zipped.writestr(name, content)
    return stream.getvalue()


@pytest.mark.parametrize("name", ["../escape.xsd", "/absolute.xsd", "C:/evil", "a\\evil", "CON.txt", "file:stream", "dir/../../x"])
def test_zip_escape_is_rejected_before_writing(tmp_path, name):
    with pytest.raises(ValueError):
        extract_zip(archive([("good.xsd", "synthetic"), (name, "bad")]), tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_zip_symlink_case_collision_and_directory_collision(tmp_path):
    link = ZipInfo("link.xsd")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    for members in [[(link, "../secret")], [("A.xsd", "a"), ("a.xsd", "b")], [("a", "x"), ("a/b", "y")]]:
        with pytest.raises(ValueError):
            extract_zip(archive(members), tmp_path / "out")
        assert not (tmp_path / "out").exists()


def test_zip_limits_and_normalization_collision(tmp_path, monkeypatch):
    import app.definitions.archives as archives
    monkeypatch.setattr(archives, "MAX_EXPANDED_BYTES", 10)
    with pytest.raises(ValueError, match="limit"):
        extract_zip(archive([("large", "x" * 11)]), tmp_path / "out")
    assert not (tmp_path / "out").exists()
    root = tmp_path / "official"
    (root / "2026").mkdir(parents=True)
    first = root / "2026/https___developers.mpsv.cz_assets_documents_00000000-0000-4000-8000-000000000001_A B.pdf"
    second = first.with_name(first.name.replace("A B", "A_B"))
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    with pytest.raises(ValueError, match="přepsala"):
        normalize_uploads(root)
    assert first.read_bytes() == b"one" and second.read_bytes() == b"two"


def test_unpack_rejects_tampered_source_and_escape_metadata(tmp_path):
    root = tmp_path / "official"
    (root / "2026").mkdir(parents=True)
    p = root / "2026/test.zip"
    content = archive([("test.xsd", "synthetic")])
    p.write_bytes(content)
    record = {"file": "2026/test.zip", "source_url": "https://example.invalid/test.zip", "sha256": "bad"}
    (root / "intake.json").write_text(json.dumps({"documents": [record]}))
    with pytest.raises(ValueError):
        unpack_archives(root, tmp_path / "staging")
    assert not (tmp_path / "staging").exists()


def test_normalization_preserves_source_hash_and_nested_schema_paths(tmp_path):
    root = tmp_path / "official"
    (root / "2027").mkdir(parents=True)
    nested = archive([("externi_xsd/root.xsd", '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>')])
    content = archive([("bundle_xsd.zip", nested), ("documentation.html", "not executed")])
    path = root / "2027/https___developers.mpsv.cz_assets_documents_00000000-0000-4000-8000-000000000001_Žluťoučký balíček.zip"
    path.write_bytes(content)
    records = normalize_uploads(root)
    record = records["documents"][0]
    assert record["original_path"] == path.relative_to(root).as_posix()
    assert record["file"] == "2027/zlutoucky-balicek.zip"
    assert record["origin_status"] == "unverified"
    assert record["sha256"] == hashlib.sha256(content).hexdigest()
    assert "%C5%BD" in record["source_url"]
    assert normalize_uploads(root) == records
    published = unpack_archives(root, tmp_path / "stage")
    assert len(published) == 2
    schema = next(r for r in published if r["file"].endswith("root.xsd"))
    assert schema["container_chain"] == ["bundle_xsd.zip", "externi_xsd/root.xsd"]
    assert (root / schema["file"]).exists()
    assert unpack_archives(root, tmp_path / "stage") == published


def test_xlsx_and_zip_catalog_do_not_claim_content_validation(tmp_path):
    book = Workbook()
    sheet = book.active
    sheet.title = "SLOVNÍK"
    sheet.append(["ID", "XML", "Rule"])
    sheet.append([10001, "hlavicka.idPodani", "=1+2"])
    path = tmp_path / "dictionary.xlsx"
    book.save(path)
    original = path.read_bytes()
    library = DefinitionLibrary(tmp_path / "library.sqlite3")
    id_ = library.import_document(path, "https://example.invalid/dictionary.xlsx", "synthetic-1", "data_dictionary")
    entry = library.get(id_)
    assert entry.artifact.technical_status == "xlsx_read_not_validated"
    assert entry.artifact.status == "unverified"
    assert entry.snapshot["sheets"]["SLOVNÍK"]["formulas_retained_not_executed"] == 1
    records = table_records(path.read_bytes(), "SLOVNÍK", 1)
    assert records["10001"]["fields"]["Rule"]["value"] == "=1+2"
    assert records["10001"]["fields"]["Rule"]["formula"]
    assert path.read_bytes() == original
    shifted = json.loads(json.dumps(records))
    shifted["10001"]["row"] = 9
    assert not record_changes(records, shifted)["changed"]
    zipped = tmp_path / "original.zip"
    zipped.write_bytes(archive([("dictionary.xlsx", original)]))
    record = register(tmp_path, zipped, "https://example.invalid/original.zip", "synthetic-1", "archive")
    assert record["technical_status"] == "zip_crc_checked"
    assert record["origin_review"]["status"] == "unverified"
    assert verify(tmp_path) == []
    ui_library = DefinitionLibrary(tmp_path / "gui.sqlite3")
    assert ui_library.import_catalog(tmp_path) == 1
    assert ui_library.list_definitions()[0].artifact.status == "unverified"
    assert ui_library.import_catalog(tmp_path) == 1
    assert len(ui_library.list_definitions()) == 1


def synthetic_header_xml(bundle):
    # Generated TEST data, schema-valid only, no payroll or methodological completeness claim.
    ns = bundle["namespace"]
    root = etree.Element(f"{{{ns}}}jmhz", nsmap={None: ns})
    head = etree.SubElement(root, f"{{{ns}}}hlavicka")
    for name, value in [("idPodani", "00000000-0000-4000-8000-000000000001"), ("typPodani", "R"),
                        ("variabilniSymbol", "0000000000"), ("mesic", "1"), ("rok", bundle["cohort_label"]),
                        ("datumVyplneni", "2026-10-30T12:00:00")]:
        etree.SubElement(head, f"{{{ns}}}{name}").text = value
    return etree.tostring(root)


def official_bundles():
    return json.loads((OFFICIAL / "bundles.json").read_text())["bundles"]


@pytest.mark.parametrize("cohort", ["2026", "2027"])
def test_actual_bundle_validates_generated_xml_and_rejects_changes(tmp_path, cohort):
    bundle = next(b for b in official_bundles() if b["cohort_label"] == cohort)
    validator = BundleValidator(OFFICIAL / bundle["entry"], OFFICIAL / bundle["root"], bundle["compiled_dependencies"])
    xml = synthetic_header_xml(bundle)
    result = validator.validate(xml)
    assert result.xsd_valid
    assert not result.submission_ready
    assert result.methodological_validation == "not_implemented"
    assert result.official_origin == "unverified"
    assert not validator.validate(xml.replace(b"<mesic>1</mesic>", b"<mesic>13</mesic>")).xsd_valid
    other = next(b for b in official_bundles() if b["cohort_label"] != cohort)
    assert not validator.validate(synthetic_header_xml(other)).xsd_valid
    assert not validator.validate(b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>').xsd_valid
    target = tmp_path / "synthetic.xml"
    target.write_bytes(xml)
    completed = subprocess.run([sys.executable, "-m", "app.xml", str(target), "--schema", str(OFFICIAL / bundle["entry"]),
                                "--bundle-root", str(OFFICIAL / bundle["root"]), "--manifest", str(OFFICIAL / "manifest.json")], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["xsd_valid"] is True


@pytest.mark.parametrize("location", ["../outside.xsd", "https://example.invalid/remote.xsd", "file:///etc/passwd"])
def test_resolver_blocks_external_locations(tmp_path, location):
    root = tmp_path / "bundle"
    root.mkdir()
    (tmp_path / "outside.xsd").write_text('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>')
    entry = root / "root.xsd"
    entry.write_text(f'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:include schemaLocation="{location}"/></xs:schema>')
    with pytest.raises((ValueError, etree.XMLSchemaParseError)):
        BundleValidator(entry, root)


def test_resolver_rejects_tampered_dependency_and_imported_dtd(tmp_path):
    root = tmp_path
    entry = root / "root.xsd"
    dependency = root / "types.xsd"
    entry.write_text('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:include schemaLocation="types.xsd"/></xs:schema>')
    dependency.write_text('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>')
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [entry, dependency]}
    assert BundleValidator(entry, root, hashes)
    dependency.write_text('<!DOCTYPE schema><xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>')
    with pytest.raises((ValueError, etree.XMLSchemaParseError)):
        BundleValidator(entry, root, hashes)
    with pytest.raises((ValueError, etree.XMLSchemaParseError)):
        BundleValidator(entry, root)


def test_delivered_documents_registered_without_mutating_originals():
    intake = json.loads((OFFICIAL / "intake.json").read_text())["documents"]
    manifest = json.loads((OFFICIAL / "manifest.json").read_text())["documents"]
    by_file = {d["file"]: d for d in manifest}
    assert len(intake) == 13
    for record in intake:
        assert hashlib.sha256((OFFICIAL / record["file"]).read_bytes()).hexdigest() == record["sha256"]
        assert by_file[record["file"]]["sha256"] == record["sha256"]
        assert by_file[record["file"]]["origin_review"]["status"] == "unverified"
    extracted = json.loads((OFFICIAL / "extraction.json").read_text())["published"]
    for record in extracted:
        assert by_file[record["file"]]["sha256"] == record["sha256"]
    assert verify(OFFICIAL) == []
    inventory = json.loads((OFFICIAL / "analysis/inventory.json").read_text())["documents"]
    instructions = next(d for d in inventory if d["file"].endswith("hlaseni-1.5.pdf"))
    assert instructions["effective_from"] == "2027-01-01"
    assert instructions["effective_evidence"].startswith("PDF strana 1")
    assert all(b["effective_from"] is None for b in official_bundles())  # not inferred from folders
