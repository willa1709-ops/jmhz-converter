"""Verzované adaptéry jediného výslovně zvoleného scénáře jinyPrijem."""
from __future__ import annotations

from lxml import etree


def build_xml(bundle: dict, records, header: dict) -> bytes:
    modern = bundle["id"] == "jmhz-1.5.0.3"
    podani = bundle["namespace"]
    form = "http://schemas.cssz.cz/JMHZ/form/2027" if modern else "http://schemas.cssz.cz/JMHZ/form/1.0"
    root = etree.Element("{" + podani + "}jmhz", nsmap={None: podani, "form": form})
    root.set("verze", bundle["xsd_attribute_version"])
    root.addprevious(etree.Comment("WORKING DRAFT - XSD validation does not mean ready for submission"))

    def child(parent, ns, name, value=None):
        node = etree.SubElement(parent, "{" + ns + "}" + name)
        if value is not None:
            node.text = value
        return node

    h = child(root, podani, "hlavicka")
    for name, value in [("idPodani", header["submission_id"]), ("typPodani", "R"),
                        ("variabilniSymbol", header["employer_variable_symbol"]), ("mesic", str(int(header["month"]))),
                        ("rok", header["year"]), ("datumVyplneni", header["filled_at"])]:
        child(h, podani, name, value)
    if not records:
        return etree.tostring(root.getroottree(), encoding="UTF-8", xml_declaration=True, pretty_print=True)
    container = child(root, podani, "formulareZamestnani" if modern else "formulareOsob")
    for _, record in records:
        ns = form if modern else podani
        wrapper = child(container, ns, "formularZamestnani" if modern else "formularOsoby")
        fh = child(wrapper, ns, "hlavicka")
        child(fh, ns, "idFormulare", record["form_id"])
        child(fh, ns, "typFormulare", "R")
        if "primary_pp" in record:
            child(fh, ns, "primarniPpv", "true" if record["primary_pp"] else "false")
        payload = child(wrapper, form, "jinyPrijem")
        identity = child(payload, form, "identifikace")
        child(identity, form, "ikMpsv", record["ik_mpsv"])
        child(identity, form, "idPpv", record["id_ppv"])
        income = child(payload, form, "prijem")
        tax = child(income, form, "dan")
        child(tax, form, "prijem" if modern else "zakladDane", record["tax_income_10535"])
        if modern:
            child(tax, form, "prijemPar6", record["tax_income_10555"])
    return etree.tostring(root.getroottree(), encoding="UTF-8", xml_declaration=True, pretty_print=True)
