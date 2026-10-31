def main(argv=None) -> int:
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description="JMHZ Converter – pouze pracovní XML; finální export blokovaný.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--self-test", action="store_true", help="Izolovaný autotest pouze se syntetickými daty.")
    mode.add_argument("--demo", action="store_true", help="Otevřít syntetickou ukázku v novém datovém adresáři.")
    parser.add_argument("--report", type=Path, help="Nový soubor JSON pro výsledek autotestu.")
    parser.add_argument("--demo-directory", type=Path, help="Nový adresář pro syntetickou ukázku.")
    args = parser.parse_args(argv)
    if args.self_test:
        if args.report is None:
            parser.error("--self-test vyžaduje --report s novým cílovým souborem.")
        try:
            # Exclusive creation first: never truncate an existing user file.
            with args.report.open("x", encoding="utf-8") as output:
                try:
                    from app.platforms.preview import self_test
                    report = self_test()
                except Exception:
                    report = {"status": "failed", "data": "synthetic_only", "error": "synthetic_acceptance_failed", "final_export": "blocked"}
                json.dump(report, output, indent=2)
            return 0 if report["status"] == "passed" else 1
        except OSError:
            return 2
    if args.report is not None or (args.demo != (args.demo_directory is not None)):
        parser.error("--demo vyžaduje --demo-directory; --report patří pouze k --self-test.")
    from app.ui.qt_compat import QtCore, QtWidgets, QT_API, run, dispose_window
    from app.platforms.qt_startup import configure_qt
    QApplication = QtWidgets.QApplication
    from app.ui.organizations_window import OrganizationsWindow

    configure_qt(QtCore, QtWidgets, QT_API)
    application = QApplication.instance() or QApplication([])
    application.setApplicationName("JMHZ Converter")
    if args.demo:
        from app.platforms.preview import seed_workspace
        try:
            workspace, entries = seed_workspace(args.demo_directory)
        except Exception:
            QtWidgets.QMessageBox.critical(None, "Ukázku nelze otevřít", "Použijte nový zapisovatelný adresář. Existující data se nepřepisují.")
            return 2
        window = OrganizationsWindow(workspace.root)
        window.setWindowTitle("JMHZ Converter – SYNTETICKÁ UKÁZKA, bez skutečných údajů")
        window.period.setText(entries[0][0]["period"])
        window.organization_id = entries[0][1].id
        window.refresh()
    else:
        window = OrganizationsWindow()
    window.show()
    try:
        return run(application)
    finally:
        # Destroy widgets while QApplication and its native resources still exist.
        dispose_window(window)


if __name__ == "__main__":
    raise SystemExit(main())
