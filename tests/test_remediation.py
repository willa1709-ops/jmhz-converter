"""Full correction cycles with synthetic payroll and receipts only."""
from copy import deepcopy
from pathlib import Path

from lxml import etree
import pytest

from app.core.remediation import (cases, case_history, prepare_correction, register_dispatch,
    link_reply, close_after_review, reopen, link_finding, runs, reply_binding, add_note)
from app.core.receipts import import_receipt, receipt_detail, ReceiptError, CJMHZ
from app.core.models import SourceRow, SourceTable
from app.core.periods import Period
from app.core.backups import create_backup, restore_backup
from app.core.organizations import OrganizationWorkspace
from test_monthly_packet import workspace_case, employer_case
from test_employee_xml import OFFICIAL
from test_completeness_receipts import protocol, FORM_GUID, OTHER_GUID
from test_receipts import response

NOTE = 'Opravena vstupní data; ověřena konkrétní návaznost PP.'


def setup_case(tmp_path, dis=False):
    w, org, other, data, imported, draft = workspace_case(tmp_path)
    content = response(status='ERROR', body=('OK', 'OK', 'ERROR')) if dis else protocol()
    receipt = import_receipt(w, org.id, imported.id, draft, content, True)
    case = next(c for c in cases(w, org.id, imported.period) if c['snapshot']['form_guid'] == FORM_GUID)
    return w, org, other, data, imported, draft, receipt, case


def corrected(w, org, data, period, form=OTHER_GUID):
    row = dict(data[2], form_id=form)
    imported = w.import_table(org.id, period, SourceTable(tuple(row), (SourceRow(2, row),)))
    monthly, employer = employer_case(2027)
    eid = w.import_employer_table(org.id, imported.id, employer, monthly)
    draft, result = w.prepare_monthly_draft(org.id, imported.id, eid, data[1], data[4], OFFICIAL)
    assert result.xsd_valid
    return imported, draft


def state(w, org, period, case):
    return next(c['state'] for c in cases(w, org.id, period) if c['id'] == case['id'])


def changed_protocol(form=OTHER_GUID, reference='b'*32, code='TEST-0', timestamp='2027-10-02T12:00:00+02:00'):
    root = etree.fromstring(protocol(form=form, technical_id=reference))
    q = '{' + CJMHZ + '}'
    root.find(q+'datumProtokolu').text = timestamp
    root.find(q+'chybySeznam/'+q+'chyba/'+q+'kod').text = code
    return etree.tostring(root)


def test_automatic_reference_pairing_recurrence_then_manual_review_close(tmp_path):
    w, org, _, data, imported, _, receipt, case = setup_case(tmp_path)
    period = imported.period
    new, draft = corrected(w, org, data, period)
    run = prepare_correction(w, org.id, period, [case['id']], new.id, draft, NOTE, True)
    assert state(w, org, period, case) == 'prepared'
    register_dispatch(w, org.id, run, 'cjmhz_completeness', 'b'*32, True)
    assert state(w, org, period, case) == 'awaiting_reply'
    reply = import_receipt(w, org.id, new.id, draft, changed_protocol(), True)
    assert reply_binding(w, org.id, reply)['run_id'] == run
    assert state(w, org, period, case) == 'reported_again'
    with pytest.raises(ReceiptError):
        close_after_review(w, org.id, case['id'], run, new.id, reply, NOTE, True)
    # A second correction, with a new local run and another external message.
    form2 = '00000000-0000-4000-8000-000000000088'
    next_import, next_draft = corrected(w, org, data, period, form2)
    next_run = prepare_correction(w, org.id, period, [case['id']], next_import.id, next_draft, NOTE, True)
    register_dispatch(w, org.id, next_run, 'cjmhz_completeness', 'c'*32, True)
    absent = import_receipt(w, org.id, next_import.id, next_draft, changed_protocol(form2, 'c'*32, 'TEST-OTHER'), True)
    assert state(w, org, period, case) == 'review_required'  # No automatic closure.
    close_after_review(w, org.id, case['id'], next_run, next_import.id, absent, NOTE, True)
    assert state(w, org, period, case) == 'closed_by_review'
    history = case_history(w, org.id, case['id'])
    assert [h['event'] for h in history].count('correction_prepared') == 2
    assert history[-1]['receipt_id'] == absent and history[0]['receipt_id'] == receipt
    assert receipt_detail(w, org.id, next_import.id, absent)['report']['submission_ready'] is False


