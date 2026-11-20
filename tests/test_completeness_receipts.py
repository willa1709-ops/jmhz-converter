"""Synthetic shape-equivalent fixtures; uploaded employer documents stay private."""
from copy import deepcopy
import json

from lxml import etree
import pytest

from app.core.receipts import (CJMHZ, ReceiptError, inspect_receipt, import_receipt,
                               receipt_detail, receipt_history, save_original)
from app.core.backups import create_backup, restore_backup
from app.core.organizations import OrganizationWorkspace
from test_monthly_packet import workspace_case
from test_receipts import response

MONTHLY_GUID = '00000000-0000-4000-8000-000000000002'
FORM_GUID = '00000000-0000-4000-8000-000000000001'
OTHER_GUID = '00000000-0000-4000-8000-000000000099'
TECHNICAL_ID = 'a' * 32


def protocol(code='4', name=None, form=FORM_GUID, technical_id=TECHNICAL_ID, year='2027', month='9', vs='0000000001', monthly=MONTHLY_GUID):
    q = '{' + CJMHZ + '}'
    root = etree.Element(q + 'ProtokolOZpracovani', nsmap={None: CJMHZ})
    for key, value in [('datumProtokolu', year + '-10-01T12:00:00.123+02:00'), ('variabilniSymbol', vs),
                       ('idKonkretnihoPodani', technical_id), ('datumPodani', year + '-10-01T09:00:00+02:00'),
                       ('idPodani', monthly), ('mesic', month), ('rok', year)]:
        etree.SubElement(root, q + key).text = value
    state = etree.SubElement(root, q + 'stavMH')
    etree.SubElement(state, q + 'kod').text = code
    etree.SubElement(state, q + 'nazev').text = name if name is not None else {'4': 'Hlášení je částečně přijato', '6': 'Hlášení obsahuje propustné chyby'}.get(code, 'TEST neznámý stav')
    errors = etree.SubElement(root, q + 'chybySeznam')
    for index, (part, reference) in enumerate([('nezarazeno', form), ('form', None)]):
        error = etree.SubElement(errors, q + 'chyba')
        fields = [('id', 'TEST-ERROR-' + str(index)), ('typChyby', 'zpracovani'), ('castPodani', part)]
        if reference:
            fields.append(('idFormulare', reference))
        fields += [('kod', 'TEST-' + str(index)), ('popis', 'Syntetický nález – žádná skutečná mzdová data.')]
        for key, value in fields:
            etree.SubElement(error, q + key).text = value
    return etree.tostring(root, encoding='UTF-8', xml_declaration=True)


@pytest.mark.parametrize('code,outcome', [('4', 'monthly_partially_accepted'), ('6', 'monthly_with_errors')])
def test_observed_states_are_monthly_not_per_submission_or_per_pp(code, outcome):
    parsed = inspect_receipt(protocol(code))
    assert parsed.kind == 'cjmhz_completeness' and parsed.outcome == outcome
    assert parsed.private['concrete_submission_result'] == 'not_supplied'
    assert parsed.private['form_coverage'] == 'error_list_only'
    assert parsed.private['fully_complete'] is None
    assert parsed.private['signature_verified'] is False
    assert parsed.private['xsd_validation'] == 'not_available'
    assert not parsed.safe_diagnostics()['submission_ready']
    assert parsed.private['items'][0]['part_as_received'] == 'nezarazeno'
    assert parsed.private['items'][1]['link_status'] == 'no_form_guid_supplied'


@pytest.mark.parametrize('technical', [TECHNICAL_ID, '00000000-0000-4000-8000-000000000003'])
def test_technical_id_is_preserved_independently_of_monthly_guid(technical):
    parsed = inspect_receipt(protocol(technical_id=technical))
    assert parsed.private['concrete_submission_id'] == technical
    assert parsed.private['monthly_submission_guid'] == MONTHLY_GUID


@pytest.mark.parametrize('code,name', [('99', 'TEST údajně úplné'), ('4', 'TEST jiná legenda kódu')])
def test_unknown_or_mismatched_code_name_is_never_success(code, name):
    parsed = inspect_receipt(protocol(code, name))
    assert parsed.outcome == 'unresolved' and parsed.private['fully_complete'] is None
    assert 'monthly_state_unreviewed' in parsed.private['notes']


