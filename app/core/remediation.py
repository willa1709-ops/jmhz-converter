"""Private, append-only correction tracking; never official submission approval.

Absence from an error list is not evidence of resolution. Local review is
explicit and distinct from DIS acceptance, cJMHZ state and final export.
"""
from datetime import datetime
from collections import Counter
import hashlib
from uuid import UUID, uuid5

from app.core.organizations import dumps, now
from app.core.payroll import strict_json
from app.core.receipts import ReceiptError, receipt_detail, canonical_guid
from app.core.xml_support import parse_local_xml

STATES = {"open": "Otevřeno", "prepared": "Oprava připravena", "awaiting_reply": "Čeká na odpověď",
          "reported_again": "Nález se opakuje", "reply_rejected": "Navazující podání odmítnuto",
          "dis_accepted": "DIS přijal – čeká na kompletnost", "review_required": "Nutný přezkum",
          "closed_by_review": "Uzavřeno ručním přezkumem", "linked_occurrence": "Výskyt navázán na původní nález"}


def ensure_tables(db):
    db.execute("CREATE TABLE IF NOT EXISTS remediation_cases (id TEXT PRIMARY KEY, period TEXT NOT NULL, source_receipt_id TEXT NOT NULL REFERENCES processing_receipts(id), item_index INTEGER NOT NULL, snapshot TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(source_receipt_id,item_index))")
    db.execute("CREATE TABLE IF NOT EXISTS remediation_runs (id TEXT PRIMARY KEY, period TEXT NOT NULL, run_index INTEGER NOT NULL, import_id TEXT NOT NULL REFERENCES imports(id), draft_id TEXT NOT NULL, monthly_guid TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(period,run_index), FOREIGN KEY(draft_id,import_id) REFERENCES drafts(id,import_id))")
    db.execute("CREATE TABLE IF NOT EXISTS remediation_run_cases (run_id TEXT NOT NULL REFERENCES remediation_runs(id), case_id TEXT NOT NULL REFERENCES remediation_cases(id), binding TEXT NOT NULL, PRIMARY KEY(run_id,case_id))")
    db.execute("CREATE TABLE IF NOT EXISTS remediation_dispatches (run_id TEXT NOT NULL REFERENCES remediation_runs(id), period TEXT NOT NULL, kind TEXT NOT NULL, reference TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(run_id,kind), UNIQUE(period,kind,reference))")
    db.execute("CREATE TABLE IF NOT EXISTS remediation_replies (receipt_id TEXT PRIMARY KEY REFERENCES processing_receipts(id), run_id TEXT NOT NULL REFERENCES remediation_runs(id), association TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS remediation_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL REFERENCES remediation_cases(id), run_id TEXT REFERENCES remediation_runs(id), receipt_id TEXT REFERENCES processing_receipts(id), item_index INTEGER, event TEXT NOT NULL, state TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS remediation_occurrences (receipt_id TEXT NOT NULL REFERENCES processing_receipts(id), item_index INTEGER NOT NULL, case_id TEXT NOT NULL REFERENCES remediation_cases(id), PRIMARY KEY(receipt_id,item_index))")
    db.execute("CREATE TABLE IF NOT EXISTS remediation_ingested (receipt_id TEXT PRIMARY KEY REFERENCES processing_receipts(id))")
    db.execute("CREATE INDEX IF NOT EXISTS remediation_case_events ON remediation_events(case_id,seq)")
    db.execute("CREATE INDEX IF NOT EXISTS remediation_case_runs ON remediation_run_cases(case_id,run_id)")
    db.execute("CREATE INDEX IF NOT EXISTS remediation_run_replies ON remediation_replies(run_id)")
    db.execute("CREATE INDEX IF NOT EXISTS remediation_period_cases ON remediation_cases(period,created_at)")


def _note(value):
    if not isinstance(value, str) or not 5 <= len(value.strip()) <= 4000:
        raise ReceiptError("Popište konkrétní opravu nebo přezkum (5–4000 znaků); poznámka zůstane v soukromé DB.")
    return value.strip()


def _event(db, case, state, event, run=None, receipt=None, index=None, note=""):
    db.execute("INSERT INTO remediation_events (case_id,run_id,receipt_id,item_index,event,state,note,created_at) VALUES (?,?,?,?,?,?,?,?)", (case, run, receipt, index, event, state, note, now()))


