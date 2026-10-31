import os
from pathlib import Path
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from app.ui.main_window import MainWindow


@pytest.fixture(scope="module", autouse=True)
def application_lifetime():
    """Keep one QApplication alive until all widget tests have finished."""
    application = QApplication.instance() or QApplication([])
    yield application
    application.closeAllWindows()
    application.processEvents()


@pytest.fixture(autouse=True)
def dispose_widgets(application_lifetime):
    from PySide6.QtCore import QCoreApplication, QEvent
    yield
    for widget in application_lifetime.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application_lifetime.processEvents()


def test_import_mapping_check_sums_and_error_navigation():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_path(Path(__file__).parents[1] / "config/example.csv")
    app.processEvents()
    assert window.preview.rowCount() == 2
    assert window.preview.item(0, 0).text() == "000001"
    assert "60000.30" in window.sums.toPlainText()
    window.period.setText("2026-08")
    window.check()
    target = next(i for i, f in enumerate(window.findings) if f.row == 2 and f.field == "period")
    window.goto_row(target, 0)
    assert window.tabs.currentIndex() == 1
    assert window.preview.currentRow() == 0
    assert window.tabs.count() == 8
    window.close()


def test_manual_definition_import_compare_and_reopen(tmp_path):
    from app.ui.definitions_page import DefinitionsPage
    app = QApplication.instance() or QApplication([])
    page = DefinitionsPage(tmp_path / "definitions.sqlite3")
    assert not page.path().exists()
    page.compare()
    assert "Nejprve" in page.summary.text()
    page.source.setText("https://example.invalid/synthetic.xsd")
    path = tmp_path / "synthetic.xsd"
    for version, type_ in [("v1", "string"), ("v2", "decimal")]:
        page.version.setText(version)
        path.write_text(f'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:element name="synthetic" type="xs:{type_}"/></xs:schema>')
        page.import_path(path)
    page.before.setCurrentIndex(0)
    page.after.setCurrentIndex(1)
    page.compare()
    app.processEvents()
    assert page.inventory.rowCount() == 2
    assert page.inventory.item(0, 1).text() == "NEOVĚŘENO"
    assert page.changes.rowCount() == 1
    assert "decimal" in page.changes.item(0, 3).text()
    reopened = DefinitionsPage(page.path())
    assert reopened.inventory.rowCount() == 2
    reopened.close()
    page.close()


def test_codelist_and_methodology_import_ui(tmp_path):
    from app.ui.definitions_page import DefinitionsPage
    app = QApplication.instance() or QApplication([])
    page = DefinitionsPage(tmp_path / "definitions.sqlite3")
    page.version.setText("synthetic-1")
    for kind, filename, content in [("codelist", "codes.csv", "code;name\n01;Synthetic\n"),
                                     ("methodology", "method.txt", "Synthetic instructions")]:
        path = tmp_path / filename
        path.write_text(content)
        page.kind.setCurrentIndex(page.kind.findData(kind))
        page.source.setText(f"https://example.invalid/{filename}")
        page.import_path(path)
    app.processEvents()
    assert page.inventory.rowCount() == 2
    assert page.inventory.item(0, 2).text() == "CSV načteno"
    assert page.inventory.item(1, 2).text() == "Text načten"
    assert page.inventory.item(0, 1).text() == page.inventory.item(1, 1).text() == "NEOVĚŘENO"
    page.close()


def test_ui_xml_validation_uses_registered_official_bundle(tmp_path):
    import json
    from lxml import etree
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    bundle = json.loads((window.official_root / "bundles.json").read_text())["bundles"][0]
    window.bundle_choice.setCurrentIndex(window.bundle_choice.findData(bundle["id"]))
    ns = bundle["namespace"]
    root = etree.Element(f"{{{ns}}}jmhz", nsmap={None: ns})
    header = etree.SubElement(root, f"{{{ns}}}hlavicka")
    for name, value in [("idPodani", "00000000-0000-4000-8000-000000000001"), ("typPodani", "R"),
                        ("variabilniSymbol", "0000000000"), ("mesic", "1"), ("rok", "2026"),
                        ("datumVyplneni", "2026-10-30T12:00:00")]:
        etree.SubElement(header, f"{{{ns}}}{name}").text = value
    path = tmp_path / "synthetic.xml"
    path.write_bytes(etree.tostring(root))
    window.validate_xml_path(path)
    assert "XSD: PROŠLO" in window.xml_validation_result.toPlainText()
    assert "K podání: NE" in window.xml_validation_result.toPlainText()
    path.write_bytes(b"<invalid/>")
    window.validate_xml_path(path)
    assert "XSD: NEPROŠLO" in window.xml_validation_result.toPlainText()
    window.close()