def test_dis_acceptance_is_not_resolution_and_late_dis_does_not_override_cjmhz(tmp_path):
    w, org, _, data, imported, _, _, case = setup_case(tmp_path, dis=True)
    new, draft = corrected(w, org, data, imported.period)
    run = prepare_correction(w, org.id, imported.period, [case['id']], new.id, draft, NOTE, True)
    register_dispatch(w, org.id, run, 'dis_processing_result', 'TEST-MESSAGE-1', True)
    reply = import_receipt(w, org.id, new.id, draft, response(form=OTHER_GUID), True)
    assert state(w, org, imported.period, case) == 'dis_accepted'
    with pytest.raises(ReceiptError):
        close_after_review(w, org.id, case['id'], run, new.id, reply, NOTE, True)
    register_dispatch(w, org.id, run, 'cjmhz_completeness', 'b'*32, True)
    cj = import_receipt(w, org.id, new.id, draft, changed_protocol(code='TEST-OTHER'), True)
    assert state(w, org, imported.period, case) == 'review_required'
    late = etree.fromstring(response(form=OTHER_GUID));late.set('errMsg','TEST additional version')
    late_id = import_receipt(w, org.id, new.id, draft, etree.tostring(late), True)
    assert state(w, org, imported.period, case) == 'review_required'
    assert case_history(w, org.id, case['id'])[-1]['event'] == 'historical_reply'
    assert late_id != reply and cj


def test_wrong_reference_scope_and_cross_organization_never_link(tmp_path):
    w, org, other, data, imported, draft, _, case = setup_case(tmp_path)
    with pytest.raises(ValueError):
        prepare_correction(w, other.id, imported.period, [case['id']], imported.id, draft, NOTE, True)
    with pytest.raises(ReceiptError):
        prepare_correction(w, org.id, Period(2027, 10), [case['id']], imported.id, draft, NOTE, True)
    new, new_draft = corrected(w, org, data, imported.period)
    run = prepare_correction(w, org.id, imported.period, [case['id']], new.id, new_draft, NOTE, True)
    register_dispatch(w, org.id, run, 'cjmhz_completeness', 'b'*32, True)
    wrong = import_receipt(w, org.id, new.id, new_draft, changed_protocol(reference='x'*32), True)
    assert reply_binding(w, org.id, wrong) is None
    assert state(w, org, imported.period, case) == 'awaiting_reply'
    with pytest.raises(ReceiptError):
        link_reply(w, org.id, run, imported.id, case['source_receipt_id'], NOTE, True)
    with pytest.raises(ValueError):
        case_history(w, other.id, case['id'])


def test_retrospective_manual_link_is_explicit_and_ambiguous_targets_need_review(tmp_path):
    w, org, _, data, imported, _, _, _ = setup_case(tmp_path)
    case = next(c for c in cases(w, org.id, imported.period) if not c['snapshot']['target'])
    new, draft = corrected(w, org, data, imported.period)
    run = prepare_correction(w, org.id, imported.period, [case['id']], new.id, draft, NOTE, True)
    content = changed_protocol(code='TEST-1')
    reply = import_receipt(w, org.id, new.id, draft, content, True)
    register_dispatch(w, org.id, run, 'cjmhz_completeness', 'b'*32, True)  # Later input isn't proof of prior linkage.
    assert reply_binding(w, org.id, reply) is None
    link_reply(w, org.id, run, new.id, reply, NOTE, True)
    assert reply_binding(w, org.id, reply)['association'] == 'manual_review'
    assert state(w, org, imported.period, case) == 'review_required'
    link_finding(w, org.id, case['id'], run, new.id, reply, 0, NOTE, True)
    assert state(w, org, imported.period, case) == 'reported_again'
    assert case_history(w, org.id, case['id'])[-1]['event'] == 'manual_occurrence_link'