def _state(db, case):
    row = db.execute("SELECT state FROM remediation_events WHERE case_id=? ORDER BY seq DESC LIMIT 1", (case,)).fetchone()
    if row and row[0] not in STATES:
        raise ReceiptError("Historie nálezu obsahuje neplatný stav; ověřte integritu databáze.")
    return row[0] if row else "open"


def findings(report):
    emitted = False
    for index, item in enumerate(report.get("items", [])):
        if report["kind"] == "cjmhz_completeness" or report["kind"] == "dis_processing_result" and item.get("result") == "ERROR":
            emitted = True
            yield index, item
    if not emitted and report["kind"] == "dis_processing_result" and report.get("top_result") == "ERROR":
        yield -1, {"scope": "top_level", "subtype": "", "form_guid": "", "identifier": "",
                   "error_code": report.get("error_code", ""), "message": report.get("message", ""), "result": "ERROR"}


def _snapshot(report, item):
    part = item.get("part_as_received", item.get("subtype", "")).lower()
    if item.get("scope") == "top_level":
        part = "top_level"
    form = item.get("form_guid", "")
    internal = item.get("internal_number", "")
    if form:
        target = "pp:" + internal if internal else "guid:" + form
    elif part in {"pvpoj", "souhrn"}:
        target = "part:" + part
    elif not part and report["kind"] == "dis_processing_result":
        target = "part:header"
    else:
        target = None
    return {"kind": report["kind"], "code": item.get("error_code", ""), "part": part,
            "error_type": item.get("error_type", ""), "form_guid": form, "internal_number": internal,
            "target": target, "message": item.get("message", "")}


def _register_findings(db, organization_id, receipt, period, report):
    for index, item in findings(report):
        if db.execute("SELECT 1 FROM remediation_occurrences WHERE receipt_id=? AND item_index=?", (receipt, index)).fetchone():
            continue
        identity = str(uuid5(UUID(organization_id), "finding:" + receipt + ":" + str(index)))
        db.execute("INSERT INTO remediation_cases VALUES (?,?,?,?,?,?)", (identity, period, receipt, index, dumps(_snapshot(report, item)), now()))
        db.execute("INSERT INTO remediation_occurrences VALUES (?,?,?)", (receipt, index, identity))
        _event(db, identity, "open", "observed", receipt=receipt, index=index)


def _matches(snapshot, binding, report, item):
    if (snapshot["kind"] != report["kind"] or not snapshot["code"] or snapshot["code"] != item.get("error_code")
            or snapshot["error_type"] != item.get("error_type", "")):
        return False
    target = snapshot["target"]
    if binding.get("form_guid"):
        known = {binding["form_guid"], snapshot["form_guid"], *binding.get("historical_form_guids", [])} - {""}
        return bool(item.get("form_guid")) and item["form_guid"] in known
    if target and target.startswith("part:"):
        return _snapshot(report, item)["target"] == target
    return False


