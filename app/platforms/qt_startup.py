"""Qt startup policy outside the shared conversion core."""
import os


def configure_qt(QtCore, QtWidgets, binding):
    if os.name == "nt" and binding == "PySide2" and QtWidgets.QApplication.instance() is None:
        # This application uses raster table/text widgets, not OpenGL/QtQuick.
        # Avoid Qt's optional ANGLE/shader runtimes from the Win32 wheel.
        os.environ["QT_OPENGL"] = "desktop"
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_ForceRasterWidgets, True)
