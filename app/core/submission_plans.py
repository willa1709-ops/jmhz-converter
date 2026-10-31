"""Working lineage ledger, never a claim of submission/acceptance or correction XML.

Rules: supplied Pravidla 1.4.6 pp. 23-26, catalog 22/305/306. Reasons remain
explicit; internal revision numbers do not determine official types or GUIDs.
"""
from uuid import UUID, uuid5

from app.core.organizations import database, dumps, now
from app.core.payroll import prepare_payroll, strict_json
from app.core.periods import SubmissionContext
from app.core.xml_support import parse_local_xml


def guid(value):
    if not isinstance(value, str) or len(value) != 36:
        raise ValueError("GUID musí být explicitně dodané UUID ve tvaru 8-4-4-4-12.")
    parsed = UUID(value)
    if str(parsed).lower() != value.lower():
        raise ValueError("GUID nemá kanonický tvar.")
    return str(parsed).upper()


def ensure_ledger(db):
    db.execute("CREATE TABLE IF NOT EXISTS submission_plans (id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, period TEXT NOT NULL, revision_index INTEGER NOT NULL, mode TEXT NOT NULL, base_id TEXT, reason TEXT NOT NULL, import_id TEXT NOT NULL, draft_id TEXT NOT NULL, plan TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(organization_id,period,revision_index))")
    db.execute("CREATE TABLE IF NOT EXISTS guid_claims (guid TEXT PRIMARY KEY, organization_id TEXT NOT NULL, period TEXT NOT NULL, kind TEXT NOT NULL, employment_id TEXT)")


def history(workspace, organization_id, period):
    workspace.organization(organization_id)
    with database(workspace.registry) as db:
        ensure_ledger(db)
        rows = db.execute("SELECT id,revision_index,mode,base_id,reason,created_at FROM submission_plans WHERE organization_id=? AND period=? ORDER BY revision_index", (organization_id, period.iso)).fetchall()
    return tuple(dict(r) for r in rows)


def record_plan(workspace, organization_id, import_id, draft_id, revision_index, mode="R", base_id=None, reason="regular"):
    imported = workspace.get_import(organization_id, import_id)
    xml = parse_local_xml(workspace.draft_bytes(organization_id, import_id, draft_id))
    payroll = prepare_payroll(imported.source, imported.profile, SubmissionContext(imported.period, 0))
    if payroll.issues:
        raise ValueError("Plán vyžaduje jednoznačné PP a identifikační vazby.")
    submission = guid(xml.xpath("string(/*/*[local-name()='hlavicka']/*[local-name()='idPodani'])"))
    forms = {}
    private_identity = {}
    for row in payroll.rows:
        if not row.metadata.get("oic") or not row.metadata.get("id_ppv"):
            raise ValueError("Pro historii oprav chybí prokázaná identita zaměstnání.")
        employment = workspace.employment_uuid(organization_id, row.metadata["internal_number"])
        forms[employment] = guid(row.metadata["form_id"])
        private_identity[employment] = (row.metadata["oic"], row.metadata["id_ppv"])
    xml_forms = [guid(v) for v in xml.xpath("//*[local-name()='idFormulare']/text()")]
    if set(xml_forms) != set(forms.values()) or len(xml_forms) != len(forms):
        raise ValueError("Plán neodpovídá formulářům pracovního XML.")
    if type(revision_index) is not int or revision_index < 0 or mode not in {"R", "O"}:
        raise ValueError("Neplatné pořadí nebo výslovný oficiální režim plánu.")
    if (mode == "R" and (base_id is not None or reason != "regular")) or (mode == "O" and (not base_id or reason not in {"employer_initiated", "rejected_component", "summary_or_insurance"})):
        raise ValueError("Doplňte doložený důvod a původní plán; revize sama není důvod opravy.")
    with database(workspace.registry) as db:
        ensure_ledger(db)
        db.commit()
        db.execute("BEGIN IMMEDIATE")
        expected = db.execute("SELECT COALESCE(MAX(revision_index),-1)+1 FROM submission_plans WHERE organization_id=? AND period=?", (organization_id, imported.period.iso)).fetchone()[0]
        if revision_index != expected:
            raise ValueError("Interní pořadí plánů musí navazovat od nuly.")
        if mode == "O":
            row = db.execute("SELECT * FROM submission_plans WHERE id=? AND organization_id=? AND period=?", (base_id, organization_id, imported.period.iso)).fetchone()
            if row is None:
                raise ValueError("Původní plán patří jiné organizaci/měsíci nebo neexistuje.")
            base = strict_json(row["plan"])
            if base["submission_guid"] != submission:
                raise ValueError("Oprava se musí vázat na GUID řádného měsíčního hlášení.")
            original = workspace.get_import(organization_id, row["import_id"])
            original_payroll = prepare_payroll(original.source, original.profile, SubmissionContext(original.period, 0))
            original_identity = {workspace.employment_uuid(organization_id, r.metadata["internal_number"]): (r.metadata.get("oic"), r.metadata.get("id_ppv")) for r in original_payroll.rows}
            for employment, form in forms.items():
                if employment not in base["form_guids"] or original_identity.get(employment) != private_identity[employment]:
                    raise ValueError("Návaznost zaměstnání není prokázána; nespojuje se odhadem.")
                if reason == "rejected_component" and form == base["form_guids"][employment]:
                    raise ValueError("Náhrada nepropustně vadné součásti vyžaduje nový GUID formuláře.")
                if reason != "rejected_component" and form != base["form_guids"][employment]:
                    raise ValueError("Oprava existující součásti používá původní GUID formuláře.")
        for value, kind, employment in [(submission, "submission", None)] + [(v, "form", k) for k, v in forms.items()]:
            existing = db.execute("SELECT * FROM guid_claims WHERE guid=?", (value,)).fetchone()
            if existing:
                if (existing["organization_id"], existing["period"], existing["kind"], existing["employment_id"]) != (organization_id, imported.period.iso, kind, employment) or mode == "R":
                    raise ValueError("GUID již má jinou vazbu nebo byl použit pro řádný plán.")
            else:
                db.execute("INSERT INTO guid_claims VALUES (?,?,?,?,?)", (value, organization_id, imported.period.iso, kind, employment))
        identity = str(uuid5(UUID(organization_id), "submission-plan:" + imported.period.iso + ":" + str(revision_index)))
        plan = {"submission_guid": submission, "form_guids": forms, "mode": mode, "base_id": base_id,
                "receipt_status": "not_recorded", "readiness": "unverified", "correction_xml_generated": False,
                "source_methodology": "Pravidla_1.4.6_pp23-26_effectivity_review_required", "submission_ready": False}
        db.execute("INSERT INTO submission_plans VALUES (?,?,?,?,?,?,?,?,?,?,?)", (identity, organization_id, imported.period.iso, revision_index, mode, base_id, reason, import_id, draft_id, dumps(plan), now()))
    return identity