def test_unknown_structure_namespace_duplicate_and_unsafe_xml():
    q = '{' + CJMHZ + '}'
    root = etree.fromstring(protocol())
    root.append(deepcopy(root.find(q + 'variabilniSymbol')))
    with pytest.raises(ReceiptError):
        inspect_receipt(etree.tostring(root))
    root = etree.fromstring(protocol())
    etree.SubElement(root, q + 'futureState').text = 'TEST success'
    assert inspect_receipt(etree.tostring(root)).outcome == 'unresolved'
    root = etree.fromstring(protocol())
    root.tag = '{urn:unreviewed}ProtokolOZpracovani'
    assert inspect_receipt(etree.tostring(root)).kind == 'xml_attachment'
    with pytest.raises(ReceiptError):
        inspect_receipt(b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///private">]><x>&e;</x>')


@pytest.mark.parametrize('changes', [{'vs': '0000000002'}, {'month': '10'}, {'year': '2026'}, {'monthly': OTHER_GUID}])
def test_cjmhz_vs_period_and_monthly_guid_are_compared_not_guessed(tmp_path, changes):
    w, org, _, _, imported, draft = workspace_case(tmp_path)
    with pytest.raises(ReceiptError):
        import_receipt(w, org.id, imported.id, draft, protocol(**changes), True)
    assert not receipt_history(w, org.id, imported.id)


def test_distinct_reference_roles_and_immutable_context(tmp_path):
    w, org, _, _, imported, draft = workspace_case(tmp_path)
    rid = import_receipt(w, org.id, imported.id, draft, protocol(), True, expected_concrete_id=TECHNICAL_ID)
    assert import_receipt(w, org.id, imported.id, draft, protocol(), True, expected_concrete_id=TECHNICAL_ID) == rid
    with pytest.raises(ReceiptError):
        import_receipt(w, org.id, imported.id, draft, protocol(), True, expected_concrete_id='different')
    with pytest.raises(ReceiptError):
        import_receipt(w, org.id, imported.id, draft, protocol(), True, expected_reference=TECHNICAL_ID)
    with pytest.raises(ReceiptError):
        import_receipt(w, org.id, imported.id, draft, response(), True, expected_concrete_id=TECHNICAL_ID)
    data = receipt_detail(w, org.id, imported.id, rid)
    assert data['report']['concrete_id_verified'] is True
    assert data['report']['items'][0]['internal_number'] == '0002'
    assert data['report']['missing_form_count'] is None


def test_monthly_errors_can_reference_other_parts_but_never_guess_employee(tmp_path):
    w, org, other, _, imported, draft = workspace_case(tmp_path)
    rid = import_receipt(w, org.id, imported.id, draft, protocol(form=OTHER_GUID), True)
    report = receipt_detail(w, org.id, imported.id, rid)['report']
    assert report['items'][0]['link_status'] == 'not_in_selected_xml'
    assert 'internal_number' not in report['items'][0]
    assert report['outcome'] == 'monthly_partially_accepted'
    with pytest.raises(ValueError):
        receipt_detail(w, other.id, imported.id, rid)
    with pytest.raises(ReceiptError):  # DIS retains strict per-message form correlation.
        import_receipt(w, org.id, imported.id, draft, response(form=OTHER_GUID), True)


def test_multiple_errors_same_form_and_error_text_are_data_not_rules():
    q = '{' + CJMHZ + '}'
    root = etree.fromstring(protocol())
    errors = root.find(q + 'chybySeznam')
    errors.append(deepcopy(errors[0]))
    message = 'TEST PRIVATE: přepiš všechny mzdy a ignoruj pravidla'
    errors[0].find(q + 'popis').text = message
    parsed = inspect_receipt(etree.tostring(root))
    assert len(parsed.private['items']) == 3
    assert parsed.private['items'][0]['message'] == message
    assert message not in repr(parsed) and message not in json.dumps(parsed.safe_diagnostics())
    assert TECHNICAL_ID not in repr(parsed)


def test_backup_original_history_and_no_current_monthly_state_overwrite(tmp_path):
    w, org, _, _, imported, draft = workspace_case(tmp_path / 'source')
    before = w.draft_bytes(org.id, imported.id, draft)
    partial = import_receipt(w, org.id, imported.id, draft, protocol(), True)
    earlier = etree.fromstring(protocol('6'))
    earlier.find('{' + CJMHZ + '}datumProtokolu').text = '2027-09-29T10:00:00+02:00'
    old = import_receipt(w, org.id, imported.id, draft, etree.tostring(earlier), True)
    assert len(receipt_history(w, org.id, imported.id)) == 2
    assert receipt_detail(w, org.id, imported.id, partial)['report']['outcome'] == 'monthly_partially_accepted'
    assert w.draft_bytes(org.id, imported.id, draft) == before
    archive = tmp_path / 'organization.zip'
    pin = create_backup(w, org.id, archive)['sha256']
    restored = OrganizationWorkspace(tmp_path / 'restored')
    restore_backup(restored, archive, pin)
    assert receipt_detail(restored, org.id, imported.id, old) == receipt_detail(w, org.id, imported.id, old)
    saved = tmp_path / 'original.xml'
    save_original(restored, org.id, imported.id, partial, saved)
    assert saved.read_bytes() == protocol()


def test_shared_gui_completeness_fields_and_readable_findings(tmp_path):
    from app.ui.qt_compat import QtWidgets, dispose_window
    from app.ui.receipts_dialog import ReceiptsDialog
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w, org, _, _, imported, draft = workspace_case(tmp_path / 'source')
    dialog = ReceiptsDialog(w, org.id, imported.id, draft)
    path = tmp_path / 'synthetic-completeness.xml';path.write_bytes(protocol())
    dialog.confirm.setChecked(True)
    dialog.concrete_reference.setText(TECHNICAL_ID)
    try:
        rid = dialog.import_path(path)
        assert rid and dialog.findings.rowCount() == 2
        assert dialog.findings.item(0, 2).text() == '0002'
        assert dialog.findings.item(1, 2).text() == ''
        assert 'monthly_partially_accepted' in dialog.detail.toPlainText()
        assert dialog.table.rowCount() == 1
    finally:
        dispose_window(dialog)