def test_old_response_does_not_erase_new_recurrence_and_late_errors_reopen_review(tmp_path):
    w, org, _, data, imported, _, _, case = setup_case(tmp_path)
    new, draft = corrected(w, org, data, imported.period)
    run = prepare_correction(w, org.id, imported.period, [case['id']], new.id, draft, NOTE, True)
    register_dispatch(w, org.id, run, 'cjmhz_completeness', 'b'*32, True)
    first = import_receipt(w, org.id, new.id, draft, changed_protocol(code='TEST-OTHER'), True)
    close_after_review(w, org.id, case['id'], run, new.id, first, NOTE, True)
    newer = import_receipt(w, org.id, new.id, draft, changed_protocol(timestamp='2027-10-03T12:00:00+02:00'), True)
    assert state(w, org, imported.period, case) == 'reported_again'
    with pytest.raises(ReceiptError):
        close_after_review(w, org.id, case['id'], run, new.id, first, NOTE, True)
    older = import_receipt(w, org.id, new.id, draft, changed_protocol(code='TEST-OTHER', timestamp='2027-10-01T12:00:00+02:00'), True)
    assert state(w, org, imported.period, case) == 'reported_again'
    assert case_history(w, org.id, case['id'])[-1]['event'] == 'historical_reply'
    assert older != newer


def test_history_idempotency_backup_restore_and_no_automatic_payroll_change(tmp_path):
    w, org, _, data, imported, draft, receipt, case = setup_case(tmp_path/'source')
    original = w.draft_bytes(org.id, imported.id, draft)
    count = len(cases(w, org.id, imported.period))
    assert import_receipt(w, org.id, imported.id, draft, protocol(), True) == receipt
    assert len(cases(w, org.id, imported.period)) == count
    new, corrected_draft = corrected(w, org, data, imported.period)
    run = prepare_correction(w, org.id, imported.period, [case['id']], new.id, corrected_draft, NOTE, True)
    register_dispatch(w, org.id, run, 'cjmhz_completeness', 'b'*32, True)
    reply = import_receipt(w, org.id, new.id, corrected_draft, changed_protocol(), True)
    register_dispatch(w, org.id, run, 'cjmhz_completeness', 'b'*32, True)
    events = case_history(w, org.id, case['id'])
    assert w.draft_bytes(org.id, imported.id, draft) == original
    backup = tmp_path/'backup.zip';pin = create_backup(w, org.id, backup)['sha256']
    restored = OrganizationWorkspace(tmp_path/'restored');restore_backup(restored, backup, pin)
    assert case_history(restored, org.id, case['id']) == events
    assert runs(restored, org.id, imported.period)[0]['id'] == run
    assert reply_binding(restored, org.id, reply)['run_id'] == run


def test_no_note_or_confirmation_cannot_manufacture_fix_or_closure(tmp_path):
    w, org, _, data, imported, draft, _, case = setup_case(tmp_path)
    with pytest.raises(ReceiptError):
        prepare_correction(w, org.id, imported.period, [case['id']], imported.id, draft, NOTE)
    with pytest.raises(ReceiptError):
        prepare_correction(w, org.id, imported.period, [case['id']], imported.id, draft, '', True)
    with pytest.raises(ReceiptError):
        register_dispatch(w, org.id, 'missing', 'cjmhz_completeness', 'x', False)
    reopen(w, org.id, case['id'], NOTE)
    assert case_history(w, org.id, case['id'])[-1]['event'] == 'reopened_by_user'
    add_note(w, org.id, case['id'], NOTE)
    assert case_history(w, org.id, case['id'])[-1]['note'] == NOTE
    assert state(w, org, imported.period, case) == 'open'


