"""Synthetic receipts use the documented DIS format, not invented cJMHZ XML."""
import json
from pathlib import Path
from zipfile import ZipFile

from lxml import etree
import pytest

from app.core.receipts import (CSSZ, GOV, ReceiptError, inspect_receipt, import_receipt,
                               receipt_history, receipt_detail, read_receipt, save_original)
from app.core.backups import create_backup, restore_backup
from app.core.organizations import OrganizationWorkspace
from test_monthly_packet import workspace_case

GUID = "00000000-0000-4000-8000-000000000001"
OTHER_GUID = "00000000-0000-4000-8000-000000000099"


def response(form=GUID, status="OK", header="OK", body=("OK", "OK", "OK"), namespace=None):
    prefix = "{" + namespace + "}" if namespace else ""
    root = etree.Element(prefix + "ProcessingResult", type="CSSZ_JMHZ", version="1,0", result=status,
                         errMsg="", errNumber="0", count="3", countErr="0", countWar="0", vlastniIdPodani="TEST-MESSAGE-1")
    details = etree.SubElement(root, prefix + "Details")
    for subtype, sqnr, result in [("", "", header), ("SOUHRN", "", body[0]), ("PVPOJ", "", body[1]), ("FORM", form, body[2])]:
        etree.SubElement(details, prefix + "Item", subtype=subtype, sqnr=sqnr, identifier=";" if subtype == "FORM" else "", result=result, errNum="", errMsg="", period="")
    return etree.tostring(root, encoding="UTF-8", xml_declaration=True)


@pytest.mark.parametrize("status,header,body,batches,outcome", [
    ("OK", "OK", ("OK", "OK", "OK"), None, "accepted_for_processing"),
    ("ERROR", "ERROR", ("OK", "OK", "OK"), None, "rejected"),
    ("ERROR", "OK", ("OK", "OK", "ERROR"), None, "partially_accepted"),
    ("ERROR", "OK", ("ERROR", "ERROR", "ERROR"), None, "unresolved"),
    ("ERROR", "OK", ("ERROR", "ERROR", "ERROR"), 1, "rejected"),
    ("ERROR", "OK", ("ERROR", "ERROR", "ERROR"), 2, "partially_accepted"),
    ("OK", "OK", ("OK", "OK", "ERROR"), None, "unresolved"),
    ("OTHER", "OK", ("OK", "OK", "OK"), None, "unresolved")])
def test_documented_dis_rules_not_monthly_completeness(status, header, body, batches, outcome):
    result = inspect_receipt(response(status=status, header=header, body=body), batches)
    assert result.outcome == outcome
    assert result.private["monthly_completeness"] == "not_determined"
    assert not result.safe_diagnostics()["submission_ready"]


def test_supplied_official_envelope_example_and_namespace_matching():
    archive = Path(__file__).parents[1] / "schemas/official/2027/mpsv-jmhz-protokoly-mh-v1.5.zip"
    with ZipFile(archive) as z:
        example = z.read(next(n for n in z.namelist() if n.endswith('.xml')))
    parsed = inspect_receipt(example)
    assert parsed.kind == "dis_processing_result" and parsed.outcome == "accepted_for_processing"
    assert parsed.private["signature_verified"] is False
    assert inspect_receipt(response(namespace=CSSZ)).outcome == "accepted_for_processing"
    # Lookalikes in an unrelated namespace are not interpreted.
    assert inspect_receipt(response(namespace="urn:not-cssz")).outcome == "not_interpreted"


@pytest.mark.parametrize("content", [b'<!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><a>&x;</a>',
    b'<ProcessingResult', b'', b'x' * (10 * 1024 * 1024 + 1)])
def test_unsafe_or_invalid_files_fail_without_echoing_source(content):
    with pytest.raises(ReceiptError) as error:
        inspect_receipt(content)
    assert '/etc/passwd' not in str(error.value)


def test_duplicates_wrapping_ambiguity_and_unknown_results():
    root = etree.fromstring(response())
    root[0].append(etree.fromstring(etree.tostring(root[0][-1])))
    with pytest.raises(ReceiptError):
        inspect_receipt(etree.tostring(root))
    root = etree.fromstring(response())
    root[0][-1].set('result', 'NEW-STATUS')
    assert inspect_receipt(etree.tostring(root)).outcome == 'unresolved'
    root.set('version', 'future')
    assert inspect_receipt(etree.tostring(root)).kind == 'xml_attachment'
    with pytest.raises(ReceiptError):
        inspect_receipt(response(), True)


def test_diagnostics_do_not_include_private_identity_or_error_text():
    private = 'TEST-PRIVATE-IDENTITY-AND-PAYROLL'
    root = etree.fromstring(response(status='ERROR', body=('OK', 'OK', 'ERROR')))
    root.set('errMsg', private);root[0][-1].set('identifier', private);root[0][-1].set('errMsg', private)
    parsed = inspect_receipt(etree.tostring(root))
    assert private not in repr(parsed) and private not in json.dumps(parsed.safe_diagnostics())
    assert parsed.private['items'][-1]['message'] == private