def _associate(db, run, receipt, report, association, note):
    prior = db.execute("SELECT run_id FROM remediation_replies WHERE receipt_id=?", (receipt,)).fetchone()
    if prior:
        if prior[0] != run["id"]:
            raise ReceiptError("Odpověď je již navázaná na jinou opravu.")
        return
    previous = db.execute("SELECT p.report FROM remediation_replies r JOIN processing_receipts p ON p.id=r.receipt_id WHERE r.run_id=?", (run["id"],)).fetchall()
    earlier, conflicting = False, False
    previous_reports = [strict_json(r[0]) for r in previous]
    if report["kind"] == "dis_processing_result":
        earlier = any(p["kind"] == "cjmhz_completeness" for p in previous_reports)
        conflicting = any(p["kind"] == "dis_processing_result" for p in previous_reports)
    elif report["kind"] == "cjmhz_completeness":
        try:
            incoming = datetime.fromisoformat(report["protocol_time"].replace("Z", "+00:00"))
            for p in previous_reports:
                if p["kind"] == "cjmhz_completeness":
                    stamp = datetime.fromisoformat(p["protocol_time"].replace("Z", "+00:00"))
                    if incoming.tzinfo is None or stamp.tzinfo is None:
                        conflicting = True
                    else:
                        earlier = earlier or incoming < stamp
                        conflicting = conflicting or incoming == stamp
        except (ValueError, TypeError, KeyError):
            conflicting = True
    db.execute("INSERT INTO remediation_replies VALUES (?,?,?,?,?)", (receipt, run["id"], association, note, now()))
    members = db.execute("SELECT c.*,m.binding FROM remediation_run_cases m JOIN remediation_cases c ON c.id=m.case_id WHERE m.run_id=?", (run["id"],)).fetchall()
    candidates = list(findings(report))
    matches, candidate_counts = {}, Counter()
    for case in members:
        snapshot, binding = strict_json(case["snapshot"]), strict_json(case["binding"])
        indices = []
        for i, item in candidates:
            if _matches(snapshot, binding, report, item):
                candidate_counts[i] += 1
                if len(indices) < 2:  # Enough to prove ambiguity without a quadratic list.
                    indices.append(i)
        matches[case["id"]] = indices
    for case in members:
        identity = case["id"]
        current = _state(db, identity)
        newest = db.execute("SELECT MAX(r.run_index) FROM remediation_run_cases m JOIN remediation_runs r ON r.id=m.run_id WHERE m.case_id=?", (identity,)).fetchone()[0]
        if earlier or run["run_index"] < newest:
            _event(db, identity, current, "historical_reply", run["id"], receipt, note="Starší odpověď zůstává v historii; nepřepisuje současný stav nálezu.")
            continue
        indices = matches[identity]
        unique = len(indices) == 1 and candidate_counts[indices[0]] == 1
        state, event, index = "review_required", "reply_needs_review", None
        if unique and not conflicting:
            index = indices[0]
            state, event = "reported_again", "reported_again"
            existing = db.execute("SELECT case_id FROM remediation_occurrences WHERE receipt_id=? AND item_index=?", (receipt, index)).fetchone()
            if existing is None:
                db.execute("INSERT INTO remediation_occurrences VALUES (?,?,?)", (receipt, index, identity))
            elif existing[0] != identity:
                # Preserve the original observed case; append a transparent link.
                if not db.execute("SELECT 1 FROM remediation_run_cases WHERE case_id=?", (existing[0],)).fetchone():
                    _event(db, existing[0], "linked_occurrence", "linked_to_original", run["id"], receipt, index, "Navázaný původní nález: " + identity)
        elif current == "closed_by_review" and not conflicting:
            _event(db, identity, current, "reply_after_review", run["id"], receipt, note="Nová odpověď sama neruší ani nepotvrzuje předchozí ruční přezkum.")
            continue
        elif report["kind"] == "dis_processing_result" and report["outcome"] == "rejected":
            state, event = "reply_rejected", "reply_rejected"
        elif not conflicting and report["kind"] == "dis_processing_result":
            binding = strict_json(case["binding"])
            snapshot = strict_json(case["snapshot"])
            accepted = [item for item in report.get("items", []) if item.get("result") == "OK" and (
                binding.get("form_guid") and item.get("form_guid") == binding["form_guid"] or
                snapshot["target"] in {"part:pvpoj", "part:souhrn"} and _snapshot(report, item)["target"] == snapshot["target"])]
            if accepted and report["outcome"] in {"accepted_for_processing", "partially_accepted"}:
                state, event = "dis_accepted", "dis_accepted_not_complete"
        message = "Konkrétní nález je znovu výslovně uveden." if unique and not conflicting else "Nepřítomnost nálezu sama neprokazuje opravu; vyžaduje přezkum."
        if conflicting:
            message = "Odpovědi stejného rozsahu nelze jednoznačně seřadit; nutný přezkum."
        _event(db, identity, state, event, run["id"], receipt, index, message)


def ingest_receipt(db, organization_id, period, receipt, draft_id, report):
    """Called in the same SQLite transaction as the raw receipt insert."""
    if db.execute("SELECT 1 FROM remediation_ingested WHERE receipt_id=?", (receipt,)).fetchone():
        return
    kind = report["kind"]
    reference = report.get("submission_reference") if kind == "dis_processing_result" else report.get("concrete_submission_id") if kind == "cjmhz_completeness" else None
    if reference:
        row = db.execute("SELECT r.* FROM remediation_dispatches d JOIN remediation_runs r ON r.id=d.run_id JOIN processing_receipts p ON p.id=? WHERE d.period=? AND d.kind=? AND d.reference=? AND r.draft_id=? AND d.created_at<=p.created_at", (receipt, period, kind, reference, draft_id)).fetchone()
        if row:
            _associate(db, row, receipt, report, "registered_reference", "Shoda předem evidovaného ID, organizace, období a pracovního XML; původ odpovědi není ověřen.")
    _register_findings(db, organization_id, receipt, period, report)
    db.execute("INSERT INTO remediation_ingested VALUES (?)", (receipt,))


