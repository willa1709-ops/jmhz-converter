def main() -> int:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QCoreApplication, QEvent
    from app.ui.organizations_window import OrganizationsWindow

    application = QApplication.instance() or QApplication([])
    application.setApplicationName("JMHZ Converter")
    window = OrganizationsWindow()
    window.show()
    try:
        return application.exec()
    finally:
        # Destroy widgets while QApplication and its native resources still exist.
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__":
    raise SystemExit(main())
