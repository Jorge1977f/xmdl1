"""Página principal de download de XMLs - COM INTEGRAÇÃO COMPLETA DE MELHORIAS."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QDate, QThread, Signal, Qt
import re
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDateEdit,
    QPushButton, QProgressBar, QTableWidget, QTableWidgetItem, QGroupBox,
    QFormLayout, QMessageBox, QFrame, QGridLayout, QHeaderView, QSizePolicy
)

from app.utils.logger import log
from app.db import get_db_session, EmpresaRepository, JobDownloadRepository
from app.core import app_signals
from app.services import PortalAutomationService, JobExecutionSummary, LicensingService
from app.services.safe_download_manager import SafeDownloadManager
from app.utils.ui_state import get_settings, save_qdate, load_qdate
from config.settings import EXECUTION_MODES


class DownloadWorker(QObject):
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(int, str)

    def __init__(self, job_id: int, download_manager: SafeDownloadManager = None):
        super().__init__()
        self.job_id = job_id
        self.download_manager = download_manager

    def _emit_progress(self, percent: int, message: str):
        self.progress.emit(int(percent), str(message or ""))

    def run(self):
        try:
            service = PortalAutomationService(progress_callback=self._emit_progress)
            service.download_manager = self.download_manager
            result = service.execute_job(self.job_id)
            self.finished.emit(result)
        except Exception as exc:
            log.exception(f"Falha no worker do job {self.job_id}: {exc}")
            self.error.emit(str(exc))


class DownloaderPage(QWidget):
    """Página de download de XMLs com todas as melhorias integradas"""

    STEP_TITLES = [
        ("certificado", "1. Certificado"),
        ("portal", "2. Portal"),
        ("periodo", "3. Período"),
        ("download", "4. Download XML"),
        ("importacao", "5. Importação"),
    ]

    def __init__(self):
        super().__init__()
        self.session = get_db_session()
        self.empresa_repo = EmpresaRepository(self.session)
        self.job_repo = JobDownloadRepository(self.session)
        self.settings = get_settings()
        self.licensing_service = LicensingService(self.session)
        self._worker_thread = None
        self._worker = None
        self._restoring_state = False
        self._last_download_dir = None
        self._current_job_id = None
        
        # ✨ NOVO: Gerenciador de downloads seguro
        self.download_manager = SafeDownloadManager(
            max_workers=5,
            preserve_on_cancel=True
        )

        layout = QVBoxLayout(self)
        title = QLabel("Download de XMLs")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Fluxo guiado: escolha a empresa e o período; o sistema abre o portal configurado, "
            "aguarda o acesso e tenta concluir o restante automaticamente. Em certificado + navegador oculto, "
            "a janela aparece para a seleção do certificado e depois é minimizada para terminar sozinha."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #64748b; margin-bottom: 4px;")
        layout.addWidget(subtitle)

        self.context_label = QLabel("Empresa ativa: nenhuma")
        self.context_label.setStyleSheet("color: #64748b;")
        layout.addWidget(self.context_label)

        self.license_banner = QLabel()
        self.license_banner.setWordWrap(True)
        self.license_banner.setStyleSheet("background: #eff6ff; border: 1px solid #bfdbfe; color: #1d4ed8; border-radius: 8px; padding: 8px;")
        layout.addWidget(self.license_banner)

        self._build_step_panel(layout)
        self._build_summary_panel(layout)

        config_group = QGroupBox("Configuração de Download")
        config_group.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        config_group.setMaximumWidth(980)
        config_layout = QFormLayout(config_group)
        config_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        config_layout.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        config_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        config_layout.setHorizontalSpacing(18)
        config_layout.setVerticalSpacing(10)

        self.empresa_combo = QComboBox()
        self._prepare_form_widget(self.empresa_combo, min_width=680, popup_width=760)
        self.empresa_combo.currentIndexChanged.connect(self._combo_changed)
        config_layout.addRow("Empresa:", self.empresa_combo)

        self.tipo_combo = QComboBox()
        self._prepare_form_widget(self.tipo_combo, min_width=420, popup_width=420)
        self.tipo_combo.addItems(["NFS-e Tomada", "NFS-e Prestada"])
        self.tipo_combo.currentIndexChanged.connect(self._save_state)
        config_layout.addRow("Tipo de Documento:", self.tipo_combo)

        self.data_inicial = QDateEdit()
        self._prepare_form_widget(self.data_inicial, min_width=260)
        self.data_inicial.setDate(QDate.currentDate().addMonths(-1))
        self.data_inicial.setCalendarPopup(True)
        self.data_inicial.setDisplayFormat("dd/MM/yyyy")
        self.data_inicial.dateChanged.connect(self._save_state)
        config_layout.addRow("Data Inicial:", self.data_inicial)

        self.data_final = QDateEdit()
        self._prepare_form_widget(self.data_final, min_width=260)
        self.data_final.setDate(QDate.currentDate())
        self.data_final.setCalendarPopup(True)
        self.data_final.setDisplayFormat("dd/MM/yyyy")
        self.data_final.dateChanged.connect(self._save_state)
        config_layout.addRow("Data Final:", self.data_final)

        self.modo_combo = QComboBox()
        self._prepare_form_widget(self.modo_combo, min_width=520, popup_width=560)
        self.modo_combo.addItems(EXECUTION_MODES.values())
        self.modo_combo.currentIndexChanged.connect(self._save_state)
        config_layout.addRow("Modo de Execução:", self.modo_combo)

        self.download_mode_label = QLabel("Somente XML")
        self.download_mode_label.setStyleSheet("font-weight: 600; color: #0f172a;")
        info_download_mode = QLabel("A captura de PDF oficial foi desativada nesta versão para evitar falhas no fluxo do portal.")
        info_download_mode.setWordWrap(True)
        info_download_mode.setStyleSheet("color: #64748b;")
        download_mode_widget = QWidget()
        download_mode_layout = QVBoxLayout(download_mode_widget)
        download_mode_layout.setContentsMargins(0, 0, 0, 0)
        download_mode_layout.setSpacing(2)
        download_mode_layout.addWidget(self.download_mode_label)
        download_mode_layout.addWidget(info_download_mode)
        config_layout.addRow("Conteúdo do download:", download_mode_widget)

        self.situacao_combo = QComboBox()
        self._prepare_form_widget(self.situacao_combo, min_width=420, popup_width=420)
        self.situacao_combo.addItems(["Todas", "Somente ativas", "Somente canceladas"])
        self.situacao_combo.currentIndexChanged.connect(self._save_state)
        config_layout.addRow("Filtro de situação:", self.situacao_combo)

        layout.addWidget(config_group)

        btn_layout = QHBoxLayout()
        self.btn_executar = QPushButton("▶️ Executar")
        self.btn_executar.clicked.connect(self.start_download)
        btn_layout.addWidget(self.btn_executar)

        self.btn_cancelar = QPushButton("⏹️ Cancelar")
        self.btn_cancelar.clicked.connect(self.cancel_download)
        btn_layout.addWidget(self.btn_cancelar)

        self.btn_abrir_pasta = QPushButton("📂 Abrir pasta")
        self.btn_abrir_pasta.clicked.connect(self.open_download_folder)
        btn_layout.addWidget(self.btn_abrir_pasta)

        self.btn_ver_xmls = QPushButton("📁 Ver XMLs")
        self.btn_ver_xmls.clicked.connect(lambda: app_signals.page_requested.emit("xmls"))
        btn_layout.addWidget(self.btn_ver_xmls)
        
        # ✨ NOVO: Botão de Relatórios
        self.btn_relatorios = QPushButton("📊 Relatórios Inteligentes")
        self.btn_relatorios.clicked.connect(lambda: app_signals.page_requested.emit("relatorios_inteligentes"))
        btn_layout.addWidget(self.btn_relatorios)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p%")
        layout.addWidget(self.progress)

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(8)
        self.results_table.setHorizontalHeaderLabels(["Job", "Empresa", "Período", "Tipo", "XMLs", "Atualizados", "Origem", "Status"])
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setAlternatingRowColors(True)
        layout.addWidget(self.results_table)

        self.status_label = QLabel("Pronto")
        self.status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        app_signals.company_selected.connect(self.set_selected_empresa)
        app_signals.companies_changed.connect(self.refresh_empresas)
        self.refresh_empresas()
        self._restore_state()
        self._reset_steps()
        self._update_summary_cards()
        self._refresh_license_banner()
        log.info("Página de download inicializada com gerenciador de downloads seguro")

    def _build_step_panel(self, parent_layout: QVBoxLayout):
        box = QGroupBox("Etapas do processo")
        layout = QHBoxLayout(box)
        self.step_labels = {}
        for key, text in self.STEP_TITLES:
            frame = QFrame()
            frame.setStyleSheet("background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;")
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(10, 8, 10, 8)
            title = QLabel(text)
            title.setStyleSheet("font-weight: 700; color: #0f172a;")
            status = QLabel("Aguardando")
            status.setStyleSheet("color: #64748b;")
            frame_layout.addWidget(title)
            frame_layout.addWidget(status)
            self.step_labels[key] = status
            layout.addWidget(frame)
        parent_layout.addWidget(box)

    def _build_summary_panel(self, parent_layout: QVBoxLayout):
        box = QGroupBox("Resumo da última execução")
        grid = QGridLayout(box)
        self.summary_labels = {}
        items = [
            ("job", "Job"),
            ("encontrados", "Varridos"),
            ("importados", "Importados"),
            ("atualizados", "Atualizados"),
            ("invalidos", "Inválidos"),
            ("debug", "Pasta debug"),
        ]
        for idx, (key, title) in enumerate(items):
            card = QFrame()
            card.setStyleSheet("background: white; border: 1px solid #e5e7eb; border-radius: 10px;")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 8, 12, 8)
            card_layout.setSpacing(4)
            card_title = QLabel(title)
            card_title.setStyleSheet("color: #64748b; font-size: 11px;")
            card_value = QLabel("0")
            card_value.setStyleSheet("font-size: 18px; font-weight: 700; color: #0f172a;")
            card_layout.addWidget(card_title)
            card_layout.addWidget(card_value)
            self.summary_labels[key] = card_value
            grid.addWidget(card, 0, idx)
        parent_layout.addWidget(box)

    def _prepare_form_widget(self, widget, min_width=None, popup_width=None):
        if min_width:
            widget.setMinimumWidth(min_width)
        if popup_width and isinstance(widget, QComboBox):
            widget.view().setMinimumWidth(popup_width)

    def _combo_changed(self):
        self._save_state()
        self._reset_steps()

    def _save_state(self):
        if self._restoring_state:
            return
        self.settings.setValue("downloader/empresa", self.empresa_combo.currentData() or "")
        self.settings.setValue("downloader/tipo", self.tipo_combo.currentIndex())
        save_qdate(self.settings, "downloader/data_inicial", self.data_inicial.date())
        save_qdate(self.settings, "downloader/data_final", self.data_final.date())
        self.settings.setValue("downloader/modo", self.modo_combo.currentIndex())
        self.settings.setValue("downloader/situacao", self.situacao_combo.currentIndex())

    def _restore_state(self):
        self._restoring_state = True
        try:
            empresa_id = self.settings.value("downloader/empresa", "")
            if empresa_id:
                idx = self.empresa_combo.findData(empresa_id)
                if idx >= 0:
                    self.empresa_combo.setCurrentIndex(idx)
            self.tipo_combo.setCurrentIndex(self.settings.value("downloader/tipo", 0))
            self.data_inicial.setDate(load_qdate(self.settings, "downloader/data_inicial", QDate.currentDate().addMonths(-1)))
            self.data_final.setDate(load_qdate(self.settings, "downloader/data_final", QDate.currentDate()))
            self.modo_combo.setCurrentIndex(self.settings.value("downloader/modo", 0))
            self.situacao_combo.setCurrentIndex(self.settings.value("downloader/situacao", 0))
        finally:
            self._restoring_state = False

    def _reset_steps(self):
        for status_label in self.step_labels.values():
            status_label.setText("Aguardando")
            status_label.setStyleSheet("color: #64748b;")

    def _update_summary_cards(self):
        try:
            job = self.job_repo.get_latest()
            if not job:
                for label in self.summary_labels.values():
                    label.setText("0")
                return
            self.summary_labels["job"].setText(str(job.id))
            self.summary_labels["encontrados"].setText(str(job.total_encontrados or 0))
            self.summary_labels["importados"].setText(str(job.total_importados or 0))
            self.summary_labels["atualizados"].setText(str(job.total_atualizados or 0))
            self.summary_labels["invalidos"].setText(str(job.total_erros or 0))
            self.summary_labels["debug"].setText(job.pasta_debug or "-")
        except Exception as exc:
            log.warning(f"Erro ao atualizar cards: {exc}")

    def _refresh_license_banner(self, force_sync=True):
        try:
            if force_sync:
                self.licensing_service.sync_with_server()
            status = self.licensing_service.get_license_status()
            if status["ativo"]:
                dias = status.get("dias_restantes", 0)
                self.license_banner.setText(f"✅ Licença ativa - {dias} dia(s) restante(s)")
                self.license_banner.setStyleSheet("background: #dcfce7; border: 1px solid #86efac; color: #166534; border-radius: 8px; padding: 8px;")
            else:
                self.license_banner.setText(f"⚠️ Licença inativa - {status.get('motivo', 'Motivo desconhecido')}")
                self.license_banner.setStyleSheet("background: #fee2e2; border: 1px solid #fca5a5; color: #991b1b; border-radius: 8px; padding: 8px;")
        except Exception as exc:
            log.warning(f"Erro ao atualizar banner de licença: {exc}")

    def refresh_empresas(self):
        self.empresa_combo.clear()
        try:
            empresas = self.empresa_repo.get_all()
            for empresa in empresas:
                self.empresa_combo.addItem(f"{empresa.razao_social} - {empresa.cnpj}", empresa.id)
        except Exception as exc:
            log.error(f"Erro ao carregar empresas: {exc}")

    def set_selected_empresa(self, empresa_id: int):
        idx = self.empresa_combo.findData(empresa_id)
        if idx >= 0:
            self.empresa_combo.setCurrentIndex(idx)

    def start_download(self):
        if not self.empresa_combo.currentData():
            QMessageBox.warning(self, "Validação", "Selecione uma empresa antes de executar.")
            return

        empresa_id = self.empresa_combo.currentData()
        tipo = self.tipo_combo.currentText()
        data_ini = self.data_inicial.date().toPython()
        data_fim = self.data_final.date().toPython()
        modo = list(EXECUTION_MODES.keys())[self.modo_combo.currentIndex()]
        situacao = self.situacao_combo.currentText()

        try:
            job = self.job_repo.create(
                empresa_id=empresa_id,
                tipo_documento=tipo,
                data_inicio=data_ini,
                data_fim=data_fim,
                modo_execucao=modo,
                filtro_situacao=situacao,
                status="PENDENTE"
            )
            self._current_job_id = job.id
            self._last_download_dir = None
            
            # ✨ NOVO: Resetar o gerenciador de downloads
            self.download_manager.reset()

            self._worker_thread = QThread()
            self._worker = DownloadWorker(job.id, self.download_manager)
            self._worker.moveToThread(self._worker_thread)
            self._worker_thread.started.connect(self._worker.run)
            self._worker.finished.connect(self._on_download_finished)
            self._worker.error.connect(self._on_download_error)
            self._worker.progress.connect(self._on_download_progress)
            self._worker_thread.finished.connect(self._cleanup_worker)
            self._worker_thread.start()

            self.btn_executar.setEnabled(False)
            self.status_label.setText("Executando...")
            self.status_label.setStyleSheet("color: #2563eb; font-weight: bold;")
            log.info(f"Job {job.id} iniciado para empresa {empresa_id}")

        except Exception as exc:
            log.exception(f"Erro ao iniciar download: {exc}")
            QMessageBox.critical(self, "Erro", f"Erro ao iniciar download: {exc}")

    def _on_download_progress(self, percent: int, message: str):
        self.progress.setValue(percent)
        if message:
            parts = message.split("|")
            if len(parts) >= 2:
                step = parts[0].strip().lower()
                status = parts[1].strip()
                if step in self.step_labels:
                    self.step_labels[step].setText(status)
                    self.step_labels[step].setStyleSheet("color: #2563eb;")

    def _on_download_finished(self, result: JobExecutionSummary):
        self.btn_executar.setEnabled(True)
        self._last_download_dir = result.download_dir
        self._update_summary_cards()

        if result.success:
            message = result.message
            self.status_label.setText(message)
            self.status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
            self.step_labels["importacao"].setText("Concluído")
            self.step_labels["importacao"].setStyleSheet("color: #4CAF50;")
            
            # ✨ NOVO: Preservar downloads completados
            if self.download_manager.get_completed_downloads():
                stats = self.download_manager.get_statistics()
                log.info(f"Downloads preservados: {stats['completed']} arquivo(s)")
        else:
            message = result.message or "Erro desconhecido"
            self.status_label.setText(message)
            self.status_label.setStyleSheet("color: #b91c1c; font-weight: bold;")
            QMessageBox.critical(self, "Download", message)

        self._refresh_license_banner(force_sync=False)

    def _on_download_error(self, error_message: str):
        self.btn_executar.setEnabled(True)
        self.status_label.setText(error_message)
        self.status_label.setStyleSheet("color: #b91c1c; font-weight: bold;")
        QMessageBox.critical(self, "Download", error_message)

    def _cleanup_worker(self):
        self.progress.setRange(0, 100)
        self._refresh_license_banner(force_sync=False)
        self._worker = None
        self._worker_thread = None
        self._current_job_id = None

    def open_download_folder(self):
        folder = Path(self._last_download_dir or "") if self._last_download_dir else None
        if not folder or not str(folder):
            QMessageBox.information(self, "Pasta de downloads", "Ainda não há uma pasta de download definida pela última execução.")
            return
        folder = folder if folder.exists() else folder.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder.resolve())))

    def cancel_download(self):
        if not self._current_job_id:
            QMessageBox.information(self, "Cancelar download", "Nenhum job em execução nesta tela no momento.")
            return
        
        # ✨ NOVO: Solicitar cancelamento seguro
        self.download_manager.request_cancel()
        PortalAutomationService.request_cancel(self._current_job_id)
        
        self.status_label.setText(
            f"Solicitação de cancelamento enviada. Os arquivos já baixados serão preservados..."
        )
        self.status_label.setStyleSheet("color: #f44336; font-weight: bold;")
        log.info(f"Cancelamento seguro solicitado para job {self._current_job_id}")