def sync_history(workspace, organization_id, period):
    workspace.organization(organization_id)
    with workspace._data(organization_id) as db:
        rows = db.execute("SELECT p.* FROM processing_receipts p JOIN imports i ON i.id=p.import_id WHERE i.period=? ORDER BY p.created_at,p.id", (period.iso,)).fetchall()
        for row in rows:
            if hashlib.sha256(row["content"]).hexdigest() != row["sha256"]:
                raise ReceiptError("Historický protokol neprošel kontrolou integrity.")
            ingest_receipt(db, organization_id, period.iso, row["id"], row["draft_id"], strict_json(row["report"]))


def cases(workspace, organization_id, period):
    sync_history(workspace, organization_id, period)
    with workspace._data(organization_id) as db:
        rows = db.execute("SELECT * FROM remediation_cases WHERE period=? ORDER BY created_at,id", (period.iso,)).fetchall()
        return tuple(dict(r, snapshot=strict_json(r["snapshot"]), state=_state(db, r["id"])) for r in rows)


def case_history(workspace, organization_id, case_id):
    with workspace._data(organization_id) as db:
        if not db.execute("SELECT 1 FROM remediation_cases WHERE id=?", (case_id,)).fetchone():
            raise ReceiptError("Nález v této organizaci neexistuje.")
        return tuple(dict(r) for r in db.execute("SELECT * FROM remediation_events WHERE case_id=? ORDER BY seq", (case_id,)))


def runs(workspace, organization_id, period):
    with workspace._data(organization_id) as db:
        return tuple(dict(r) for r in db.execute("SELECT * FROM remediation_runs WHERE period=? ORDER BY run_index", (period.iso,)))


def _xml_forms(xml):
    root = parse_local_xml(xml)
    result = {}
    for node in root.xpath("//*[local-name()='idFormulare']"):
        wrapper = node.getparent().getparent()
        result[canonical_guid(node.text)] = (wrapper.xpath("string(.//*[local-name()='ikMpsv'])"), wrapper.xpath("string(.//*[local-name()='idPpv'])"))
    return root, result


