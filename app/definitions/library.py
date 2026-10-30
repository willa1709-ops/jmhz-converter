"""Ruční evidence XSD, číselníků a metodiky; původ a technický stav jsou oddělené."""
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit

from lxml import etree

from app.definitions import Artifact, Change, compare_definitions
from app.xml import parse_local_xml

XSD = "http://www.w3.org/2001/XMLSchema"
MAX_SCHEMA_BYTES = 5 * 1024 * 1024


def inspect_xsd(content: bytes, allow_dependencies: bool = False) -> dict:
    """Normalizovaný strukturální přehled XSD 1.0, nikoliv metodická analýza.

    Kompozice schémat čeká na lokální balíčkový resolver. Žádné externí čtení.
    """
    if len(content) > MAX_SCHEMA_BYTES:
        raise ValueError("XSD překračuje limit 5 MiB.")
    root = parse_local_xml(content)
    if root.tag != f"{{{XSD}}}schema":
        raise ValueError("Soubor není XSD schéma.")
    dependencies = root.xpath(".//xs:include | .//xs:import | .//xs:redefine | .//xs:override", namespaces={"xs": XSD})
    if dependencies and not allow_dependencies:
        raise ValueError("Import zatím podporuje pouze samostatné XSD bez include/import/redefine/override.")
    if sum(1 for _ in root.iter()) > 50_000:
        raise ValueError("Schéma obsahuje příliš mnoho uzlů.")
    if not dependencies:
        try:
            etree.XMLSchema(root)
        except etree.XMLSchemaParseError as exc:
            raise ValueError("Schéma není platné samostatné XSD 1.0.") from exc

    def expanded_qname(value: str, node: etree._Element) -> str:
        if ":" in value:
            prefix, name = value.split(":", 1)
            namespace = node.nsmap.get(prefix)
        else:
            name, namespace = value, node.nsmap.get(None)
        return f"{{{namespace}}}{name}" if namespace else name

    def normalized(node: etree._Element) -> dict:
        attrs = dict(node.attrib)
        for key in ("type", "ref", "base", "substitutionGroup", "itemType", "memberTypes"):
            if key in attrs:
                attrs[key] = " ".join(expanded_qname(v, node) for v in attrs[key].split())
        if node.tag in {f"{{{XSD}}}{name}" for name in ("element", "sequence", "choice", "any", "group")} and node is not root:
            attrs.setdefault("minOccurs", "1")
            attrs.setdefault("maxOccurs", "1")
        children = {}
        for child in node:
            if not isinstance(child.tag, str):
                continue
            # Stable order indexes intentionally report moves in sequence/choice.
            key = f"{len(children):04}:{etree.QName(child).localname}:{child.get('name', child.get('value', ''))}"
            children[key] = normalized(child)
        return {"tag": node.tag, "attributes": attrs, "text": (node.text or "").strip(), "children": children}

    return {"xsd_structure": normalized(root), "methodology": "not_provided"}


def inspect_document(content: bytes, kind: str, suffix: str) -> tuple[dict, str]:
    if len(content) > MAX_SCHEMA_BYTES:
        raise ValueError("Dokument překračuje limit 5 MiB.")
    if kind == "xsd":
        snapshot = inspect_xsd(content, allow_dependencies=True)
        root = parse_local_xml(content)
        dependencies = root.xpath(".//xs:include | .//xs:import | .//xs:redefine | .//xs:override", namespaces={"xs": XSD})
        return snapshot, "dependencies_unchecked" if dependencies else "standalone_xsd_valid"
    if kind == "codelist":
        import csv
        import io
        text = content.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=csv.Sniffer().sniff(text[:65536], delimiters=";,\t|").delimiter, strict=True)
        rows = list(reader)
        if len(rows) < 2 or any(len(r) != len(rows[0]) for r in rows):
            raise ValueError("Číselník CSV musí být neprázdná pravidelná tabulka.")
        if any(not h.strip() for h in rows[0]) or len(set(rows[0])) != len(rows[0]):
            raise ValueError("Hlavičky číselníku musí být jedinečné a neprázdné.")
        return {"codelist_table": {"headers": rows[0], "rows": {str(i): r for i, r in enumerate(rows[1:])}}}, "csv_parsed"
    if kind == "methodology":
        if suffix.lower() == ".pdf":
            if not content.startswith(b"%PDF-"):
                raise ValueError("Soubor nemá PDF hlavičku.")
            return {"document_sha256": hashlib.sha256(content).hexdigest(), "interpretation": "not_implemented"}, "retained_only"
        if suffix.lower() == ".json":
            value = json.loads(content.decode("utf-8-sig"))
            if not isinstance(value, dict):
                raise ValueError("Metodický JSON musí být objekt, nikoliv spustitelný kód.")
            return {"methodology_document": value, "interpretation": "not_implemented"}, "json_parsed"
        if suffix.lower() not in {".txt", ".md"}:
            raise ValueError("Metodika podporuje PDF, JSON, TXT a MD.")
        return {"methodology_text": content.decode("utf-8-sig"), "interpretation": "not_implemented"}, "text_decoded"
    raise ValueError("Neznámý typ dokumentu.")