def test_ui_prepares_employee_draft_and_clears_it_on_missing_values(tmp_path):
    import json
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    root = Path(__file__).parents[1]
    source = tmp_path / "synthetic.csv"
    source.write_text("form_id;period;activity_code;ik_mpsv;id_ppv;tax_income_10535;tax_income_10555\n"
                      "00000000-0000-4000-8000-000000000002;2027-01;11;0000000000;000001;123;0\n")
    parameters = tmp_path / "parameters.json"
    parameters.write_text(json.dumps({"submission_id": "00000000-0000-4000-8000-000000000001",
                                      "employer_variable_symbol": "0000000000", "year": 2027, "month": 1,
                                      "filled_at": "2026-10-30T12:00:00"}))
    profile = root / "config/conversion/jiny-prijem-2027.json"
    window.load_path(source)
    window.prepare_conversion_paths(profile, parameters)
    app.processEvents()
    assert window.generated_draft is not None
    assert "jinyPrijem" in window.draft_preview.toPlainText()
    assert "XSD: PROŠLO" in window.conversion_status.text()
    source.write_text(source.read_text().replace(";123;0", ";;0"))
    window.load_path(source)
    assert window.generated_draft is None
    window.prepare_conversion_paths(profile, parameters)
    assert window.generated_draft is None
    assert "Chybí hodnota" in window.draft_preview.toPlainText()
    assert "XSD: NEPROŠLO" in window.conversion_status.text()
    window.close()


def test_numbered_payroll_ui_calculates_primary_and_invalidates_context_without_logging_identifiers():
    from app.ui.payroll_dialog import PayrollDialog
    from app.core.models import SourceRow, SourceTable
    app = QApplication.instance() or QApplication([])
    row = {"internal_number": "10", "period": "26-09", "oic": "1234567890", "rc": "900101/1234",
           "form_id": "", "id_ppv": "", "activity_code": "", "p100": "100.10", "p110": "0.2", "p120": "0.01", "p190": "100.29", "p200": "0"}
    second = dict(row, internal_number="0002")
    source = SourceTable(tuple(row), (SourceRow(2, row), SourceRow(3, second)))
    dialog = PayrollDialog(source)
    dialog.load_profile_path(Path(__file__).parents[1] / "config/payroll/numbered.template.json")
    dialog.period.setText("26-09")
    dialog.analyze()
    assert dialog.errors.rowCount() == 0
    assert dialog.rows.item(0, 4).text() == "ne"
    assert dialog.rows.item(1, 4).text() == "ano"
    assert dialog.rows.item(1, 5).text() == "100.29"
    dialog.revision.setValue(1)
    assert dialog.result is None and dialog.rows.rowCount() == 0
    dialog.period.setText("26-10")
    dialog.analyze()
    assert any(i.code == "period_mismatch" for i in dialog.result.issues)
    second["rc"] = "910101/1234"
    dialog.period.setText("26-09")
    dialog.analyze()
    assert all(r.primary_pp is None for r in dialog.result.rows)
    diagnostics = " ".join(dialog.errors.item(i, j).text() for i in range(dialog.errors.rowCount()) for j in range(dialog.errors.columnCount()))
    assert row["oic"] not in diagnostics and row["rc"] not in diagnostics and second["rc"] not in diagnostics
    app.processEvents()
    dialog.close()