def prepare_correction(workspace, organization_id, period, case_ids, import_id, draft_id, note, confirmed=False):
    if confirmed is not True or not case_ids or len(set(case_ids)) != len(case_ids):
        raise ReceiptError("Vyberte nálezy a potvrďte návaznost opravených dat a XML.")
    note = _note(note)
    imported = workspace.get_import(organization_id, import_id)
    if imported.period != period:
        raise ReceiptError("Opravená data patří jinému období.")
    xml = workspace.draft_bytes(organization_id, import_id, draft_id)
    root, form_ids = _xml_forms(xml)
    org = workspace.organization(organization_id)
    if (root.xpath("string(/*/*[local-name()='hlavicka']/*[local-name()='variabilniSymbol'])") != org.variable_symbol
            or root.xpath("string(/*/*[local-name()='hlavicka']/*[local-name()='rok'])") != str(period.year)
            or root.xpath("string(/*/*[local-name()='hlavicka']/*[local-name()='mesic'])") not in {str(period.month), str(period.month).zfill(2)}):
        raise ReceiptError("Pracovní XML nemá správný kontext organizace a měsíce.")
    mapping = {}
    def meta(row, key):
        ref = imported.profile["metadata"].get(key, {})
        column = ref.get("column") or imported.profile["items"].get(ref.get("item"), {}).get("column")
        return str(row.values.get(column, "")).strip()
    for row in imported.source.rows:
        form = meta(row, "form_id")
        if form:
            mapping.setdefault(meta(row, "internal_number"), []).append(canonical_guid(form))
    sync_history(workspace, organization_id, period)
    with workspace._data(organization_id) as db:
        selected, original_cache = [], {}
        for identity in case_ids:
            case = db.execute("SELECT c.*,p.import_id,p.draft_id FROM remediation_cases c JOIN processing_receipts p ON p.id=c.source_receipt_id WHERE c.id=? AND c.period=?", (identity, period.iso)).fetchone()
            if case is None or _state(db, identity) in {"closed_by_review", "linked_occurrence"}:
                raise ReceiptError("Nález není otevřený v této organizaci a období.")
            snapshot = strict_json(case["snapshot"])
            original_import, original_draft = case["import_id"], case["draft_id"]
            manual = db.execute("SELECT e.item_index,p.report,p.import_id,p.draft_id FROM remediation_events e JOIN processing_receipts p ON p.id=e.receipt_id WHERE e.case_id=? AND e.event='manual_occurrence_link' ORDER BY e.seq DESC LIMIT 1", (identity,)).fetchone()
            if manual:
                proof = dict(findings(strict_json(manual["report"])))[manual["item_index"]]
                snapshot = _snapshot(strict_json(manual["report"]), proof)
                original_import, original_draft = manual["import_id"], manual["draft_id"]
            expected = snapshot["form_guid"] if snapshot["form_guid"] in form_ids else ""
            if snapshot["internal_number"]:
                candidates = mapping.get(snapshot["internal_number"], [])
                if len(candidates) != 1 or candidates[0] not in form_ids:
                    raise ReceiptError("PP z nálezu nemá jednoznačnou návaznost v opraveném XML.")
                expected = candidates[0]
                key = (original_import, original_draft)
                if key not in original_cache:
                    original_cache[key] = _xml_forms(workspace.draft_bytes(organization_id, original_import, original_draft))[1]
                original_ids = original_cache[key]
                old = original_ids.get(snapshot["form_guid"], ("", ""))
                if any(a and b and a != b for a, b in zip(old, form_ids[expected])):
                    raise ReceiptError("Identifikační údaje PP si odporují; automatická návaznost opravy není přípustná.")
            known = {snapshot["form_guid"]} - {""}
            for row in db.execute("SELECT binding FROM remediation_run_cases WHERE case_id=?", (identity,)):
                binding = strict_json(row[0])
                known.update(binding.get("historical_form_guids", []))
                if binding.get("form_guid"):
                    known.add(binding["form_guid"])
            selected.append((identity, dumps({"form_guid": expected, "internal_number": snapshot["internal_number"], "historical_form_guids": sorted(known)})))
        db.execute("BEGIN IMMEDIATE")
        if any(_state(db, identity) in {"closed_by_review", "linked_occurrence"} for identity, _ in selected):
            raise ReceiptError("Nález byl mezitím uzavřen nebo navázán jinam; obnovte přehled.")
        index = db.execute("SELECT COALESCE(MAX(run_index),-1)+1 FROM remediation_runs WHERE period=?", (period.iso,)).fetchone()[0]
        run = str(uuid5(UUID(organization_id), "correction:" + period.iso + ":" + str(index)))
        monthly = canonical_guid(root.xpath("string(/*/*[local-name()='hlavicka']/*[local-name()='idPodani'])"))
        db.execute("INSERT INTO remediation_runs VALUES (?,?,?,?,?,?,?,?)", (run, period.iso, index, import_id, draft_id, monthly, note, now()))
        for identity, binding in selected:
            db.execute("INSERT INTO remediation_run_cases VALUES (?,?,?)", (run, identity, binding))
            _event(db, identity, "prepared", "correction_prepared", run=run, note=note)
    return run


def register_dispatch(workspace, organization_id, run_id, kind, reference, confirmed=False, note=""):
    if confirmed is not True or kind not in {"dis_processing_result", "cjmhz_completeness"} or not isinstance(reference, str) or not 1 <= len(reference) <= 500 or not reference.strip():
        raise ReceiptError("Potvrďte skutečné externí odeslání a uveďte přesné ID správného typu odpovědi.")
    note = _note(note) if note else ""
    with workspace._data(organization_id) as db:
        run = db.execute("SELECT * FROM remediation_runs WHERE id=?", (run_id,)).fetchone()
        if run is None:
            raise ReceiptError("Oprava v této organizaci neexistuje.")
        existing = db.execute("SELECT * FROM remediation_dispatches WHERE (run_id=? AND kind=?) OR (period=? AND kind=? AND reference=?)", (run_id, kind, run["period"], kind, reference)).fetchall()
        if existing:
            if len(existing) == 1 and existing[0]["run_id"] == run_id and existing[0]["reference"] == reference:
                return
            raise ReceiptError("Toto ID je již evidované jinak; odeslání ani historii nelze přepsat.")
        db.execute("INSERT INTO remediation_dispatches VALUES (?,?,?,?,?)", (run_id, run["period"], kind, reference, now()))
        for row in db.execute("SELECT case_id FROM remediation_run_cases WHERE run_id=?", (run_id,)):
            state = _state(db, row[0])
            newest = db.execute("SELECT MAX(r.run_index) FROM remediation_run_cases m JOIN remediation_runs r ON r.id=m.run_id WHERE m.case_id=?", (row[0],)).fetchone()[0]
            if state not in {"closed_by_review", "linked_occurrence"} and run["run_index"] == newest and not db.execute("SELECT 1 FROM remediation_replies WHERE run_id=?", (run_id,)).fetchone():
                state = "awaiting_reply"
            _event(db, row[0], state, "external_dispatch_recorded", run_id, note="Uživatelem zaznamenané odeslání mimo aplikaci; nejde o doklad doručení. " + note)


