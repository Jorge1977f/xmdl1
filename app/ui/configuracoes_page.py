"""Página de configurações com suporte a certificado e portal."""
from __future__ import annotations

import os
import shutil
import webbrowser
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGroupBox, QFormLayout, QSpinBox,
    QFileDialog, QMessageBox, QTabWidget, QComboBox, QCheckBox, QInputDialog
)

from app.utils.logger import log
from app.db import get_db_session, CredencialRepository, EmpresaRepository, DatabaseConnection
from app.core import app_signals
from config.settings import DOWNLOADS_DIR, CERTIFICATES_DIR, DEFAULT_NFSE_CONTRIBUINTE_URL


class ConfiguracoesPage(QWidget):
    """Página de configurações com certificado digital e acesso ao portal."""

    LOGIN_MODES = {
        "MANUAL_ASSISTIDO": "Manual assistido (certificado / gov.br / captcha)",
        "LOGIN_SENHA": "Login e senha automático",
    }

    def __init__(self):
        super().__init__()
        self.session = get_db_session()
        self.credencial_repo = CredencialRepository(self.session)
        self.empresa_repo = EmpresaRepository(self.session)

        layout = QVBoxLayout(self)
        title = QLabel("Configurações")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self.create_certificate_tab(), "🔐 Certificado Digital")
        tabs.addTab(self.create_portal_tab(), "🌐 Portal")
        tabs.addTab(self.create_system_tab(), "⚙️ Sistema")
        layout.addWidget(tabs)

        app_signals.company_selected.connect(self.set_selected_empresa)
        app_signals.companies_changed.connect(self.refresh_empresas)
        self.refresh_empresas()
        self._ensure_portal_defaults_saved()
        log.info("Página de configurações inicializada")

    def create_certificate_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        cert_group = QGroupBox("Certificado Digital (A1)")
        cert_layout = QFormLayout(cert_group)

        self.empresa_combo = QComboBox()
        self.empresa_combo.currentIndexChanged.connect(self._combo_changed)
        cert_layout.addRow("Empresa:", self.empresa_combo)

        self.cert_path = QLineEdit()
        self.cert_path.setReadOnly(True)
        self.cert_path.setPlaceholderText("Nenhum certificado carregado")

        btn_browse = QPushButton("📁 Selecionar Certificado")
        btn_browse.clicked.connect(self.select_certificate)

        cert_path_layout = QHBoxLayout()
        cert_path_layout.addWidget(self.cert_path)
        cert_path_layout.addWidget(btn_browse)
        cert_layout.addRow("Arquivo (.pfx/.p12):", cert_path_layout)

        self.cert_password = QLineEdit()
        self.cert_password.setEchoMode(QLineEdit.Password)
        self.cert_password.setPlaceholderText("Digite a senha do certificado")
        self.btn_toggle_cert_password = QPushButton("👁")
        self.btn_toggle_cert_password.setCheckable(True)
        self.btn_toggle_cert_password.setFixedWidth(38)
        self.btn_toggle_cert_password.setToolTip("Mostrar / ocultar senha")
        self.btn_toggle_cert_password.toggled.connect(self.toggle_cert_password_visibility)
        cert_password_layout = QHBoxLayout()
        cert_password_layout.setContentsMargins(0, 0, 0, 0)
        cert_password_layout.addWidget(self.cert_password)
        cert_password_layout.addWidget(self.btn_toggle_cert_password)
        cert_layout.addRow("Senha:", cert_password_layout)

        self.cert_info = QLabel("Nenhum certificado carregado")
        self.cert_info.setStyleSheet("color: #666; font-size: 12px;")
        self.cert_info.setWordWrap(True)
        cert_layout.addRow("Status:", self.cert_info)
        layout.addWidget(cert_group)

        btn_layout = QHBoxLayout()
        btn_salvar = QPushButton("💾 Salvar Certificado")
        btn_salvar.clicked.connect(self.save_certificate)
        btn_layout.addWidget(btn_salvar)

        btn_validar = QPushButton("✓ Validar")
        btn_validar.clicked.connect(self.validate_certificate)
        btn_layout.addWidget(btn_validar)

        btn_limpar = QPushButton("🗑️ Limpar")
        btn_limpar.clicked.connect(self.clear_certificate)
        btn_layout.addWidget(btn_limpar)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        layout.addStretch()
        return widget

    def create_portal_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        portal_group = QGroupBox("Acesso ao portal de download")
        portal_layout = QFormLayout(portal_group)

        self.portal_url = QLineEdit()
        self.portal_url.setPlaceholderText(DEFAULT_NFSE_CONTRIBUINTE_URL)
        self.portal_url.setText(DEFAULT_NFSE_CONTRIBUINTE_URL)
        self.portal_url.setReadOnly(True)
        self.portal_url.setToolTip("URL fixa nesta versão do sistema")
        portal_layout.addRow("URL do portal (fixa):", self.portal_url)

        self.portal_mode = QComboBox()
        self.portal_mode.addItems(self.LOGIN_MODES.values())
        portal_layout.addRow("Modo de login:", self.portal_mode)

        self.portal_login = QLineEdit()
        self.portal_login.setPlaceholderText("Usuário, CPF, CNPJ ou e-mail")
        portal_layout.addRow("Login:", self.portal_login)

        self.portal_password = QLineEdit()
        self.portal_password.setEchoMode(QLineEdit.Password)
        self.portal_password.setPlaceholderText("Senha do portal")
        self.btn_toggle_portal_password = QPushButton("👁")
        self.btn_toggle_portal_password.setCheckable(True)
        self.btn_toggle_portal_password.setFixedWidth(38)
        self.btn_toggle_portal_password.setToolTip("Mostrar / ocultar senha")
        self.btn_toggle_portal_password.toggled.connect(self.toggle_portal_password_visibility)
        portal_password_layout = QHBoxLayout()
        portal_password_layout.setContentsMargins(0, 0, 0, 0)
        portal_password_layout.addWidget(self.portal_password)
        portal_password_layout.addWidget(self.btn_toggle_portal_password)
        portal_layout.addRow("Senha:", portal_password_layout)

        self.portal_download_dir = QLineEdit()
        self.portal_download_dir.setPlaceholderText(str(Path(DOWNLOADS_DIR)))
        self.portal_download_dir.setText(str(Path(DOWNLOADS_DIR)))
        self.portal_download_dir.setReadOnly(True)
        self.portal_download_dir.setToolTip("Pasta fixa nesta versão do sistema")
        portal_layout.addRow("Pasta monitorada (fixa):", self.portal_download_dir)

        self.portal_wait_seconds = QSpinBox()
        self.portal_wait_seconds.setMinimum(10)
        self.portal_wait_seconds.setMaximum(3600)
        self.portal_wait_seconds.setValue(120)
        portal_layout.addRow("Tempo de espera (segundos):", self.portal_wait_seconds)

        self.portal_headless = QCheckBox("Executar navegador oculto")
        self.portal_headless.setChecked(True)
        self.portal_headless.toggled.connect(self.on_headless_toggled)
        portal_layout.addRow("Headless:", self.portal_headless)

        self.portal_info = QLabel("A URL do portal e a pasta de downloads ficam fixas nesta versão. Login, senha e modo de acesso são salvos automaticamente por empresa; com navegador oculto, o sistema abre visível só para escolher o certificado e depois minimiza para concluir os downloads.")
        self.portal_info.setStyleSheet("color: #666; font-size: 12px;")
        self.portal_info.setWordWrap(True)
        portal_layout.addRow("Status:", self.portal_info)
        self.portal_login.editingFinished.connect(self._autosave_portal)
        self.portal_password.editingFinished.connect(self._autosave_portal)
        self.portal_mode.currentIndexChanged.connect(self._autosave_portal)
        self.portal_wait_seconds.valueChanged.connect(self._autosave_portal)
        layout.addWidget(portal_group)

        btn_layout = QHBoxLayout()
        btn_save_portal = QPushButton("💾 Salvar credenciais")
        btn_save_portal.clicked.connect(self.save_portal)
        btn_layout.addWidget(btn_save_portal)

        btn_open_portal = QPushButton("🌐 Abrir portal")
        btn_open_portal.clicked.connect(self.open_portal)
        btn_layout.addWidget(btn_open_portal)

        btn_clear_portal = QPushButton("🗑️ Limpar acesso")
        btn_clear_portal.clicked.connect(self.clear_portal)
        btn_layout.addWidget(btn_clear_portal)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        layout.addStretch()
        return widget



    def create_system_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        db_group = QGroupBox("Banco de Dados")
        db_layout = QFormLayout(db_group)
        ok, detail = DatabaseConnection.test_connection()
        db_layout.addRow("Status:", QLabel("Conectado" if ok else "Erro"))
        db_label = QLabel(detail)
        db_label.setWordWrap(True)
        db_layout.addRow("Arquivo:", db_label)
        layout.addWidget(db_group)

        period_group = QGroupBox("Configurações de Período")
        period_layout = QFormLayout(period_group)
        self.max_days = QSpinBox()
        self.max_days.setValue(30)
        self.max_days.setMinimum(1)
        self.max_days.setMaximum(365)
        period_layout.addRow("Dias Máximos por Lote:", self.max_days)
        layout.addWidget(period_group)

        cache_group = QGroupBox("Configurações de Cache")
        cache_layout = QFormLayout(cache_group)
        self.cache_expiration = QSpinBox()
        self.cache_expiration.setValue(365)
        self.cache_expiration.setMinimum(1)
        self.cache_expiration.setMaximum(3650)
        cache_layout.addRow("Expiração de Cache (dias):", self.cache_expiration)
        layout.addWidget(cache_group)

        manifest_group = QGroupBox("Configurações de Manifestação")
        manifest_layout = QFormLayout(manifest_group)
        self.manifest_retries = QSpinBox()
        self.manifest_retries.setValue(5)
        self.manifest_retries.setMinimum(1)
        self.manifest_retries.setMaximum(20)
        manifest_layout.addRow("Máximo de Tentativas:", self.manifest_retries)
        self.manifest_delay = QSpinBox()
        self.manifest_delay.setValue(3600)
        self.manifest_delay.setMinimum(60)
        self.manifest_delay.setMaximum(86400)
        manifest_layout.addRow("Delay entre Tentativas (segundos):", self.manifest_delay)
        layout.addWidget(manifest_group)

        log_group = QGroupBox("Configurações de Log")
        log_layout = QFormLayout(log_group)
        self.log_level = QLineEdit()
        self.log_level.setText("INFO")
        log_layout.addRow("Nível de Log:", self.log_level)
        layout.addWidget(log_group)

        btn_layout = QHBoxLayout()
        btn_salvar = QPushButton("💾 Salvar")
        btn_salvar.clicked.connect(self.save_settings)
        btn_layout.addWidget(btn_salvar)
        btn_restaurar = QPushButton("🔄 Restaurar Padrão")
        btn_restaurar.clicked.connect(self.restore_defaults)
        btn_layout.addWidget(btn_restaurar)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        layout.addStretch()
        return widget

    def refresh_empresas(self, select_company_id=None):
        empresas = self.empresa_repo.list_all()
        self.empresa_combo.blockSignals(True)
        self.empresa_combo.clear()
        self.empresa_combo.addItem("Selecione uma empresa", None)
        for empresa in empresas:
            self.empresa_combo.addItem(f"{empresa.razao_social} - {empresa.cnpj}", empresa.id)
        idx = self.empresa_combo.findData(select_company_id)
        self.empresa_combo.setCurrentIndex(idx if idx >= 0 else (1 if empresas else 0))
        self.empresa_combo.blockSignals(False)
        self.load_certificate()
        self.load_portal()
        self._ensure_portal_defaults_saved()

    def set_selected_empresa(self, empresa_id):
        idx = self.empresa_combo.findData(empresa_id)
        self.empresa_combo.blockSignals(True)
        if idx >= 0:
            self.empresa_combo.setCurrentIndex(idx)
        elif self.empresa_combo.count():
            self.empresa_combo.setCurrentIndex(0)
        self.empresa_combo.blockSignals(False)
        self.load_certificate()
        self.load_portal()
        self._ensure_portal_defaults_saved()

    def on_page_activated(self):
        self.refresh_empresas(self.empresa_combo.currentData())

    def _combo_changed(self):
        app_signals.company_selected.emit(self.empresa_combo.currentData())
        self.load_certificate()
        self.load_portal()
        self._ensure_portal_defaults_saved()

    def select_certificate(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar Certificado Digital", os.path.expanduser("~"),
            "Certificados (*.pfx *.p12);;Todos os arquivos (*.*)"
        )
        if file_path:
            stored_path = self._store_certificate_file(file_path)
            final_path = stored_path or file_path
            self.cert_path.setText(final_path)
            if stored_path:
                self.cert_info.setText(f"Certificado copiado para a pasta interna: {os.path.basename(final_path)}")
            else:
                self.cert_info.setText(f"Arquivo selecionado: {os.path.basename(file_path)}")
            log.info(f"Certificado selecionado: {final_path}")

    def select_download_folder(self):
        QMessageBox.information(self, "Pasta monitorada", f"Nesta versão a pasta de downloads é fixa:\n{Path(DOWNLOADS_DIR)}")

    def load_certificate(self):
        empresa_id = self.empresa_combo.currentData()
        if not empresa_id:
            self.cert_path.clear()
            self.cert_password.clear()
            self.cert_info.setText("Selecione uma empresa para ver o certificado.")
            return
        credencial = self.credencial_repo.get_ativo_by_empresa(empresa_id, "CERTIFICADO")
        if credencial:
            current_cert_path = credencial.cert_path or ""
            self.cert_path.setText(current_cert_path)
            self.cert_password.setText(credencial.cert_senha or "")
            if current_cert_path and not os.path.exists(current_cert_path):
                self.cert_info.setText("O certificado salvo não foi encontrado no caminho atual. Reimporte ou ajuste o arquivo.")
            else:
                self.cert_info.setText(f"Certificado salvo para a empresa selecionada. Ambiente: {credencial.ambiente or 'PRODUCAO'}")
        else:
            self.cert_path.clear()
            self.cert_password.clear()
            self.cert_info.setText("Nenhum certificado salvo para a empresa selecionada.")

    def _empresa_tem_certificado_salvo(self, empresa_id) -> bool:
        if not empresa_id:
            return False
        credencial = self.credencial_repo.get_ativo_by_empresa(empresa_id, "CERTIFICADO")
        cert_path = (credencial.cert_path or '').strip() if credencial else ''
        return bool(cert_path and os.path.exists(cert_path))

    def _headless_preferencial(self, empresa_id, valor_salvo: bool | None = None) -> bool:
        tem_certificado = self._empresa_tem_certificado_salvo(empresa_id)
        if valor_salvo is None:
            return tem_certificado
        return bool(valor_salvo) or tem_certificado

    def _set_headless_checkbox(self, checked: bool):
        self.portal_headless.blockSignals(True)
        self.portal_headless.setChecked(checked)
        self.portal_headless.blockSignals(False)

    def toggle_cert_password_visibility(self, visible: bool):
        self.cert_password.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)
        self.btn_toggle_cert_password.setText("🙈" if visible else "👁")

    def toggle_portal_password_visibility(self, visible: bool):
        self.portal_password.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)
        self.btn_toggle_portal_password.setText("🙈" if visible else "👁")

    def load_portal(self):
        empresa_id = self.empresa_combo.currentData()
        self.portal_mode.blockSignals(True)
        self.portal_wait_seconds.blockSignals(True)
        try:
            if not empresa_id:
                self.portal_url.setText(DEFAULT_NFSE_CONTRIBUINTE_URL)
                self.portal_login.clear()
                self.portal_password.clear()
                self.portal_download_dir.setText(str(Path(DOWNLOADS_DIR)))
                self.portal_wait_seconds.setValue(120)
                self._set_headless_checkbox(True)
                self.portal_mode.setCurrentIndex(0)
                self.portal_info.setText("Selecione uma empresa. A URL do portal e a pasta de downloads já ficam fixas automaticamente.")
                return

            credencial = self.credencial_repo.get_ativo_by_empresa(empresa_id, "PORTAL")
            if credencial:
                current_portal_url = credencial.portal_url or DEFAULT_NFSE_CONTRIBUINTE_URL
                self.portal_url.setText(current_portal_url)
                self.portal_login.setText(credencial.login or "")
                self.portal_password.setText(credencial.senha or "")
                self.portal_download_dir.setText(str(Path(DOWNLOADS_DIR)))
                self.portal_wait_seconds.setValue(int(credencial.tempo_espera_login or 120))
                self._set_headless_checkbox(self._headless_preferencial(empresa_id, bool(credencial.navegador_headless)))
                mode_text = self.LOGIN_MODES.get(credencial.modo_login or "MANUAL_ASSISTIDO", self.LOGIN_MODES["MANUAL_ASSISTIDO"])
                idx = self.portal_mode.findText(mode_text)
                self.portal_mode.setCurrentIndex(max(idx, 0))
                if current_portal_url != DEFAULT_NFSE_CONTRIBUINTE_URL:
                    self.portal_info.setText("Configuração carregada. Atenção: a URL salva está diferente da URL padrão da NFS-e; revise se o portal mudar.")
                else:
                    self.portal_info.setText("Configuração do portal carregada. A URL e a pasta de downloads permanecem fixas; o navegador oculto usa certificado visível só na etapa inicial e depois minimiza a janela para concluir o download.")
            else:
                self.portal_url.setText(DEFAULT_NFSE_CONTRIBUINTE_URL)
                self.portal_login.clear()
                self.portal_password.clear()
                self.portal_download_dir.setText(str(Path(DOWNLOADS_DIR)))
                self.portal_wait_seconds.setValue(120)
                self._set_headless_checkbox(True if empresa_id else self._headless_preferencial(empresa_id))
                self.portal_mode.setCurrentIndex(0)
                self.portal_info.setText("Nenhuma configuração anterior foi encontrada. A URL do portal e a pasta de downloads já foram aplicadas automaticamente.")
        finally:
            self.portal_mode.blockSignals(False)
            self.portal_wait_seconds.blockSignals(False)

    def save_certificate(self):
        empresa_id = self.empresa_combo.currentData()
        cert_path = self.cert_path.text().strip()
        password = self.cert_password.text().strip()
        if not empresa_id:
            QMessageBox.warning(self, "Configurações", "Selecione uma empresa antes de salvar o certificado.")
            return
        if not cert_path:
            QMessageBox.warning(self, "Configurações", "Selecione um certificado primeiro.")
            return
        if not password:
            QMessageBox.warning(self, "Configurações", "Digite a senha do certificado.")
            return
        if not os.path.exists(cert_path):
            QMessageBox.critical(self, "Erro", "Arquivo de certificado não encontrado.")
            return
        stored_path = self._store_certificate_file(cert_path)
        final_cert_path = stored_path or cert_path
        credencial = self.credencial_repo.get_ativo_by_empresa(empresa_id, "CERTIFICADO")
        if credencial:
            self.credencial_repo.update(credencial.id, cert_path=final_cert_path, cert_senha=password, ambiente="PRODUCAO", ativo=True)
        else:
            self.credencial_repo.create(empresa_id=empresa_id, tipo_credencial="CERTIFICADO", cert_path=final_cert_path, cert_senha=password, ambiente="PRODUCAO", ativo=True)
        self.cert_path.setText(final_cert_path)
        self.cert_info.setText("Certificado salvo com sucesso na pasta interna do programa para a empresa selecionada.")
        QMessageBox.information(self, "Sucesso", "Certificado salvo com sucesso.")

    def save_portal(self, silent: bool = False):
        empresa_id = self.empresa_combo.currentData()
        portal_url = DEFAULT_NFSE_CONTRIBUINTE_URL
        login = self.portal_login.text().strip()
        password = self.portal_password.text().strip()
        downloads_dir = str(Path(DOWNLOADS_DIR))
        modo_login = self.get_selected_login_mode_key()

        if not empresa_id:
            if not silent:
                QMessageBox.warning(self, "Portal", "Selecione uma empresa antes de salvar o portal.")
            return False

        Path(downloads_dir).mkdir(parents=True, exist_ok=True)

        credencial = self.credencial_repo.get_ativo_by_empresa(empresa_id, "PORTAL")
        payload = dict(
            portal_url=portal_url,
            login=login or None,
            downloads_dir=downloads_dir,
            modo_login=modo_login,
            navegador_headless=self._headless_preferencial(empresa_id, self.portal_headless.isChecked()),
            tempo_espera_login=int(self.portal_wait_seconds.value()),
            ambiente="PRODUCAO",
            ativo=True,
        )
        if password:
            payload["senha"] = password

        if credencial:
            self.credencial_repo.update(credencial.id, **payload)
        else:
            if "senha" not in payload:
                payload["senha"] = None
            self.credencial_repo.create(empresa_id=empresa_id, tipo_credencial="PORTAL", **payload)

        self.portal_url.setText(portal_url)
        self.portal_download_dir.setText(downloads_dir)
        self._set_headless_checkbox(self._headless_preferencial(empresa_id, self.portal_headless.isChecked()))
        self.portal_info.setText("Configuração do portal salva. A URL do Portal Contribuinte NFS-e e a pasta C:/xmdl/data/downloads permanecem fixas; com navegador oculto, o certificado é selecionado com a janela visível e depois o navegador é minimizado para continuar o download.")
        if not silent:
            QMessageBox.information(self, "Sucesso", "Credenciais do portal salvas com sucesso.")
        return True

    def validate_certificate(self):
        cert_path = self.cert_path.text().strip()
        password = self.cert_password.text().strip()
        if not cert_path:
            QMessageBox.warning(self, "Configurações", "Selecione um certificado primeiro.")
            return
        if not os.path.exists(cert_path):
            QMessageBox.critical(self, "Erro", "Arquivo de certificado não encontrado.")
            return
        if not password:
            QMessageBox.warning(self, "Configurações", "Digite a senha para validar o certificado.")
            return
        QMessageBox.information(self, "Validação", f"✓ Arquivo localizado e senha informada.\n\nArquivo: {os.path.basename(cert_path)}")
        self.cert_info.setText(f"Validação básica concluída: {os.path.basename(cert_path)}")

    def open_portal(self):
        portal_url = self.portal_url.text().strip() or DEFAULT_NFSE_CONTRIBUINTE_URL
        self.portal_url.setText(portal_url)
        webbrowser.open(portal_url)
        self.portal_info.setText(f"Portal aberto no navegador padrão: {portal_url}")

    def clear_certificate(self):
        empresa_id = self.empresa_combo.currentData()
        if not empresa_id:
            self.cert_path.clear()
            self.cert_password.clear()
            self.cert_info.setText("Nenhum certificado carregado")
            return
        credencial = self.credencial_repo.get_ativo_by_empresa(empresa_id, "CERTIFICADO")
        if credencial:
            self.credencial_repo.update(credencial.id, ativo=False)
        self.cert_path.clear()
        self.cert_password.clear()
        self.cert_info.setText("Certificado removido da empresa selecionada.")

    def clear_portal(self):
        empresa_id = self.empresa_combo.currentData()
        if empresa_id:
            credencial = self.credencial_repo.get_ativo_by_empresa(empresa_id, "PORTAL")
            if credencial:
                self.credencial_repo.update(credencial.id, ativo=False)
        self.portal_url.setText(DEFAULT_NFSE_CONTRIBUINTE_URL)
        self.portal_login.clear()
        self.portal_password.clear()
        self.portal_download_dir.setText(str(Path(DOWNLOADS_DIR)))
        self.portal_wait_seconds.setValue(120)
        self._set_headless_checkbox(self._headless_preferencial(empresa_id))
        self.portal_mode.setCurrentIndex(0)
        self.portal_info.setText("Configuração de portal removida da empresa selecionada. A URL e a pasta padrão continuam fixas para a próxima configuração.")

    def get_selected_login_mode_key(self) -> str:
        selected = self.portal_mode.currentText()
        for key, value in self.LOGIN_MODES.items():
            if value == selected:
                return key
        return "MANUAL_ASSISTIDO"

    def _ensure_portal_defaults_saved(self):
        empresa_id = self.empresa_combo.currentData()
        if empresa_id:
            self.save_portal(silent=True)

    def _autosave_portal(self, *_args):
        empresa_id = self.empresa_combo.currentData()
        if not empresa_id:
            return
        self.save_portal(silent=True)

    def on_headless_toggled(self, checked: bool):
        empresa_id = self.empresa_combo.currentData()
        if not empresa_id:
            self.portal_headless.blockSignals(True)
            self._set_headless_checkbox(True if self.empresa_combo.currentData() else self._headless_preferencial(self.empresa_combo.currentData()))
            self.portal_headless.blockSignals(False)
            QMessageBox.warning(self, "Navegador oculto", "Selecione uma empresa antes de alterar essa opção.")
            return

        if checked:
            credencial = self.credencial_repo.get_ativo_by_empresa(empresa_id, "CERTIFICADO")
            cert_path = (credencial.cert_path or '').strip() if credencial else ''
            cert_exists = bool(cert_path and os.path.exists(cert_path))
            if not cert_exists:
                self.portal_headless.blockSignals(True)
                self._set_headless_checkbox(False)
                self.portal_headless.blockSignals(False)
                QMessageBox.information(
                    self,
                    "Navegador oculto",
                    "Para usar o navegador oculto, deixe primeiro um certificado A1 salvo para essa empresa. Na execução, o sistema vai abrir a janela visível só para você escolher o certificado e depois minimizar o navegador para continuar sozinho.",
                )
                self.portal_info.setText("Navegador oculto não ativado: falta um certificado salvo para a empresa.")
                return
            self.portal_info.setText("Navegador oculto ativado. Ao executar o download, o sistema vai abrir a janela visível para você escolher o certificado e, depois do login, minimizar o navegador para continuar os XMLs automaticamente.")
        else:
            self.portal_info.setText("Navegador visível ativado. O login e o download continuam aparecendo normalmente na tela.")
        self._autosave_portal()

    def _store_certificate_file(self, source_path: str) -> str | None:
        empresa_id = self.empresa_combo.currentData()
        if not source_path or not os.path.exists(source_path) or not empresa_id:
            return None

        empresa = self.empresa_repo.get_by_id(empresa_id)
        company_key = (empresa.cnpj if empresa and empresa.cnpj else str(empresa_id)).replace('/', '').replace('.', '').replace('-', '')
        target_dir = Path(CERTIFICATES_DIR) / company_key
        target_dir.mkdir(parents=True, exist_ok=True)

        source = Path(source_path)
        target = target_dir / source.name
        if source.resolve() == target.resolve():
            return str(target)

        candidate = target
        counter = 2
        while candidate.exists():
            try:
                if source.read_bytes() == candidate.read_bytes():
                    return str(candidate)
            except Exception:
                pass
            candidate = target_dir / f"{source.stem}_{counter}{source.suffix}"
            counter += 1

        try:
            shutil.copy2(source, candidate)
            return str(candidate)
        except Exception as exc:
            log.warning(f"Não foi possível copiar o certificado para a pasta interna: {exc}")
            return None

    def save_settings(self):
        QMessageBox.information(self, "Configurações", "As configurações gerais continuam visuais nesta versão. A parte funcional agora está no certificado e no portal por empresa.")

    def restore_defaults(self):
        self.max_days.setValue(30)
        self.cache_expiration.setValue(365)
        self.manifest_retries.setValue(5)
        self.manifest_delay.setValue(3600)
        self.log_level.setText("INFO")
        self.portal_wait_seconds.setValue(120)
        self._set_headless_checkbox(self._headless_preferencial(self.empresa_combo.currentData()))
        self.portal_mode.setCurrentIndex(0)
        self.portal_url.setText(DEFAULT_NFSE_CONTRIBUINTE_URL)
        self.portal_download_dir.setText(str(Path(DOWNLOADS_DIR)))
        QMessageBox.information(self, "Configurações", "Valores restaurados para o padrão visual da tela.")