def test_manual_occurrence_prevents_false_closure_and_guid_rebinding_stays_audited(tmp_path):
    w, org, _, data, imported, _, _, _ = setup_case(tmp_path)
    case = next(c for c in cases(w, org.id, imported.period) if not c['snapshot']['target'])
    new, draft = corrected(w, org, data, imported.period)
    run = prepare_correction(w, org.id, imported.period, [case['id']], new.id, draft, NOTE, True)
    reply = import_receipt(w, org.id, new.id, draft, changed_protocol(code='TEST-1'), True)
    link_reply(w, org.id, run, new.id, reply, NOTE, True)
    link_finding(w, org.id, case['id'], run, new.id, reply, 0, NOTE, True)
    with pytest.raises(ReceiptError):
        close_after_review(w, org.id, case['id'], run, new.id, reply, NOTE, True)
    newer, newer_draft = corrected(w, org, data, imported.period, '00000000-0000-4000-8000-000000000077')
    next_run = prepare_correction(w, org.id, imported.period, [case['id']], newer.id, newer_draft, NOTE, True)
    register_dispatch(w, org.id, next_run, 'cjmhz_completeness', 'c'*32, True)
    import_receipt(w, org.id, newer.id, newer_draft, changed_protocol(form='00000000-0000-4000-8000-000000000077', reference='c'*32, code='TEST-1'), True)
    assert state(w, org, imported.period, case) == 'reported_again'


def test_older_run_response_and_duplicate_reference_cannot_replace_current_attempt(tmp_path):
    w, org, _, data, imported, _, _, case = setup_case(tmp_path)
    first_import, first_draft = corrected(w, org, data, imported.period)
    first_run = prepare_correction(w, org.id, imported.period, [case['id']], first_import.id, first_draft, NOTE, True)
    register_dispatch(w, org.id, first_run, 'cjmhz_completeness', 'b'*32, True)
    next_import, next_draft = corrected(w, org, data, imported.period, '00000000-0000-4000-8000-000000000077')
    next_run = prepare_correction(w, org.id, imported.period, [case['id']], next_import.id, next_draft, NOTE, True)
    with pytest.raises(ReceiptError):
        register_dispatch(w, org.id, next_run, 'cjmhz_completeness', 'b'*32, True)
    reply = import_receipt(w, org.id, first_import.id, first_draft, changed_protocol(), True)
    assert state(w, org, imported.period, case) == 'prepared'
    assert case_history(w, org.id, case['id'])[-1]['event'] == 'historical_reply'
    with pytest.raises(ReceiptError):
        close_after_review(w, org.id, case['id'], first_run, first_import.id, reply, NOTE, True)


def test_repeated_errors_without_unique_match_require_review(tmp_path):
    w, org, _, data, imported, _, _, case = setup_case(tmp_path)
    new, draft = corrected(w, org, data, imported.period)
    run = prepare_correction(w, org.id, imported.period, [case['id']], new.id, draft, NOTE, True)
    register_dispatch(w, org.id, run, 'cjmhz_completeness', 'b'*32, True)
    root = etree.fromstring(changed_protocol());errors = root.find('{'+CJMHZ+'}chybySeznam');errors.append(deepcopy(errors[0]))
    import_receipt(w, org.id, new.id, draft, etree.tostring(root), True)
    assert state(w, org, imported.period, case) == 'review_required'


def test_private_gui_status_and_history_are_available_without_changing_payroll(tmp_path):
    from app.ui.qt_compat import QtWidgets, dispose_window
    from app.ui.remediation_dialog import RemediationDialog
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w, org, _, _, imported, draft, _, case = setup_case(tmp_path)
    original = w.draft_bytes(org.id, imported.id, draft)
    dialog = RemediationDialog(w, org.id, imported.period)
    try:
        assert dialog.table.rowCount() == 2
        row = next(i for i, c in enumerate(dialog.records) if c['id'] == case['id'])
        dialog.table.selectRow(row);dialog.show_case(row, 0)
        assert 'Otevřeno' in dialog.table.item(row, 3).text()
        assert 'historie' in dialog.history.toPlainText()
        assert w.draft_bytes(org.id, imported.id, draft) == original
        dialog.show();app.processEvents();dialog.resize(750, 600);app.processEvents()
        assert dialog.minimumSizeHint().width() <= 750
        assert dialog.scroll.widgetResizable()
    finally:
        dispose_window(dialog)


