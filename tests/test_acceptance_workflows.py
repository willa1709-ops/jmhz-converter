"""Synthetic acceptance regressions, shared Qt5/Qt6 workflow."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")
import pytest
from app.core.backups import create_backup
from app.core.periods import Period
from app.ui import organizations_window as ui
from app.ui.qt_compat import QtWidgets, dispose_window
from test_employee_xml import case
from app.core.models import SourceRow, SourceTable

_APPLICATION = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def window(tmp_path, monkeypatch):
    messages = []
    for name in ('warning', 'information'):
        monkeypatch.setattr(getattr(QtWidgets, 'QMessageBox'), name,
                            lambda parent, title, message: messages.append((title, message)))
    w = ui.OrganizationsWindow(tmp_path / 'workspace')
    w.messages = messages
    yield w
    dispose_window(w)


def setup_import(w):
    data = case(2027)
    org = w.workspace.register('Synthetic', '00000001', '0000000001')
    w.workspace.set_profile(data[0])
    imported = w.workspace.import_table(org.id, data[3].period, SourceTable(tuple(data[2]), (SourceRow(2, data[2]),)))
    w.period.setText(imported.period.iso)
    w.select_organization(org.id)
    return data, org, imported


def test_restore_selected_path_hash_and_visible_outcomes(window, tmp_path, monkeypatch):
    data, org, imported = setup_import(window)
    archive = tmp_path / 'Žluťoučká záloha.zip'
    pin = create_backup(window.workspace, org.id, archive)['sha256']
    from app.core.organizations import OrganizationWorkspace
    window.workspace = OrganizationWorkspace(tmp_path / 'empty')
    window.organization_id = None
    monkeypatch.setattr(ui.QFileDialog, 'getOpenFileName', lambda *args: (str(archive), 'ZIP'))
    monkeypatch.setattr(ui.QInputDialog, 'getText', lambda *args: ('0' * 64, True))
    window.choose_restore()
    assert window.messages[-1][0] == 'Obnova selhala'
    assert not window.workspace.organizations()
    monkeypatch.setattr(ui.QInputDialog, 'getText', lambda *args: (' ' + pin + ' ', True))
    window.choose_restore()
    assert window.messages[-1][0] == 'Obnova dokončena'
    assert window.workspace.get_import(org.id, imported.id).source == imported.source
    window.choose_restore()
    assert window.messages[-1][0] == 'Obnova selhala'
    assert len(window.workspace.organizations()) == 1


def test_explicit_versions_zero_one_are_separate_from_plans_and_months(window):
    data, org, imported = setup_import(window)
    window.check()
    assert not window.analysis.issues
    assert not window.workspace.history(org.id, imported.period)['versions']
    for revision in (0, 1):
        window.check()
        window.revision.setValue(revision)
        window.record_version()
        assert window.workspace.overview(imported.period)[0]['last_revision'] == revision
    assert [r['revision_index'] for r in window.workspace.history(org.id, imported.period)['versions']] == [0, 1]
    other = window.workspace.register('Other', '00000002', '0000000002')
    assert not window.workspace.history(other.id, imported.period)['versions']
    assert not window.workspace.history(org.id, Period.parse('2027-12'))['versions']
    from app.core.submission_plans import history
    assert not history(window.workspace, org.id, imported.period)


def test_plan_missing_context_draft_valid_context_and_setup_exception(window, monkeypatch):
    window.choose_plan()
    assert window.messages[-1][0] == 'Plán nelze otevřít'
    data, org, imported = setup_import(window)
    window.choose_plan()
    assert 'pracovní XML' in window.messages[-1][1]
    window.prepare_employee_xml(data[1], data[4])
    assert window.draft_id
    opened = []
    monkeypatch.setattr(window, 'open_plan_dialog', lambda: opened.append(True))
    window.choose_plan()
    assert opened == [True]
    def fail():
        raise OSError('synthetic storage failure')
    monkeypatch.setattr(window, 'open_plan_dialog', fail)
    window.choose_plan()
    assert window.messages[-1][0] == 'Plán nelze otevřít'
    window.period.setText('2027-12')
    window.choose_plan()
    assert opened == [True]


def test_plan_dialog_saves_regular_plan_and_reports_duplicate(window, monkeypatch):
    data, org, imported = setup_import(window)
    window.prepare_employee_xml(data[1], data[4])
    xml = window.workspace.draft_bytes(org.id, imported.id, window.draft_id)
    monkeypatch.setattr(ui, 'run', lambda dialog: ui.enum(ui.QDialog, 'DialogCode', 'Accepted'))
    window.choose_plan()
    assert window.messages[-1][0] == 'Plán uložen'
    from app.core.submission_plans import history
    assert history(window.workspace, org.id, imported.period)[0]['mode'] == 'R'
    window.choose_plan()
    assert window.messages[-1][0] == 'Plán neuložen'
    assert len(history(window.workspace, org.id, imported.period)) == 1
    assert window.workspace.draft_bytes(org.id, imported.id, window.draft_id) == xml
