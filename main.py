"""
Aplicação principal - XML Downloader
Sistema inteligente de download de XMLs para escritório contábil
"""
import sys
from typing import NoReturn

from PySide6.QtWidgets import QApplication

from app.db import DatabaseConnection
from app.ui import (
    MainWindow, EmpresasPage, DownloaderPage, DashboardPage,
    LogsPage, RelatoriosPage, ManifestacaoPage, XMLsPage, ConfiguracoesPage, LicencasPage, AjudaPage, LimpezaBackupPage
)
from app.utils.logger import log


def main() -> NoReturn:
    """Função principal da aplicação"""

    DatabaseConnection.initialize()
    log.info("Aplicação iniciada")

    app = QApplication(sys.argv)
    window = MainWindow()

    page_factories = {
        "dashboard": DashboardPage,
        "empresas": EmpresasPage,
        "download": DownloaderPage,
        "xmls": XMLsPage,
        "manifestacao": ManifestacaoPage,
        "logs": LogsPage,
        "relatorios": RelatoriosPage,
        "limpeza_backup": LimpezaBackupPage,
        "configuracoes": ConfiguracoesPage,
        "licencas": LicencasPage,
        "ajuda": AjudaPage,
    }
    for page_name, factory in page_factories.items():
        window.register_page_factory(page_name, factory)

    initial_page = window._pending_page_name or "dashboard"
    if initial_page not in page_factories:
        initial_page = "dashboard"
    window.switch_page(initial_page)

    window.showMaximized()
    log.info("Interface gráfica inicializada")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
