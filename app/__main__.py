def main() -> int:
    from PySide6.QtWidgets import QApplication
    from app.ui.organizations_window import OrganizationsWindow

    application = QApplication.instance() or QApplication([])
    application.setApplicationName("JMHZ Converter")
    window = OrganizationsWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
