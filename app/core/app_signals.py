from PySide6.QtCore import QObject, Signal


class AppSignals(QObject):
    """Barramento simples de sinais da aplicação."""

    companies_changed = Signal(object)
    company_selected = Signal(object)
    page_requested = Signal(str)


app_signals = AppSignals()
