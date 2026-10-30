import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from app.ui.main_window import MainWindow


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