def test_organizations_dashboard_isolates_context_history_and_old_tools(tmp_path):
    import json
    from app.ui.organizations_window import OrganizationsWindow
    from app.core.models import SourceRow, SourceTable
    from app.core.periods import Period
    app = QApplication.instance() or QApplication([])
    window = OrganizationsWindow(tmp_path / "workspace")
    window.period.setText("26-09")
    a = window.workspace.register("Synthetic A", "00000001", "0000000001")
    b = window.workspace.register("Synthetic B", "00000002", "0000000002")
    p = json.loads((Path(__file__).parents[1] / "config/payroll/numbered.template.json").read_text())
    p["metadata"].update(employment_type={"column": "kind"}, income_amount={"item": "190"})
    window.workspace.set_profile(p)
    row = {"internal_number": "2", "period": "26-09", "oic": "1234567890", "rc": "", "form_id": "", "id_ppv": "1", "activity_code": "11",
           "p100": "100", "p110": "10", "p120": "5", "p190": "105", "p200": "0", "kind": "HPP"}
    source_a = SourceTable(tuple(row), (SourceRow(2, row), SourceRow(3, dict(row, internal_number="10"))))
    source_b = SourceTable(tuple(row), (SourceRow(2, dict(row, internal_number="10")),))
    window.workspace.import_table(a.id, Period(2026, 9), source_a)
    window.workspace.import_table(b.id, Period(2026, 9), source_b)
    window.refresh()
    assert window.organizations.rowCount() == 2
    window.select_organization(a.id)
    window.check()
    assert window.rows.rowCount() == 2
    assert window.rows.item(1, 4).text() == "ne"
    window.open_tools()
    tools = window.tools
    assert tools.source == source_a and not tools.xml_scenario_allowed
    window.draft.setPlainText("private synthetic preview")
    window.select_organization(b.id)
    assert window.tools is None and not tools.isVisible()
    assert window.analysis is None and window.rows.rowCount() == 0 and not window.draft.toPlainText()
    window.check()
    assert window.rows.rowCount() == 1 and window.rows.item(0, 4).text() == "ano"
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QTabWidget, QPlainTextEdit
    history_preview = []
    def inspect_history():
        dialog = app.activeModalWidget()
        try:
            tabs = dialog.findChild(QTabWidget)
            checks = tabs.widget(0)
            checks.cellClicked.emit(0, 0)
            history_preview.append((checks.rowCount(), dialog.findChild(QPlainTextEdit).toPlainText()))
        finally:
            dialog.accept()
    QTimer.singleShot(0, inspect_history)
    window.open_audit_history()
    assert history_preview[0][0] == 1 and "105" in history_preview[0][1]
    assert "1234567890" not in history_preview[0][1]
    window.record_version()
    assert window.revision.value() == 1
    assert window.organizations.item(1, 6).text() == "0"
    window.period.setText("26-10")
    assert window.imported is None and window.analysis is None
    assert window.rows.rowCount() == 0 and window.import_history.count() == 0
    window.period.setText("26-09")
    window.select_organization(a.id)
    csv = tmp_path / "repeat.csv"
    csv.write_text(";".join(row) + "\n" + ";".join(row.values()) + "\n")
    window.import_path(csv)
    assert window.imported.import_index == 1
    assert window.import_history.count() == 2
    assert window.workspace.overview(Period(2026, 9))[1]["pp_count"] == 1
    app.processEvents()
    window.close()


def test_employee_xml_ui_shows_real_payload_and_clears_it_between_organizations(tmp_path):
    from test_employee_xml import case
    from app.ui.organizations_window import OrganizationsWindow
    from app.core.models import SourceTable, SourceRow
    app = QApplication.instance() or QApplication([])
    numbered, profile, row, context, parameters = case(2027)
    window = OrganizationsWindow(tmp_path / "workspace")
    org = window.workspace.register("Synthetic A", "00000001", parameters["employer_variable_symbol"])
    other = window.workspace.register("Synthetic B", "00000002", "0000000002")
    window.workspace.set_profile(numbered)
    window.workspace.import_table(org.id, context.period, SourceTable(tuple(row), (SourceRow(2, row),)))
    window.period.setText(context.period.iso)
    window.refresh()
    window.select_organization(org.id)
    window.prepare_employee_xml(profile, parameters)
    assert "bezPriznaku" in window.draft.toPlainText()
    assert "XSD: PROŠLO" in window.status.text() and "Finální export NE" in window.status.text()
    assert window.errors.rowCount() > 0
    window.select_organization(other.id)
    assert window.draft_id is None and not window.draft.toPlainText()
    app.processEvents()
    window.close()
