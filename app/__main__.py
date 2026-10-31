def main() -> int:
    from app.ui.qt_compat import QtWidgets, run, dispose_window
    QApplication = QtWidgets.QApplication
    from app.ui.organizations_window import OrganizationsWindow

    application = QApplication.instance() or QApplication([])
    application.setApplicationName("JMHZ Converter")
    window = OrganizationsWindow()
    window.show()
    try:
        return run(application)
    finally:
        # Destroy widgets while QApplication and its native resources still exist.
        dispose_window(window)


if __name__ == "__main__":
    raise SystemExit(main())
