def main() -> int:
    from PySide6.QtWidgets import QApplication
    from app.ui.main_window import MainWindow

    application = QApplication.instance() or QApplication([])
    application.setApplicationName("JMHZ Converter")
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
