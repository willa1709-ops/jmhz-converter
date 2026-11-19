"""Offline DIS ProcessingResult (supplied protocol documentation v1.5).

Origin/signatures and cJMHZ completeness are NOT proved by parsing a receipt.
All source text and identifiers stay in the private organization database/UI.
"""
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from uuid import uuid5, UUID

from lxml import etree

from app.core.organizations import dumps, now
from app.core.payroll import strict_json
from app.core.xml_support import parse_local_xml

MAX_RECEIPT = 10 * 1024 * 1024
CSSZ = "http://www.cssz.cz/XMLSchema/envelope"
GOV = "http://www.govtalk.gov.uk/CM/envelope"
OUTCOMES = {"accepted_for_processing": "DIS: přijato do dalšího zpracování",
            "partially_accepted": "DIS: částečně přijato do dalšího zpracování",
            "rejected": "DIS: dílčí podání zamítnuto", "unresolved": "Výsledek vyžaduje přezkum",
            "not_interpreted": "Příloha – obsah se strojově nevyhodnocuje"}


class ReceiptError(ValueError):
    """Only static messages: never echo XML, error text, RČ or OIČ."""


def fail():
    raise ReceiptError("Protokol není v podporovaném jednoznačném formátu nebo překračuje limity.") from None


def canonical_guid(value):
    try:
        if not isinstance(value, str) or len(value) != 36 or str(UUID(value)).lower() != value.lower():
            fail()
        return str(UUID(value)).upper()
    except (ValueError, TypeError, AttributeError):
        fail()


@dataclass(frozen=True)
class ParsedReceipt:
    kind: str
    outcome: str
    private: dict = field(repr=False)

    def safe_diagnostics(self):
        return {"kind": self.kind, "outcome": self.outcome, "item_count": len(self.private.get("items", [])),
                "origin_verified": False, "signature_verified": False, "submission_ready": False}


def inspect_receipt(content, batch_count=None):
    if not isinstance(content, bytes) or not content or len(content) > MAX_RECEIPT:
        fail()
    if batch_count is not None and (type(batch_count) is not int or not 1 <= batch_count <= 100000):
        fail()
    if content.startswith(b"%PDF-"):
        return ParsedReceipt("pdf_attachment", "not_interpreted", {"items": [], "notes": ["pdf_not_parsed"]})
    try:
        root = parse_local_xml(content)
    except (etree.LxmlError, ValueError, TypeError):
        fail()
    if sum(1 for _ in root.iter()) > 30000:
        fail()
    tag = etree.QName(root)
    if tag.localname == "ProcessingResult" and tag.namespace in (None, CSSZ):
        result = root
    elif root.tag == "{" + GOV + "}GovTalkMessage":
        envelope = root.findall("{" + GOV + "}Body/{" + CSSZ + "}Message")
        if len(envelope) != 1 or envelope[0].get("eType") != "response":
            fail()
        classification = root.findall("{" + GOV + "}Header/{" + GOV + "}MessageDetails/{" + GOV + "}Class")
        if len(classification) != 1 or classification[0].text != "CSSZ_JMHZ":
            fail()
        results = envelope[0].findall("{" + CSSZ + "}Body/{" + CSSZ + "}ProcessingResult")
        if len(results) != 1:
            fail()
        result = results[0]
    elif root.tag == "{" + CSSZ + "}Message" and root.get("eType") == "response":
        results = root.findall("{" + CSSZ + "}Body/{" + CSSZ + "}ProcessingResult")
        if len(results) != 1:
            fail()
        result = results[0]
    else:
        return ParsedReceipt("xml_attachment", "not_interpreted", {"items": [], "notes": ["xml_format_not_supported"]})
    if result.get("type") != "CSSZ_JMHZ" or result.get("version") != "1,0":
        return ParsedReceipt("xml_attachment", "not_interpreted", {"items": [], "notes": ["processing_result_version_not_supported"]})
    if any(len(v) > 65536 for v in result.attrib.values()):
        fail()
    # No hidden second result or foreign-namespace lookalikes inside an envelope.
    results = [n for n in root.iter() if isinstance(n.tag, str) and etree.QName(n).localname == "ProcessingResult"]
    if len(results) != 1:
        fail()
    ns = etree.QName(result).namespace
    prefix = "{" + ns + "}" if ns else ""
    containers = result.findall(prefix + "Details")
    if len(containers) > 1:
        fail()
    items, notes, seen, singular = [], [], set(), set()
    for index, node in enumerate(containers[0] if containers else []):
        if index > 1502 or node.tag != prefix + "Item" or len(node):
            fail()
        if any(len(v) > 65536 for v in node.attrib.values()):
            fail()
        subtype = node.get("subtype", "").strip()
        item = {"subtype": subtype, "form_guid": "", "identifier": node.get("identifier", ""),
                "result": node.get("result", ""), "error_code": node.get("errNum", ""),
                "message": node.get("errMsg", ""), "period_as_received": node.get("period", "")}
        if index == 0:
            if subtype or node.get("sqnr", "").strip() or item["identifier"].strip():
                fail()
        elif subtype == "FORM":
            item["form_guid"] = canonical_guid(node.get("sqnr", ""))
            if item["form_guid"] in seen or len(seen) >= 1500:
                fail()
            seen.add(item["form_guid"])
        elif subtype in {"SOUHRN", "PVPOJ"}:
            if subtype in singular or node.get("sqnr", "").strip():
                fail()
            singular.add(subtype)
        else:
            fail()
        if item["result"] not in {"OK", "ERROR"}:
            notes.append("item_result_not_supported")
        items.append(item)
    # Catch ignored siblings/namespace variants instead of deriving success.
    if len([n for n in result.iter() if isinstance(n.tag, str) and etree.QName(n).localname == "Item"]) != len(items):
        fail()
    status = result.get("result", "")
    outcome = "unresolved"
    if items and items[0]["result"] == "ERROR":
        outcome = "rejected"  # General/header rejection wins over per-form OK.
    elif status == "OK" and all(i["result"] == "OK" for i in items):
        outcome = "accepted_for_processing"
    elif status == "ERROR" and items and not notes:
        body = items[1:]
        ok = sum(i["result"] == "OK" for i in body)
        errors = sum(i["result"] == "ERROR" for i in body)
        if errors and ok:
            outcome = "partially_accepted"
        elif errors and not ok and batch_count is not None:
            outcome = "rejected" if batch_count == 1 else "partially_accepted"
        else:
            notes.append("batch_count_or_result_review_required")
    if status == "OK" and any(i["result"] == "ERROR" for i in items):
        notes.append("top_result_inconsistent")
        if not items or items[0]["result"] != "ERROR":
            outcome = "unresolved"
    if status not in {"OK", "ERROR"}:
        notes.append("top_result_not_supported")
        outcome = "unresolved"
    if "item_result_not_supported" in notes:
        outcome = "unresolved"
    private = {"items": items, "notes": sorted(set(notes)), "top_result": status,
               "error_code": result.get("errNumber", ""), "message": result.get("errMsg", ""),
               "submission_reference": result.get("vlastniIdPodani", ""),
               "counts_as_received": {k: result.get(k, "") for k in ("count", "countErr", "countWar")},
               "format_version": "1,0", "methodology": "MPSV-JMHZ-protokoly-MH-v1.5-DOCX",
               "xsd_validation": "not_available", "monthly_completeness": "not_determined",
               "signature_verified": False, "origin_verified": False}
    return ParsedReceipt("dis_processing_result", outcome, private)