def test_multiple_findings_share_one_correction_and_reference(tmp_path):
    w, org, _, data, imported, draft = workspace_case(tmp_path)
    root = etree.fromstring(protocol(form=None));q = '{'+CJMHZ+'}'
    for error in root.find(q+'chybySeznam'):
        error.find(q+'castPodani').text = 'pvpoj'
    import_receipt(w, org.id, imported.id, draft, etree.tostring(root), True)
    selected = cases(w, org.id, imported.period)
    new, changed_draft = corrected(w, org, data, imported.period)
    run = prepare_correction(w, org.id, imported.period, [c['id'] for c in selected], new.id, changed_draft, NOTE, True)
    register_dispatch(w, org.id, run, 'cjmhz_completeness', 'b'*32, True, note=NOTE)
    root.find(q+'idKonkretnihoPodani').text = 'b'*32
    reply = import_receipt(w, org.id, new.id, changed_draft, etree.tostring(root), True)
    assert all(state(w, org, imported.period, c) == 'reported_again' for c in selected)
    assert len(runs(w, org.id, imported.period)) == 1
    assert reply_binding(w, org.id, reply)['run_id'] == run
    assert NOTE in next(e['note'] for e in case_history(w, org.id, selected[0]['id']) if e['event']=='external_dispatch_recorded')


def test_old_form_guid_in_monthly_protocol_is_still_a_recurrence(tmp_path):
    w, org, _, data, imported, _, _, case = setup_case(tmp_path)
    new, draft = corrected(w, org, data, imported.period)
    run = prepare_correction(w, org.id, imported.period, [case['id']], new.id, draft, NOTE, True)
    register_dispatch(w, org.id, run, 'cjmhz_completeness', 'b'*32, True)
    reply = import_receipt(w, org.id, new.id, draft, changed_protocol(form=FORM_GUID), True)
    assert state(w, org, imported.period, case) == 'reported_again'
    with pytest.raises(ReceiptError):
        close_after_review(w, org.id, case['id'], run, new.id, reply, NOTE, True)


def test_top_level_dis_error_without_items_is_tracked_without_guessing_scope(tmp_path):
    w, org, _, _, imported, draft = workspace_case(tmp_path)
    root = etree.fromstring(response(status='ERROR'));root.remove(root[0]);root.set('errNumber','TEST-HEADER');root.set('errMsg','TEST obecná zpráva bez určené části')
    import_receipt(w, org.id, imported.id, draft, etree.tostring(root), True)
    registered = cases(w, org.id, imported.period)
    assert len(registered) == 1
    assert registered[0]['snapshot']['target'] is None
    assert registered[0]['snapshot']['part'] == 'top_level'


def test_manual_link_cannot_conflate_two_known_employments(tmp_path):
    w, org, _, data, imported, _, _, case = setup_case(tmp_path)
    first = dict(data[2], form_id=OTHER_GUID, target_10286='200', target_10344='200')
    second_guid = '00000000-0000-4000-8000-000000000077'
    second = dict(first, internal_number='0010', id_ppv='2', form_id=second_guid)
    new = w.import_table(org.id, imported.period, SourceTable(tuple(first), (SourceRow(2, first), SourceRow(3, second))))
    monthly, employer = employer_case(2027)
    eid = w.import_employer_table(org.id, new.id, employer, monthly)
    draft, result = w.prepare_monthly_draft(org.id, new.id, eid, data[1], data[4], OFFICIAL)
    assert result.xsd_valid
    run = prepare_correction(w, org.id, imported.period, [case['id']], new.id, draft, NOTE, True)
    register_dispatch(w, org.id, run, 'cjmhz_completeness', 'b'*32, True)
    reply = import_receipt(w, org.id, new.id, draft, changed_protocol(form=second_guid), True)
    assert state(w, org, imported.period, case) == 'review_required'
    with pytest.raises(ReceiptError):
        link_finding(w, org.id, case['id'], run, new.id, reply, 0, NOTE, True)
