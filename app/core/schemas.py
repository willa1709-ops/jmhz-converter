"""XSD validace uzavřeného lokálního balíčku bez síťových a externích entit."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from io import BytesIO
from pathlib import Path
import json
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname
import nturl2path
import os
import re

from lxml import etree

from app.core.xml_support import parse_local_xml


def is_below(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def decode_local_schema_url(url: str, windows: bool = False) -> str:
    if url.startswith(("\\\\", "//")):
        raise ValueError("Síťová cesta není povolena.")
    if windows and re.match(r"^[A-Za-z]:[\\/]", url):
        return url
    parsed = urlsplit(url)
    if parsed.scheme not in {"", "file"} or parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("Síťová nebo nekonkrétní XSD závislost není povolena.")
    if parsed.scheme == "file":
        decoded = nturl2path.url2pathname(parsed.path) if windows else url2pathname(parsed.path)
    else:
        decoded = unquote(parsed.path)
    if decoded.startswith(("\\\\", "//")):
        raise ValueError("Zakódovaná síťová cesta není povolena.")
    return decoded


class LocalSchemaResolver(etree.Resolver):
    def __init__(self, root: Path, expected_hashes: dict[str, str] | None = None):
        super().__init__()
        self.root = root.resolve()
        self.expected_hashes = expected_hashes
        self.loaded: dict[str, str] = {}
        self.sizes: dict[str, int] = {}

    def read(self, path: Path) -> bytes:
        path = path.resolve()
        if not is_below(path, self.root) or path.suffix.lower() != ".xsd" or not path.is_file():
            raise ValueError("XSD závislost je mimo schválený lokální balíček nebo chybí.")
        relative = path.relative_to(self.root).as_posix()
        if path.stat().st_size > 5 * 1024 * 1024 or (relative not in self.loaded and len(self.loaded) >= 512):
            raise ValueError("XSD balíček překračuje limity.")
        content = path.read_bytes()
        self.sizes[relative] = len(content)
        if sum(self.sizes.values()) > 25 * 1024 * 1024:
            raise ValueError("Součet XSD překračuje limit 25 MiB.")
        digest = hashlib.sha256(content).hexdigest()
        if self.expected_hashes is not None and self.expected_hashes.get(relative) != digest:
            raise ValueError("XSD není v manifestu nebo nesouhlasí SHA-256.")
        parse_local_xml(content)  # Reject DTD even in imported schema documents.
        self.loaded[relative] = digest
        return content

    def resolve(self, url: str, public_id: str, context: object) -> object:
        path = Path(decode_local_schema_url(url, windows=os.name == "nt"))
        if not path.is_absolute():
            path = self.root / path
        content = self.read(path)
        return self.resolve_string(content, context, base_url=path.resolve().as_uri())


@dataclass(frozen=True)
class XmlValidation:
    xsd_valid: bool
    errors: tuple[str, ...]
    methodological_validation: str = "not_implemented"
    official_origin: str = "unverified"
    submission_ready: bool = False


class BundleValidator:
    def __init__(self, entry: Path, root: Path, expected_hashes: dict[str, str] | None = None):
        self.resolver = LocalSchemaResolver(root, expected_hashes)
        content = self.resolver.read(entry)
        parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True, huge_tree=False)
        parser.resolvers.add(self.resolver)
        schema = etree.parse(BytesIO(content), parser, base_url=entry.resolve().as_uri())
        self.schema = etree.XMLSchema(schema)

    def validate(self, xml: bytes) -> XmlValidation:
        if len(xml) > 25 * 1024 * 1024:
            raise ValueError("XML překračuje limit 25 MiB.")
        try:
            root = parse_local_xml(xml)
        except (ValueError, etree.XMLSyntaxError):
            return XmlValidation(False, ("XML_PARSE_OR_DTD_ERROR",))
        valid = self.schema.validate(root)
        # Do not leak values or identifiers into logs.
        errors = tuple(f"Řádek {e.line}: {e.type_name}" for e in self.schema.error_log)
        return XmlValidation(valid, errors)


def registered_validator(official_root: Path, bundle_id: str) -> BundleValidator:
    official_root = official_root.resolve()
    bundles = json.loads((official_root / "bundles.json").read_text(encoding="utf-8"))["bundles"]
    bundle = next((b for b in bundles if b["id"] == bundle_id), None)
    if bundle is None:
        raise ValueError("Neznámý balíček. Volte výslovně, ne jen podle roku složky.")
    entry = (official_root / bundle["entry"]).resolve()
    root = (official_root / bundle["root"]).resolve()
    if not is_below(entry, official_root) or not is_below(root, official_root):
        raise ValueError("Balíček uniká z úložiště.")
    hashes = {}
    for record in json.loads((official_root / "manifest.json").read_text(encoding="utf-8"))["documents"]:
        path = (official_root / record["file"]).resolve()
        if is_below(path, root) and path.suffix == ".xsd":
            hashes[path.relative_to(root).as_posix()] = record["sha256"]
    return BundleValidator(entry, root, hashes)


class IdentityValidator(BundleValidator):
    """Validate a component using the real identifikaceType, never a guessed type.

    The inspection root is internal to the application, not a JMHZ output format.
    """

    def __init__(self, official_root: Path, bundle_id: str):
        registered = registered_validator(official_root, bundle_id)
        self.resolver = registered.resolver
        entry = self.resolver.root / "formCommonTypes.xsd"
        document = parse_local_xml(self.resolver.read(entry))
        ns = document.get("targetNamespace")
        xs = "http://www.w3.org/2001/XMLSchema"
        wrapper = etree.Element("{" + xs + "}schema", nsmap={"xs": xs, "form": ns})
        etree.SubElement(wrapper, "{" + xs + "}import", namespace=ns, schemaLocation=entry.as_uri())
        etree.SubElement(wrapper, "{" + xs + "}element", name="identity", type="form:identifikaceType")
        parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
        parser.resolvers.add(self.resolver)
        self.schema = etree.XMLSchema(etree.fromstring(etree.tostring(wrapper), parser))
        self.namespace = ns

    def alternative(self, metadata: dict) -> XmlValidation:
        root = etree.Element("identity")
        try:
            for tag, key in [("prijmeni", "surname"), ("jmeno", "given_name"), ("datumNarozeni", "birth_date"),
                             ("datumNastupu", "employment_start"), ("druhCinnosti", "activity_code")]:
                etree.SubElement(root, "{" + self.namespace + "}" + tag).text = metadata.get(key) or ""
        except (ValueError, TypeError):
            return XmlValidation(False, ("IDENTITY_FORMAT_ERROR",))
        return self.validate(etree.tostring(root))
