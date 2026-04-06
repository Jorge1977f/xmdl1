"""
Janela principal da aplicação em PySide6
"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QPushButton, QLabel, QFrame, QComboBox, QMessageBox
)
from PySide6.QtCore import Qt, QTimer
from typing import Callable
from PySide6.QtGui import QKeySequence, QShortcut
from app.utils.logger import log
from app.db import get_db_session, EmpresaRepository, DatabaseConnection
from app.core import app_signals
from app.services import LicensingService
from app.utils.ui_state import get_settings
from app.ui.help_dialog import HelpDialog
from app.ui.first_access_dialog import FirstAccessDialog


class MainWindow(QMainWindow):
    """Janela principal da aplicação"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("XML Downloader - Sistema de Download Inteligente")
        self.setGeometry(100, 100, 1360, 860)
        self.setMinimumSize(1200, 760)

        self.page_map = {}
        self.page_factories: dict[str, Callable[[], QWidget]] = {}
        self.nav_buttons = {}
        self.current_page = None
        self._pending_page_name = None
        self._suppress_company_save = False
        self.settings = get_settings()
        self.session = get_db_session()
        self.licensing_service = LicensingService(self.session)
        self.empresa_repo = EmpresaRepository(self.session)

        self.setStyleSheet("""
            QMainWindow { background-color: #f5f5f5; }
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1976D2; }
            QPushButton:pressed { background-color: #1565C0; }
            QComboBox, QDateEdit {
                padding: 6px 10px;
                border: 1px solid #d0d7de;
                border-radius: 6px;
                background-color: white;
                min-width: 280px;
                min-height: 34px;
            }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        sidebar = self.create_sidebar()
        main_layout.addWidget(sidebar)

        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(16, 16, 16, 16)
        content_layout.setSpacing(12)

        topbar = self.create_topbar()
        content_layout.addWidget(topbar)

        self.stacked_widget = QStackedWidget()
        content_layout.addWidget(self.stacked_widget, 1)

        footer = self.create_footer()
        content_layout.addWidget(footer)
        main_layout.addWidget(content_container, 1)

        self._help_shortcut = QShortcut(QKeySequence("F1"), self)
        self._help_shortcut.activated.connect(self.show_current_help)

        app_signals.companies_changed.connect(self.refresh_company_selector)
        app_signals.page_requested.connect(self.switch_page)

        self.refresh_company_selector(self._load_last_company_id())
        self._pending_page_name = self.settings.value("main/last_page", "dashboard") or "dashboard"
        snapshot = self.licensing_service.get_snapshot(force_sync=False)
        
        # Verifica se o usuário desabilitou o aviso
        show_startup_warning = str(self.settings.value("main/show_startup_warning", "true")).lower() in {"1", "true", "yes"}
        
        # Exibe o aviso sempre (a menos que o usuário tenha desabilitado)
        if show_startup_warning:
            QTimer.singleShot(250, self._show_first_access_notice)
        
        # Redireciona para Licenças se não cadastrado
        if snapshot.status == "NAO_CADASTRADO":
            self._pending_page_name = "licencas"
        elif snapshot.status == "TRIAL_EXPIRADO":
            QTimer.singleShot(250, self._show_trial_expired_notice)
        self.refresh_license_status_banner()
        QTimer.singleShot(0, self._force_maximized)
        log.info("Janela principal inicializada")

    def _force_maximized(self):
        try:
            self.showMaximized()
            self.setWindowState(self.windowState() | Qt.WindowMaximized)
        except Exception as exc:
            log.warning(f"Não foi possível maximizar automaticamente a janela: {exc}")

    def create_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setStyleSheet("""
            QFrame {
                background-color: #263238;
                border-right: 1px solid #1a1a1a;
            }
        """)
        sidebar.setMaximumWidth(250)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = QLabel("XML Downloader")
        title.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 20px;
                border-bottom: 1px solid #455A64;
            }
        """)
        layout.addWidget(title)

        nav_buttons = [
            ("📊 Dashboard", "dashboard"),
            ("🏢 Empresas", "empresas"),
            ("⬇️ Download", "download"),
            ("📁 XMLs", "xmls"),
            ("✋ Manifestação", "manifestacao"),
            ("📋 Logs", "logs"),
            ("📈 Relatórios", "relatorios"),
            ("🗑️ Limpeza & Backup", "limpeza_backup"),
            ("🪪 Licenças", "licencas"),
            ("⚙️ Configurações", "configuracoes"),
            ("❓ Ajuda", "ajuda"),
        ]

        for label, page_name in nav_buttons:
            btn = QPushButton(label)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #b0bec5;
                    border: none;
                    border-radius: 0;
                    padding: 12px 20px;
                    text-align: left;
                    font-size: 13px;
                    font-weight: normal;
                }
                QPushButton:hover {
                    background-color: #37474F;
                    color: #ffffff;
                }
                QPushButton:pressed {
                    background-color: #455A64;
                    color: #ffffff;
                }
            """)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, p=page_name: self.switch_page(p))
            self.nav_buttons[page_name] = btn
            layout.addWidget(btn)

        layout.addStretch()

        exit_btn = QPushButton("🚪 Sair")
        exit_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #b0bec5;
                border: none;
                border-radius: 0;
                padding: 12px 20px;
                text-align: left;
                font-size: 13px;
                border-top: 1px solid #455A64;
            }
            QPushButton:hover {
                background-color: #d32f2f;
                color: #ffffff;
            }
        """)
        exit_btn.setCursor(Qt.PointingHandCursor)
        exit_btn.clicked.connect(self.close)
        layout.addWidget(exit_btn)
        return sidebar

    def create_topbar(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 10px;
            }
            QLabel#Muted {
                color: #64748b;
                font-size: 12px;
            }
        """)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(16, 12, 16, 12)

        title = QLabel("Empresa ativa:")
        title.setStyleSheet("font-weight: bold; color: #0f172a;")
        layout.addWidget(title)

        self.company_selector = QComboBox()
        self.company_selector.currentIndexChanged.connect(self._company_selector_changed)
        layout.addWidget(self.company_selector)

        btn_refresh = QPushButton("🔄 Atualizar empresas")
        btn_refresh.clicked.connect(lambda: self.refresh_company_selector(self.get_selected_company_id()))
        layout.addWidget(btn_refresh)

        layout.addStretch()

        ok, detail = DatabaseConnection.test_connection()
        db_status = "Banco conectado" if ok else "Banco com erro"
        db_color = "#166534" if ok else "#b91c1c"
        self.db_status = QLabel(f"{db_status}: {detail}")
        self.db_status.setObjectName("Muted")
        self.db_status.setStyleSheet(f"color: {db_color}; font-size: 12px;")
        self.db_status.setToolTip(detail)
        layout.addWidget(self.db_status)

        self.license_status_label = QLabel()
        self.license_status_label.setObjectName("Muted")
        layout.addWidget(self.license_status_label)
        self.refresh_license_status_banner()
        return frame

    def create_footer(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: none;
            }
            QLabel {
                color: #6b7280;
                font-size: 11px;
            }
        """)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(8)

        self.footer_company_label = QLabel("Empresa atual: nenhuma selecionada")
        self.footer_company_label.setToolTip("Empresa selecionada no momento")
        layout.addWidget(self.footer_company_label, 0, Qt.AlignLeft)

        layout.addStretch()

        self.footer_credit_label = QLabel("desenvolvido por jfl · todos os direitos reservados")
        self.footer_credit_label.setStyleSheet("color: #9ca3af; font-size: 10px;")
        layout.addWidget(self.footer_credit_label, 0, Qt.AlignRight)
        return frame

    def update_footer_company(self, empresa_id):
        empresa = self.empresa_repo.get_by_id(empresa_id) if empresa_id else None
        if empresa:
            texto = f"Empresa atual: {empresa.razao_social}"
            if empresa.cnpj:
                texto += f" · {empresa.cnpj}"
        else:
            texto = "Empresa atual: nenhuma selecionada"
        self.footer_company_label.setText(texto)

    def _load_last_company_id(self):
        raw = self.settings.value("main/selected_company_id")
        if raw in (None, "", "None"):
            return None
        try:
            return int(raw)
        except Exception:
            return None

    def refresh_company_selector(self, select_company_id=None):
        empresas = self.empresa_repo.list_all()
        remembered_company_id = self._load_last_company_id()
        target_company_id = select_company_id if select_company_id is not None else remembered_company_id

        self.company_selector.blockSignals(True)
        self._suppress_company_save = True
        self.company_selector.clear()
        self.company_selector.addItem("Todas / nenhuma empresa selecionada", None)
        for empresa in empresas:
            self.company_selector.addItem(f"{empresa.razao_social} - {empresa.cnpj}", empresa.id)

        if target_company_id is not None:
            index = self.company_selector.findData(target_company_id)
            self.company_selector.setCurrentIndex(index if index >= 0 else (1 if empresas else 0))
        elif empresas and self.company_selector.currentIndex() <= 0:
            self.company_selector.setCurrentIndex(1)
        else:
            self.company_selector.setCurrentIndex(0)
        self._suppress_company_save = False
        self.company_selector.blockSignals(False)

        self._emit_selected_company()
        log.info("Seletor global de empresas atualizado")

    def get_selected_company_id(self):
        return self.company_selector.currentData()

    def _company_selector_changed(self):
        self._emit_selected_company()

    def _emit_selected_company(self):
        empresa_id = self.get_selected_company_id()
        if not self._suppress_company_save:
            self.settings.setValue("main/selected_company_id", "" if empresa_id is None else str(empresa_id))
        self.update_footer_company(empresa_id)
        self.refresh_license_status_banner()
        app_signals.company_selected.emit(empresa_id)

    def _update_nav_highlight(self, current_page: str):
        for name, btn in self.nav_buttons.items():
            if name == current_page:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #1976D2;
                        color: #ffffff;
                        border: none;
                        border-radius: 0;
                        padding: 12px 20px;
                        text-align: left;
                        font-size: 13px;
                        font-weight: bold;
                    }
                    QPushButton:hover { background-color: #1565C0; }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        color: #b0bec5;
                        border: none;
                        border-radius: 0;
                        padding: 12px 20px;
                        text-align: left;
                        font-size: 13px;
                        font-weight: normal;
                    }
                    QPushButton:hover {
                        background-color: #37474F;
                        color: #ffffff;
                    }
                    QPushButton:pressed {
                        background-color: #455A64;
                        color: #ffffff;
                    }
                """)

    def show_help_topic(self, topic: str):
        dialog = HelpDialog(self, topic or "geral")
        dialog.exec()

    def show_current_help(self):
        topic = self.current_page or "geral"
        if topic == "ajuda":
            topic = "geral"
        self.show_help_topic(topic)

    def refresh_license_status_banner(self):
        if not hasattr(self, "license_status_label"):
            return
        snapshot = self.licensing_service.get_snapshot(force_sync=False)
        text = f"Licença: {snapshot.status_label}"
        if snapshot.days_left is not None and snapshot.status == "TRIAL":
            text += f" · {snapshot.days_left} dia(s)"
        self.license_status_label.setText(text)
        if snapshot.status == "ATIVA":
            color = "#166534"
        elif snapshot.status in {"TRIAL_EXPIRADO", "PAGAMENTO_PENDENTE"}:
            color = "#b45309"
        else:
            color = "#64748b"
        self.license_status_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        self.license_status_label.setToolTip(snapshot.message)

    def _show_first_access_notice(self):
        dialog = FirstAccessDialog(self)
        dialog.exec()
        # Se o usuário marcou "Não exibir mais", salva a preferência
        if dialog.dont_show_again:
            self.settings.setValue("main/show_startup_warning", False)

    def _show_trial_expired_notice(self):
        QMessageBox.warning(
            self,
            "Teste encerrado",
            "O período de teste terminou. Os XMLs já baixados continuam disponíveis, "
            "mas novos downloads foram bloqueados. Gere o Pix no módulo Licenças para ativar a máquina atual.",
        )

    def _ensure_page_loaded(self, page_name: str) -> bool:
        if page_name in self.page_map:
            return True
        factory = self.page_factories.get(page_name)
        if not factory:
            return False
        try:
            page_widget = factory()
            self.add_page(page_widget, page_name)
            return True
        except Exception as exc:
            log.error(f"Erro ao carregar página {page_name}: {exc}")
            return False

    def switch_page(self, page_name: str):
        if self.current_page == page_name:
            page = self.stacked_widget.currentWidget()
            if hasattr(page, "on_page_activated"):
                page.on_page_activated()
            return

        if page_name not in self.page_map and not self._ensure_page_loaded(page_name):
            self._pending_page_name = page_name
            log.warning(f"Página não encontrada: {page_name}")
            return

        index = self.page_map[page_name]
        self.stacked_widget.setCurrentIndex(index)
        self.current_page = page_name
        self.settings.setValue("main/last_page", page_name)
        self._update_nav_highlight(page_name)
        page = self.stacked_widget.widget(index)
        if hasattr(page, "on_page_activated"):
            page.on_page_activated()
        if page_name == "ajuda" and hasattr(page, "show_topic"):
            page.show_topic("geral")
        self.refresh_license_status_banner()
        log.info(f"Página alterada para: {page_name}")

    def register_page_factory(self, page_name: str, factory: Callable[[], QWidget]):
        self.page_factories[page_name] = factory
        log.debug(f"Factory registrada para página: {page_name}")

    def add_page(self, page_widget: QWidget, page_name: str):
        index = self.stacked_widget.addWidget(page_widget)
        self.page_map[page_name] = index

        selected_company_id = self.get_selected_company_id()
        try:
            if hasattr(page_widget, "refresh_empresas"):
                page_widget.refresh_empresas(selected_company_id)
            elif hasattr(page_widget, "set_selected_empresa"):
                page_widget.set_selected_empresa(selected_company_id)
        except Exception as exc:
            log.warning(f"Falha ao sincronizar empresa ao carregar a página {page_name}: {exc}")

        log.debug(f"Página adicionada: {page_name} (index: {index})")
