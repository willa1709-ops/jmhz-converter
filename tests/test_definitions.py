import hashlib
import sqlite3

import pytest
from lxml import etree

from app.definitions.library import DefinitionLibrary, inspect_xsd
from app.xml import ExportBlocked, generate_final_xml


def schema(version=1, prefix="xs"):
    # Synthetic only, not an official JMHZ schema or data vocabulary.
    minimum = ' minOccurs="0"' if version == 1 else ''
    kind = "string" if version == 1 else "decimal"
    extra = '' if version == 1 else f'<{prefix}:element name="extra" type="{prefix}:string"/>'
    return f'''<{prefix}:schema xmlns:{prefix}="http://www.w3.org/2001/XMLSchema">
      <{prefix}:element name="synthetic"><{prefix}:complexType><{prefix}:sequence>
        <{prefix}:element name="amount" type="{prefix}:{kind}"{minimum}/>{extra}
      </{prefix}:sequence></{prefix}:complexType></{prefix}:element>
    </{prefix}:schema>'''.encode()


def test_import_retains_hash_content_metadata_and_reimport(tmp_path):
    path = tmp_path / "synthetic.xsd"
    path.write_bytes(schema())
    library = DefinitionLibrary(tmp_path / "definitions.sqlite3")
    id_ = library.import_xsd(path, "https://example.invalid/synthetic.xsd", "test-1", "2026-01-01")
    record = library.get(id_)
    assert record.artifact.sha256 == hashlib.sha256(schema()).hexdigest()
    assert record.artifact.status == "unverified"
    assert record.artifact.effective_from == "2026-01-01"
    acquired = record.artifact.acquired_at
    assert library.import_xsd(path, record.artifact.source_url, "test-1") == id_
    assert library.get(id_).artifact.acquired_at == acquired
    path.unlink()  # retained bytes do not depend on the original file
    assert library.get(id_).snapshot == {**inspect_xsd(schema()), "document_suffix": ".xsd"}
    assert record.artifact.technical_status == "standalone_xsd_valid"
    assert len(library.list_definitions()) == 1
    with pytest.raises(ExportBlocked):
        generate_final_xml(record)


def test_compare_obligation_type_and_new_element(tmp_path):
    library = DefinitionLibrary(tmp_path / "definitions.sqlite3")
    path = tmp_path / "synthetic.xsd"
    path.write_bytes(schema(1))
    first = library.import_xsd(path, "https://example.invalid/one.xsd", "one")
    path.write_bytes(schema(2))
    second = library.import_xsd(path, "https://example.invalid/two.xsd", "two")
    changes = library.compare(first, second)
    assert any(c.path.endswith("/attributes/minOccurs") and c.before == "0" and c.after == "1" for c in changes)
    assert any(c.path.endswith("/attributes/type") and c.after.endswith("}decimal") for c in changes)
    assert any(c.kind == "added" and "extra" in c.path for c in changes)
    assert library.compare(first, first) == []
    assert inspect_xsd(schema(prefix="a")) == inspect_xsd(schema(prefix="b"))


def test_enum_restrictions_and_order_are_visible():
    old = b'''<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:simpleType name="Code"><xs:restriction base="xs:string"><xs:enumeration value="A"/><xs:enumeration value="B"/></xs:restriction></xs:simpleType></xs:schema>'''
    from app.definitions import compare_definitions
    assert compare_definitions(inspect_xsd(old), inspect_xsd(old.replace(b'value="B"', b'value="C"')))


@pytest.mark.parametrize("source,version,start,end", [
    ("http://example.invalid/a", "v", None, None),
    ("https://user:pass@example.invalid/a", "v", None, None),
    ("https://example.invalid/a?token=x", "v", None, None),
    ("https://example.invalid/a", "", None, None),
    ("https://example.invalid/a", "v", "2026-02-30", None),
    ("https://example.invalid/a", "v", "2026-02-01", "2026-01-01"),
])
def test_metadata_validation(tmp_path, source, version, start, end):
    path = tmp_path / "test.xsd"
    path.write_bytes(schema())
    library = DefinitionLibrary(tmp_path / "definitions.sqlite3")
    with pytest.raises(ValueError):
        library.import_xsd(path, source, version, start, end)
    assert not library.list_definitions()


@pytest.mark.parametrize("content", [
    b"<not_a_schema/>",
    b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>',
    b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:include schemaLocation="file:///etc/passwd"/></xs:schema>',
    b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:import namespace="urn:external"/></xs:schema>',
    b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:element name="bad" type="xs:nonexistent"/></xs:schema>',
])
def test_bad_or_external_schemas_rejected_without_partial_entry(tmp_path, content):
    library = DefinitionLibrary(tmp_path / "definitions.sqlite3")
    path = tmp_path / "bad.xsd"
    path.write_bytes(content)
    with pytest.raises((ValueError, etree.XMLSyntaxError)):
        library.import_xsd(path, "https://example.invalid/bad.xsd", "v")
    assert not library.list_definitions()


def test_tamper_detection_and_missing_id(tmp_path):
    db_path = tmp_path / "definitions.sqlite3"
    library = DefinitionLibrary(db_path)
    path = tmp_path / "schema.xsd"
    path.write_bytes(schema())
    id_ = library.import_xsd(path, "https://example.invalid/schema.xsd", "v")
    with sqlite3.connect(db_path) as db:
        db.execute("UPDATE definition_library SET content=? WHERE id=?", (schema(2), id_))
    with pytest.raises(ValueError, match="hash"):
        library.get(id_)
    with pytest.raises(ValueError, match="neexistuje"):
        library.get(999)