def test_context_guid_reference_history_isolation_and_identity_conflict(tmp_path):
    w, org, other, data, imported, draft = workspace_case(tmp_path)
    with pytest.raises(ReceiptError):
        import_receipt(w, org.id, imported.id, draft, response())
    with pytest.raises(ValueError):
        import_receipt(w, other.id, imported.id, draft, response(), True)
    with pytest.raises(ReceiptError):
        import_receipt(w, org.id, imported.id, draft, response(form=OTHER_GUID), True)
    with pytest.raises(ReceiptError):
        import_receipt(w, org.id, imported.id, draft, response(), True, 'different-message')
    rid = import_receipt(w, org.id, imported.id, draft, response(), True, 'TEST-MESSAGE-1')
    assert import_receipt(w, org.id, imported.id, draft, response(), True, 'TEST-MESSAGE-1') == rid
    assert len(receipt_history(w, org.id, imported.id)) == 1
    detail = receipt_detail(w, org.id, imported.id, rid)
    item = detail['report']['items'][-1]
    assert item['internal_number'] == '0002' and item['source_row'] == 2
    assert not item['returned_identity_applied']
    assert detail['report']['outcome'] == 'accepted_for_processing'
    with pytest.raises(ReceiptError):
        import_receipt(w, org.id, imported.id, draft, response(), True, batch_count=2)
    with pytest.raises(ValueError):
        receipt_detail(w, other.id, imported.id, rid)
    conflict = etree.fromstring(response());conflict[0][-1].set('identifier', '0000000000;999')
    with pytest.raises(ReceiptError):
        import_receipt(w, org.id, imported.id, draft, etree.tostring(conflict), True)
    assert w.get_import(org.id, imported.id).source == imported.source


def test_attachments_backup_restore_and_corruption_detection(tmp_path):
    w, org, _, _, imported, draft = workspace_case(tmp_path / 'source')
    rid = import_receipt(w, org.id, imported.id, draft, response(), True)
    pdf = import_receipt(w, org.id, imported.id, draft, b'%PDF-1.4\nsynthetic attachment only', True)
    unknown = import_receipt(w, org.id, imported.id, draft, b'<unknown/>', True)
    assert receipt_detail(w, org.id, imported.id, pdf)['report']['outcome'] == 'not_interpreted'
    assert receipt_detail(w, org.id, imported.id, unknown)['report']['outcome'] == 'not_interpreted'
    backup = tmp_path / 'backup.zip';pin = create_backup(w, org.id, backup)['sha256']
    restored = OrganizationWorkspace(tmp_path / 'restored');restore_backup(restored, backup, pin)
    assert len(receipt_history(restored, org.id, imported.id)) == 3
    assert receipt_detail(restored, org.id, imported.id, rid) == receipt_detail(w, org.id, imported.id, rid)
    exported = tmp_path / 'original.xml'
    save_original(restored, org.id, imported.id, rid, exported)
    assert exported.read_bytes() == response()
    with pytest.raises(ReceiptError):
        save_original(restored, org.id, imported.id, rid, exported)
    with restored._data(org.id) as db:
        db.execute('UPDATE processing_receipts SET content=? WHERE id=?', (b'changed', rid))
    with pytest.raises(ReceiptError):
        receipt_detail(restored, org.id, imported.id, rid)


def test_xml_declared_cp1250_and_unrelated_import_cannot_receive_receipt(tmp_path):
    root = etree.fromstring(response())
    root.set('errMsg', 'Žluťoučký syntetický nález')
    content = etree.tostring(root, encoding='windows-1250', xml_declaration=True)
    assert inspect_receipt(content).private['message'] == 'Žluťoučký syntetický nález'
    path = tmp_path / 'receipt.xml';path.write_bytes(content)
    assert read_receipt(path) == content
    w, org, _, _, imported, draft = workspace_case(tmp_path / 'source')
    other_import = w.import_table(org.id, imported.period, imported.source)
    with pytest.raises(ValueError):
        import_receipt(w, org.id, other_import.id, draft, content, True)


def test_new_identity_from_response_stays_separate_for_foreigner(tmp_path):
    from app.core.models import SourceRow, SourceTable
    from test_monthly_packet import employer_case
    from test_employee_xml import OFFICIAL
    w, org, _, data, imported, _ = workspace_case(tmp_path / 'source')
    row = dict(data[2], oic='', rc='', registration_status='pending_oic')
    incoming = w.import_table(org.id, imported.period, SourceTable(tuple(row), (SourceRow(2, row),)))
    monthly, employer = employer_case(2027)
    eid = w.import_employer_table(org.id, incoming.id, employer, monthly)
    draft, result = w.prepare_monthly_draft(org.id, incoming.id, eid, data[1], data[4], OFFICIAL)
    assert result.xsd_valid
    root = etree.fromstring(response());root[0][-1].set('identifier', '0000000000;999999')
    rid = import_receipt(w, org.id, incoming.id, draft, etree.tostring(root), True)
    assert not receipt_detail(w, org.id, incoming.id, rid)['report']['items'][-1]['returned_identity_applied']
    assert w.get_import(org.id, incoming.id).source.rows[0].values['oic'] == ''


def test_gui_import_private_detail_and_no_confirmation(tmp_path):
    from app.ui.qt_compat import QtWidgets, dispose_window
    from app.ui.receipts_dialog import ReceiptsDialog
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w, org, _, _, imported, draft = workspace_case(tmp_path / 'source')
    dialog = ReceiptsDialog(w, org.id, imported.id, draft)
    path = tmp_path / 'synthetic.xml';path.write_bytes(response())
    assert dialog.import_path(path) is None
    dialog.confirm.setChecked(True)
    rid = dialog.import_path(path)
    assert rid and dialog.table.rowCount() == 1
    assert 'accepted_for_processing' in dialog.detail.toPlainText()
    assert dialog.import_path(path) == rid and dialog.table.rowCount() == 1
    dispose_window(dialog)
