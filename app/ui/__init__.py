"""
Módulo de interface gráfica
"""
from app.ui.main_window import MainWindow
from app.ui.empresas_page import EmpresasPage
from app.ui.downloader_page import DownloaderPage
from app.ui.dashboard_page import DashboardPage
from app.ui.logs_page import LogsPage
from app.ui.relatorios_page import RelatoriosPage
from app.ui.manifestacao_page import ManifestacaoPage
from app.ui.xmls_page import XMLsPage
from app.ui.limpeza_backup_page import LimpezaBackupPage
from app.ui.configuracoes_page import ConfiguracoesPage
from app.ui.licencas_page import LicencasPage
from app.ui.ajuda_page import AjudaPage
from app.ui.first_access_dialog import FirstAccessDialog

__all__ = [
    "MainWindow",
    "EmpresasPage",
    "DownloaderPage",
    "DashboardPage",
    "LogsPage",
    "RelatoriosPage",
    "ManifestacaoPage",
    "XMLsPage",
    "LimpezaBackupPage",
    "ConfiguracoesPage",
    "LicencasPage",
    "AjudaPage",
    "FirstAccessDialog",
]