def read_receipt(path):
    try:
        path = Path(path)
        if not path.is_file():
            fail()
        with path.open("rb") as stream:
            content = stream.read(MAX_RECEIPT + 1)
    except OSError:
        raise ReceiptError("Soubor protokolu nelze načíst.") from None
    if len(content) > MAX_RECEIPT:
        fail()
    return content


def import_receipt(workspace, organization_id, import_id, draft_id, content, context_confirmed=False,
                   expected_reference=None, batch_count=None):
    if context_confirmed is not True:
        raise ReceiptError("Potvrďte organizaci, měsíc a konkrétní odeslané pracovní XML; protokol nemusí obsahovat VS/období.")
    imported = workspace.get_import(organization_id, import_id)
    org = workspace.organization(organization_id)
    draft = parse_local_xml(workspace.draft_bytes(org.id, import_id, draft_id))
    # Bind to the selected original XML, never to whichever import is newest.
    header = draft[0]
    ns = etree.QName(header).namespace
    prefix = "{" + ns + "}" if ns else ""
    if (header.findtext(prefix + "variabilniSymbol") != org.variable_symbol
            or header.findtext(prefix + "rok") != str(imported.period.year)
            or int(header.findtext(prefix + "mesic", "0")) != imported.period.month):
        raise ReceiptError("Pracovní XML neodpovídá organizaci nebo období.")
    identities = {}
    for node in draft.iter():
        if isinstance(node.tag, str) and etree.QName(node).localname == "idFormulare":
            wrapper = node.getparent().getparent()
            identities[canonical_guid(node.text)] = (wrapper.xpath("string(.//*[local-name()='ikMpsv'])"),
                                                     wrapper.xpath("string(.//*[local-name()='idPpv'])"))
    expected = set(identities)
    parsed = inspect_receipt(content, batch_count)
    forms = [i for i in parsed.private["items"] if i["subtype"] == "FORM"]
    if any(i["form_guid"] not in expected for i in forms):
        raise ReceiptError("Protokol obsahuje GUID formuláře, které není ve zvoleném XML; nic nebylo spárováno odhadem.")
    def metadata(row, key):
        ref = imported.profile["metadata"].get(key, {})
        column = ref.get("column") or imported.profile["items"].get(ref.get("item"), {}).get("column")
        return row.values.get(column, "")
    source_forms = {}
    for row in imported.source.rows:
        source_forms.setdefault(str(metadata(row, "form_id")).strip().upper(), []).append(row)
    for item in forms:
        matches = source_forms.get(item["form_guid"], [])
        if len(matches) == 1:
            row = matches[0]
            item["source_row"] = row.number
            item["internal_number"] = metadata(row, "internal_number")
        pair = item["identifier"].split(";")
        if len(pair) == 2:
            # Compare what was actually sent, not metadata omitted by an IN01 choice.
            for original, returned in zip(identities[item["form_guid"]], pair):
                if original and returned and original != returned:
                    raise ReceiptError("Identifikace zaměstnání v odpovědi odporuje zvolenému vstupu; vazba nebyla změněna odhadem.")
        # Returned/new OIČ and PPV stay in the receipt, never mutate payroll.
        item["returned_identity_applied"] = False
    if expected_reference is not None and (not isinstance(expected_reference, str) or not expected_reference.strip()
            or parsed.kind != "dis_processing_result" or parsed.private["submission_reference"] != expected_reference):
        raise ReceiptError("Identifikátor odeslané zprávy neodpovídá protokolu.")
    report = dict(parsed.private, kind=parsed.kind, outcome=parsed.outcome, submission_ready=False,
                  correlation="explicit_context_and_form_guids" if forms else "explicit_context_only",
                  expected_form_count=len(expected), missing_form_count=len(expected - {i["form_guid"] for i in forms}))
    if report["missing_form_count"] and parsed.outcome != "rejected" and parsed.kind == "dis_processing_result":
        report["notes"].append("selected_xml_forms_not_all_reported")
        report["outcome"] = "unresolved"
    context = {"confirmed": True, "expected_reference": expected_reference, "batch_count": batch_count,
               "period": imported.period.iso, "draft_sha256": hashlib.sha256(workspace.draft_bytes(org.id, import_id, draft_id)).hexdigest()}
    sha = hashlib.sha256(content).hexdigest()
    identity = str(uuid5(UUID(org.id), "receipt:" + draft_id + ":" + sha))
    with workspace._data(org.id) as db:
        previous = db.execute("SELECT id,context FROM processing_receipts WHERE draft_id=? AND sha256=?", (draft_id, sha)).fetchone()
        if previous:
            if previous["context"] != dumps(context):
                raise ReceiptError("Tento protokol je již uložen s jiným kontextem; historie se nepřepisuje.")
            return previous["id"]
        db.execute("INSERT INTO processing_receipts VALUES (?,?,?,?,?,?,?,?,?)", (identity, import_id, draft_id, now(), sha, parsed.kind, dumps(context), dumps(report), content))
    return identity