def link_reply(workspace, organization_id, run_id, import_id, receipt_id, note, confirmed=False):
    if confirmed is not True:
        raise ReceiptError("Potvrďte ručně ověřenou návaznost odpovědi na konkrétní opravu.")
    note = _note(note)
    data = receipt_detail(workspace, organization_id, import_id, receipt_id)
    with workspace._data(organization_id) as db:
        run = db.execute("SELECT * FROM remediation_runs WHERE id=?", (run_id,)).fetchone()
        row = db.execute("SELECT * FROM processing_receipts WHERE id=? AND import_id=?", (receipt_id, import_id)).fetchone()
        if run is None or row is None or run["import_id"] != import_id or run["draft_id"] != row["draft_id"]:
            raise ReceiptError("Odpověď nemá stejný import a pracovní XML jako zvolená oprava.")
        _associate(db, run, receipt_id, data["report"], "manual_review", note)


def close_after_review(workspace, organization_id, case_id, run_id, import_id, receipt_id, note, confirmed=False):
    if confirmed is not True:
        raise ReceiptError("Uzavření vyžaduje výslovný přezkum konkrétní opravy; zmizení chyby nestačí.")
    note = _note(note)
    data = receipt_detail(workspace, organization_id, import_id, receipt_id)
    if data["report"]["kind"] != "cjmhz_completeness":
        raise ReceiptError("DIS ani nevyhodnocená příloha nenahrazují přezkum navazujícího protokolu o kompletnosti.")
    with workspace._data(organization_id) as db:
        row = db.execute("SELECT r.*,m.binding,c.snapshot FROM remediation_runs r JOIN remediation_run_cases m ON m.run_id=r.id JOIN remediation_cases c ON c.id=m.case_id WHERE r.id=? AND c.id=?", (run_id, case_id)).fetchone()
        linked = db.execute("SELECT 1 FROM remediation_replies WHERE run_id=? AND receipt_id=?", (run_id, receipt_id)).fetchone()
        newest = db.execute("SELECT MAX(r.run_index) FROM remediation_run_cases m JOIN remediation_runs r ON r.id=m.run_id WHERE m.case_id=?", (case_id,)).fetchone()[0]
        if row is None or not linked or row["import_id"] != import_id or row["run_index"] != newest:
            raise ReceiptError("Přezkum musí patřit poslední opravě nálezu a její navázané odpovědi.")
        if any(_matches(strict_json(row["snapshot"]), strict_json(row["binding"]), data["report"], item) for _, item in findings(data["report"])):
            raise ReceiptError("Tento nález je v odpovědi stále výslovně uvedený; nelze jej uzavřít jako opravený.")
        events = db.execute("SELECT event FROM remediation_events WHERE case_id=? AND run_id=? AND receipt_id=? ORDER BY seq DESC LIMIT 1", (case_id, run_id, receipt_id)).fetchone()
        if events is None or events[0] in {"historical_reply", "reply_rejected", "reported_again", "manual_occurrence_link"}:
            raise ReceiptError("Historická nebo odmítnutá odpověď nemůže doložit tuto opravu.")
        latest = db.execute("SELECT receipt_id FROM remediation_events WHERE case_id=? AND run_id=? AND receipt_id IS NOT NULL AND event NOT IN ('historical_reply','external_dispatch_recorded') ORDER BY seq DESC LIMIT 1", (case_id, run_id)).fetchone()
        if latest is None or latest[0] != receipt_id:
            raise ReceiptError("Použijte poslední relevantní odpověď této opravy; starší odpověď nesmí zakrýt novější nález.")
        _event(db, case_id, "closed_by_review", "closed_by_manual_review", run_id, receipt_id, note=note)


