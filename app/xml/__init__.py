"""Veřejné XML API; finální mzdový export zůstává blokovaný."""
from app.core.xml_support import NoExternalResources, parse_local_xml, validate_local_xsd


class ExportBlocked(ValueError):
    pass


def generate_final_xml(*args: object, **kwargs: object) -> bytes:
    raise ExportBlocked("Export zablokován: metodická pravidla, původ a účinnost sad nejsou ověřeny.")
