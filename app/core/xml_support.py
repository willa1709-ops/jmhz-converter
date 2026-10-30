from __future__ import annotations

from lxml import etree


class NoExternalResources(etree.Resolver):
    def resolve(self, url: str, public_id: str, context: object) -> object:
        raise ValueError("Externí XML zdroje nejsou povoleny.")


def parse_local_xml(content: bytes) -> etree._Element:
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True,
                             huge_tree=False, recover=False)
    parser.resolvers.add(NoExternalResources())
    root = etree.fromstring(content, parser)
    if root.getroottree().docinfo.doctype:
        raise ValueError("DTD není povoleno.")
    return root


def validate_local_xsd(xml: bytes, xsd: bytes) -> tuple[bool, tuple[str, ...]]:
    schema = etree.XMLSchema(parse_local_xml(xsd))
    valid = schema.validate(parse_local_xml(xml))
    return valid, tuple(f"Řádek {error.line}: {error.type_name}" for error in schema.error_log)
