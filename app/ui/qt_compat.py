"""Small binding adapter: shared workflow for Qt6 and the Qt5 test candidate."""
try:
    from PySide6 import QtCore, QtWidgets
    QT_API = "PySide6"
except ModuleNotFoundError as error:
    if error.name != "PySide6":
        raise
    from PySide2 import QtCore, QtWidgets
    QT_API = "PySide2"


def enum(owner, group, name):
    return getattr(getattr(owner, group, owner), name)


def run(obj):
    method = getattr(obj, "exec", None) or obj.exec_
    return method()


def dispose_window(window):
    window.close()
    window.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, enum(QtCore.QEvent, "Type", "DeferredDelete"))