@dataclass(frozen=True)
class StoredDefinition:
    id: int
    artifact: Artifact
    snapshot: dict


class DefinitionLibrary:
    """SQLite transakce ukládá neměnný XSD blob společně s metadaty a přehledem."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with sqlite3.connect(path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS definition_library (
                id INTEGER PRIMARY KEY, sha256 TEXT NOT NULL, version TEXT NOT NULL,
                source_url TEXT NOT NULL, metadata TEXT NOT NULL, snapshot TEXT NOT NULL,
                content BLOB NOT NULL, UNIQUE(sha256, version, source_url))""")

    def import_xsd(self, path: Path, source_url: str, version: str,
                   effective_from: str | None = None, effective_until: str | None = None) -> int:
        # Compatibility API for strictly self-contained XSD.
        with path.open("rb") as handle:
            inspect_xsd(handle.read(MAX_SCHEMA_BYTES + 1))
        return self.import_document(path, source_url, version, "xsd", effective_from, effective_until)

    def import_document(self, path: Path, source_url: str, version: str, kind: str,
                        effective_from: str | None = None, effective_until: str | None = None) -> int:
        source = urlsplit(source_url)
        if source.scheme != "https" or not source.hostname or source.username or source.password or source.query or source.fragment:
            raise ValueError("Zadejte veřejné HTTPS URL zdroje bez přihlašovacích údajů, query a fragmentu.")
        if not version.strip() or len(version) > 100:
            raise ValueError("Zadejte verzi do 100 znaků.")
        try:
            start = date.fromisoformat(effective_from) if effective_from else None
            end = date.fromisoformat(effective_until) if effective_until else None
        except ValueError as exc:
            raise ValueError("Účinnost musí mít tvar YYYY-MM-DD nebo zůstat prázdná.") from exc
        if start and end and start > end:
            raise ValueError("Účinnost od nesmí být po účinnosti do.")
        with path.open("rb") as handle:
            content = handle.read(MAX_SCHEMA_BYTES + 1)
        snapshot, technical = inspect_document(content, kind, path.suffix)
        artifact = Artifact(source_url, version.strip(), datetime.now(timezone.utc).isoformat(),
                            effective_from, effective_until, hashlib.sha256(content).hexdigest(),
                            technical_status=technical, kind=kind)
        snapshot["document_suffix"] = path.suffix.lower()
        with sqlite3.connect(self.path) as db:
            # Reimport preserves the original acquisition timestamp and metadata.
            db.execute("INSERT OR IGNORE INTO definition_library (sha256,version,source_url,metadata,snapshot,content) VALUES (?,?,?,?,?,?)",
                       (artifact.sha256, artifact.version, source_url, json.dumps(artifact.as_dict()), json.dumps(snapshot), content))
            found = db.execute("SELECT id,metadata FROM definition_library WHERE sha256=? AND version=? AND source_url=?",
                               (artifact.sha256, artifact.version, source_url)).fetchone()
            if Artifact(**json.loads(found[1])).kind != kind:
                raise ValueError("Tentýž dokument již existuje jako jiný typ; metadata nebyla přepsána.")
            return found[0]

    def list_definitions(self) -> list[StoredDefinition]:
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT id, metadata, snapshot FROM definition_library ORDER BY id").fetchall()
        return [StoredDefinition(id_, Artifact(**json.loads(metadata)), json.loads(snapshot)) for id_, metadata, snapshot in rows]

    def get(self, id_: int) -> StoredDefinition:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT metadata,snapshot,content FROM definition_library WHERE id=?", (id_,)).fetchone()
        if row is None:
            raise ValueError("Definice neexistuje.")
        artifact = Artifact(**json.loads(row[0]))
        if hashlib.sha256(row[2]).hexdigest() != artifact.sha256:
            raise ValueError("Uložený obsah neodpovídá kontrolnímu hashi.")
        # Recompute from the retained bytes; do not trust an independently edited snapshot.
        suffix = json.loads(row[1]).get("document_suffix", ".xsd")
        snapshot, _ = inspect_document(row[2], artifact.kind, suffix)
        if "document_suffix" in json.loads(row[1]):
            snapshot["document_suffix"] = suffix
        return StoredDefinition(id_, artifact, snapshot)

    def compare(self, before_id: int, after_id: int) -> list[Change]:
        before, after = self.get(before_id), self.get(after_id)
        if before.artifact.kind != after.artifact.kind:
            raise ValueError("Porovnávejte dokumenty stejného typu.")
        return compare_definitions(before.snapshot, after.snapshot)