def receipt_history(workspace, organization_id, import_id):
    workspace.get_import(organization_id, import_id)
    with workspace._data(organization_id) as db:
        rows = db.execute("SELECT id,draft_id,created_at,sha256,kind,report FROM processing_receipts WHERE import_id=? ORDER BY created_at,id", (import_id,)).fetchall()
    return tuple(
        {"id": r["id"], "draft_id": r["draft_id"], "created_at": r["created_at"], "sha256": r["sha256"], "kind": r["kind"],
         "outcome": strict_json(r["report"])["outcome"]} for r in rows)


def _receipt_row(workspace, organization_id, import_id, receipt_id):
    workspace.get_import(organization_id, import_id)
    with workspace._data(organization_id) as db:
        row = db.execute("SELECT * FROM processing_receipts WHERE id=? AND import_id=?", (receipt_id, import_id)).fetchone()
    if row is None:
        raise ReceiptError("Protokol v této organizaci a importu neexistuje.")
    if hashlib.sha256(row["content"]).hexdigest() != row["sha256"]:
        raise ReceiptError("Uložený protokol neprošel kontrolou integrity.")
    return row


def receipt_detail(workspace, organization_id, import_id, receipt_id):
    row = _receipt_row(workspace, organization_id, import_id, receipt_id)
    return {"context": strict_json(row["context"]), "report": strict_json(row["report"]), "sha256": row["sha256"]}


def save_original(workspace, organization_id, import_id, receipt_id, path):
    content = _receipt_row(workspace, organization_id, import_id, receipt_id)["content"]
    try:
        with Path(path).open("xb") as stream:
            import os
            if os.name != "nt":
                os.fchmod(stream.fileno(), 0o600)
            stream.write(content)
    except OSError:
        raise ReceiptError("Originál nelze uložit. Použijte nový soubor v chráněném umístění; existující soubor se nepřepisuje.") from None