def link_finding(workspace, organization_id, case_id, run_id, import_id, receipt_id, item_index, note, confirmed=False):
    if confirmed is not True or type(item_index) is not int:
        raise ReceiptError("Potvrďte ruční přiřazení konkrétního výskytu nálezu.")
    note = _note(note)
    data = receipt_detail(workspace, organization_id, import_id, receipt_id)
    item = dict(findings(data["report"])).get(item_index)
    with workspace._data(organization_id) as db:
        case = db.execute("SELECT c.*,m.binding FROM remediation_cases c JOIN remediation_run_cases m ON m.case_id=c.id WHERE c.id=? AND m.run_id=?", (case_id, run_id)).fetchone()
        linked = db.execute("SELECT 1 FROM remediation_replies WHERE run_id=? AND receipt_id=?", (run_id, receipt_id)).fetchone()
        if case is None or not linked or item is None:
            raise ReceiptError("Výskyt nebo nález není součástí navázané odpovědi této opravy.")
        snapshot = strict_json(case["snapshot"])
        if snapshot["kind"] != data["report"]["kind"] or snapshot["code"] != item.get("error_code"):
            raise ReceiptError("Jiný typ protokolu nebo jiný chybový kód se neslučuje odhadem.")
        binding = strict_json(case["binding"])
        internal = binding.get("internal_number") or snapshot["internal_number"]
        if internal and item.get("internal_number") and internal != item["internal_number"]:
            raise ReceiptError("Výskyt má doložený jiný pracovní poměr; nálezy se neslučují podle stejného kódu.")
        target = _snapshot(data["report"], item)["target"]
        if snapshot["target"] in {"part:pvpoj", "part:souhrn"} and target and target != snapshot["target"]:
            raise ReceiptError("Výskyt má jinou doloženou část podání; evidujte jej samostatně.")
        newest = db.execute("SELECT MAX(r.run_index) FROM remediation_run_cases m JOIN remediation_runs r ON r.id=m.run_id WHERE m.case_id=?", (case_id,)).fetchone()[0]
        run = db.execute("SELECT * FROM remediation_runs WHERE id=?", (run_id,)).fetchone()
        events = db.execute("SELECT event FROM remediation_events WHERE case_id=? AND run_id=? AND receipt_id=? ORDER BY seq DESC LIMIT 1", (case_id, run_id, receipt_id)).fetchone()
        if run["run_index"] != newest or events is None or events[0] == "historical_reply":
            raise ReceiptError("Starší oprava nebo historická odpověď nesmí změnit aktuální nález.")
        original = db.execute("SELECT case_id FROM remediation_occurrences WHERE receipt_id=? AND item_index=?", (receipt_id, item_index)).fetchone()
        if original and original[0] != case_id:
            if db.execute("SELECT 1 FROM remediation_run_cases WHERE case_id=?", (original[0],)).fetchone():
                raise ReceiptError("Výskyt má vlastní evidovanou opravu; neslučujte dvě rozpracované historie.")
            _event(db, original[0], "linked_occurrence", "linked_to_original_by_user", run_id, receipt_id, item_index, note + " | Původní nález: " + case_id)
        _event(db, case_id, "reported_again", "manual_occurrence_link", run_id, receipt_id, item_index, note)


def reply_binding(workspace, organization_id, receipt_id):
    with workspace._data(organization_id) as db:
        row = db.execute("SELECT r.run_id,r.association,c.run_index FROM remediation_replies r JOIN remediation_runs c ON c.id=r.run_id WHERE r.receipt_id=?", (receipt_id,)).fetchone()
        return dict(row) if row else None


def reopen(workspace, organization_id, case_id, note):
    note = _note(note)
    with workspace._data(organization_id) as db:
        if not db.execute("SELECT 1 FROM remediation_cases WHERE id=?", (case_id,)).fetchone():
            raise ReceiptError("Nález v této organizaci neexistuje.")
        _event(db, case_id, "open", "reopened_by_user", note=note)


def add_note(workspace, organization_id, case_id, note):
    note = _note(note)
    with workspace._data(organization_id) as db:
        if not db.execute("SELECT 1 FROM remediation_cases WHERE id=?", (case_id,)).fetchone():
            raise ReceiptError("Nález v této organizaci neexistuje.")
        _event(db, case_id, _state(db, case_id), "user_note", note=note)
