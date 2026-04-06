"""Página principal de download de XMLs."""
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
from app.utils.ui_state import get_settings, save_qdate, load_qdate
from config.settings import EXECUTION_MODES


class DownloadWorker(QObject):
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(int, str)

    def __init__(self, job_id: int):
        super().__init__()
        self.job_id = job_id

    def _emit_progress(self, percent: int, message: str):
        self.progress.emit(int(percent), str(message or ""))

    def run(self):
        try:
            service = PortalAutomationService(progress_callback=self._emit_progress)
            result = service.execute_job(self.job_id)
            self.finished.emit(result)
        except Exception as exc:
            log.exception(f"Falha no worker do job {self.job_id}: {exc}")
            self.error.emit(str(exc))


class DownloaderPage(QWidget):
    """Página de download de XMLs"""

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
        log.info("Página de download inicializada")

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
            card_layout.setContentsMargins(10, 8, 10, 8)
            label_title = QLabel(title)
            label_title.setStyleSheet("color: #64748b; font-size: 12px;")
            label_value = QLabel("-")
            label_value.setStyleSheet("font-size: 16px; font-weight: 700; color: #0f172a;")
            label_value.setWordWrap(True)
            card_layout.addWidget(label_title)
            card_layout.addWidget(label_value)
            self.summary_labels[key] = label_value
            grid.addWidget(card, idx // 3, idx % 3)
        parent_layout.addWidget(box)

    def _prepare_form_widget(self, widget, min_width: int = 420, popup_width: int | None = None):
        target_width = max(260, min_width)
        widget.setMinimumHeight(34)
        widget.setMaximumHeight(34)
        widget.setMinimumWidth(target_width)
        widget.setMaximumWidth(target_width)
        widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        widget.setStyleSheet(
            "QComboBox, QDateEdit { padding: 4px 8px; min-height: 30px; background: white; color: #111827; }"
            "QComboBox QAbstractItemView { min-height: 28px; background: white; color: #111827; selection-background-color: #dbeafe; selection-color: #111827; outline: 0; }"
        )
        if isinstance(widget, QComboBox):
            widget.setMaxVisibleItems(18)
            widget.setMinimumContentsLength(max(18, target_width // 16))
            widget.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            view = widget.view()
            view.setTextElideMode(Qt.ElideNone)
            view.setUniformItemSizes(True)
            if popup_width:
                view.setMinimumWidth(popup_width)
                view.setMaximumWidth(max(popup_width, target_width))

    def _reset_steps(self):
        for key, _title in self.STEP_TITLES:
            self._set_step(key, "Aguardando", "#64748b")

    def _set_step(self, step_key: str, text: str, color: str):
        label = self.step_labels.get(step_key)
        if label:
            label.setText(text)
            label.setStyleSheet(f"color: {color}; font-weight: 600;")

    def _ensure_running_row(self, job_id: int, empresa_nome: str, period_str: str, tipo: str):
        self.results_table.setRowCount(1)
        values = [str(job_id), empresa_nome, period_str, tipo, "0%", "0", "PORTAL", "EXECUTANDO"]
        for col, value in enumerate(values):
            self.results_table.setItem(0, col, QTableWidgetItem(value))

    def _update_running_row(self, percent: int, status: str, imported_hint: str = ""):
        if self.results_table.rowCount() == 0:
            return
        xml_item = self.results_table.item(0, 4)
        if xml_item is None:
            xml_item = QTableWidgetItem()
            self.results_table.setItem(0, 4, xml_item)
        xml_item.setText(f"{max(0, min(100, int(percent)))}%")

        upd_item = self.results_table.item(0, 5)
        if upd_item is None:
            upd_item = QTableWidgetItem()
            self.results_table.setItem(0, 5, upd_item)
        upd_item.setText(imported_hint or "-")

        status_item = self.results_table.item(0, 7)
        if status_item is None:
            status_item = QTableWidgetItem()
            self.results_table.setItem(0, 7, status_item)
        status_item.setText(status)

    def _extract_download_hint(self, message: str) -> str:
        msg = message or ""
        page_part = ""
        item_part = ""

        page_match = re.search(r"p[aá]gina\s+(\d+)\s+de\s+(\d+)", msg, re.IGNORECASE)
        if page_match:
            page_part = f"pág {page_match.group(1)}/{page_match.group(2)}"
        else:
            page_match = re.search(r"p[aá]gina\s+(\d+)", msg, re.IGNORECASE)
            if page_match:
                page_part = f"pág {page_match.group(1)}"

        item_match = re.search(r"item\s+(\d+)\s+de\s+(\d+)", msg, re.IGNORECASE)
        if item_match:
            item_part = f"item {item_match.group(1)}/{item_match.group(2)}"

        parts = [part for part in (page_part, item_part) if part]
        if parts:
            return " | ".join(parts)
        if "importando" in msg.lower():
            return "Importando"
        return "-"

    def _update_summary_cards(self, result: JobExecutionSummary | None = None):
        values = {
            "job": "-",
            "encontrados": "0",
            "importados": "0",
            "atualizados": "0",
            "invalidos": "0",
            "debug": "-",
        }
        if result:
            values.update({
                "job": str(result.job_id),
                "encontrados": str(result.files_scanned),
                "importados": str(result.files_imported),
                "atualizados": str(result.files_updated),
                "invalidos": str(result.files_invalid),
                "debug": result.debug_dir or "-",
            })
        for key, value in values.items():
            self.summary_labels[key].setText(value)

    def _restore_state(self):
        self._restoring_state = True
        self.tipo_combo.setCurrentText(self.settings.value("download/tipo", "NFS-e Tomada") or "NFS-e Tomada")
        self.modo_combo.setCurrentText(self.settings.value("download/modo", list(EXECUTION_MODES.values())[0]) or list(EXECUTION_MODES.values())[0])
        self.situacao_combo.setCurrentText(self.settings.value("download/situacao_filtro", "Todas") or "Todas")
        self.data_inicial.setDate(load_qdate(self.settings, "download/data_inicial", QDate.currentDate().addMonths(-1)))
        self.data_final.setDate(load_qdate(self.settings, "download/data_final", QDate.currentDate()))
        remembered_company = self.settings.value("download/empresa_id")
        if remembered_company not in (None, "", "None"):
            try:
                idx = self.empresa_combo.findData(int(remembered_company))
                if idx >= 0:
                    self.empresa_combo.setCurrentIndex(idx)
            except Exception:
                pass
        self._restoring_state = False

    def _save_state(self, *_args):
        if self._restoring_state:
            return
        self.settings.setValue("download/empresa_id", "" if self.empresa_combo.currentData() is None else str(self.empresa_combo.currentData()))
        self.settings.setValue("download/tipo", self.tipo_combo.currentText())
        self.settings.setValue("download/modo", self.modo_combo.currentText())
        self.settings.setValue("download/situacao_filtro", self.situacao_combo.currentText())
        save_qdate(self.settings, "download/data_inicial", self.data_inicial.date())
        save_qdate(self.settings, "download/data_final", self.data_final.date())

    def refresh_empresas(self, select_company_id=None):
        empresas = self.empresa_repo.list_all()
        remembered_company = self.settings.value("download/empresa_id")
        target_company_id = select_company_id
        if target_company_id is None and remembered_company not in (None, "", "None"):
            try:
                target_company_id = int(remembered_company)
            except Exception:
                target_company_id = None

        self.empresa_combo.blockSignals(True)
        self.empresa_combo.clear()
        self.empresa_combo.addItem("Selecione uma empresa", None)
        for empresa in empresas:
            self.empresa_combo.addItem(f"{empresa.razao_social} - {empresa.cnpj}", empresa.id)
        idx = self.empresa_combo.findData(target_company_id)
        self.empresa_combo.setCurrentIndex(idx if idx >= 0 else (1 if empresas else 0))
        self.empresa_combo.blockSignals(False)
        self._update_context_label()
        self._save_state()

    def set_selected_empresa(self, empresa_id):
        idx = self.empresa_combo.findData(empresa_id)
        self.empresa_combo.blockSignals(True)
        if idx >= 0:
            self.empresa_combo.setCurrentIndex(idx)
        elif self.empresa_combo.count():
            self.empresa_combo.setCurrentIndex(0)
        self.empresa_combo.blockSignals(False)
        self._update_context_label()
        self._save_state()

    def on_page_activated(self):
        self.refresh_empresas(self.empresa_combo.currentData())
        self._refresh_license_banner(force_sync=False)

    def _combo_changed(self):
        self._update_context_label()
        self._save_state()
        app_signals.company_selected.emit(self.empresa_combo.currentData())

    def _update_context_label(self):
        empresa_id = self.empresa_combo.currentData()
        if empresa_id:
            empresa = self.empresa_repo.get_by_id(empresa_id)
            if empresa:
                self.context_label.setText(f"Empresa ativa: {empresa.razao_social} - {empresa.cnpj}")
                return
        self.context_label.setText("Empresa ativa: nenhuma")

    def _refresh_license_banner(self, force_sync: bool = False):
        snapshot = self.licensing_service.get_snapshot(force_sync=force_sync)
        color_bg = "#eff6ff"
        color_border = "#bfdbfe"
        color_text = "#1d4ed8"
        if snapshot.status in {"TRIAL_EXPIRADO", "PAGAMENTO_PENDENTE"}:
            color_bg = "#fff7ed"
            color_border = "#fdba74"
            color_text = "#c2410c"
        elif snapshot.status == "ATIVA":
            color_bg = "#ecfdf5"
            color_border = "#86efac"
            color_text = "#166534"
        self.license_banner.setStyleSheet(f"background: {color_bg}; border: 1px solid {color_border}; color: {color_text}; border-radius: 8px; padding: 8px;")
        head = f"Licença: {snapshot.status_label}"
        if snapshot.status == "TRIAL" and snapshot.days_left is not None:
            head += f" · {snapshot.days_left} dia(s) restantes"
        self.license_banner.setText(head + "\n" + snapshot.message)
        self.btn_executar.setEnabled(snapshot.downloads_allowed and not (self._worker_thread and self._worker_thread.isRunning()))

    def start_download(self):
        if self._worker_thread and self._worker_thread.isRunning():
            QMessageBox.information(self, "Download", "Já existe um job em execução nesta tela.")
            return

        allowed, reason, snapshot = self.licensing_service.can_start_download()
        self._refresh_license_banner(force_sync=False)
        if not allowed:
            QMessageBox.warning(self, "Download bloqueado", reason)
            if snapshot.status in {"NAO_CADASTRADO", "TRIAL_EXPIRADO", "PAGAMENTO_PENDENTE"}:
                app_signals.page_requested.emit("licencas")
            return

        empresa_id = self.empresa_combo.currentData()
        if not empresa_id:
            QMessageBox.warning(self, "Download", "Selecione uma empresa antes de executar.")
            return

        self._save_state()
        data_inicial = datetime.combine(self.data_inicial.date().toPython(), datetime.min.time())
        data_final = datetime.combine(self.data_final.date().toPython(), datetime.max.time())
        empresa = self.empresa_repo.get_by_id(empresa_id)
        empresa_nome = f"{empresa.razao_social} - {empresa.cnpj}" if empresa else "-"
        period_str = f"{self.data_inicial.date().toString('dd/MM/yyyy')} a {self.data_final.date().toString('dd/MM/yyyy')}"
        import json
        payload = {
            "download_mode": "XML_ONLY",
            "download_mode_label": "Somente XML",
            "situacao_filtro": self.situacao_combo.currentText(),
        }
        job = self.job_repo.create(
            empresa_id=empresa_id,
            tipo_documento=self.tipo_combo.currentText(),
            data_inicial=data_inicial,
            data_final=data_final,
            modo_execucao=self.modo_combo.currentText(),
            status="PENDENTE",
            log_resumo=json.dumps(payload, ensure_ascii=False),
        )

        self._reset_steps()
        self._set_step("certificado", "Preparando acesso", "#2563eb")
        self._set_step("portal", "Aguardando abertura", "#64748b")
        self._set_step("periodo", "Aguardando consulta", "#64748b")
        self._set_step("download", "Aguardando XMLs", "#64748b")
        self._set_step("importacao", "Aguardando importação", "#64748b")
        self._update_summary_cards()

        self.progress.setRange(0, 100)
        self.progress.setValue(3)
        self.progress.setFormat("3%")
        self._current_job_id = job.id
        self._ensure_running_row(job.id, empresa_nome, period_str, self.tipo_combo.currentText())
        self.status_label.setText(
            f"Job {job.id} criado. O sistema vai abrir o portal da empresa, aplicar o período e tentar baixar os XMLs. "
            "Se houver certificado, faça somente a seleção e aguarde a continuação automática."
        )
        self.status_label.setStyleSheet("color: #2196F3; font-weight: bold;")
        self.btn_executar.setEnabled(False)

        self._worker_thread = QThread(self)
        self._worker = DownloadWorker(job.id)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_download_progress)
        self._worker.finished.connect(self._on_download_finished)
        self._worker.error.connect(self._on_download_error)
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker.error.connect(self._worker_thread.quit)
        self._worker_thread.finished.connect(self._cleanup_worker)
        self._worker_thread.start()
        log.info(f"Download iniciado: job {job.id}")

    def _on_download_progress(self, percent: int, message: str):
        percent = max(0, min(100, int(percent)))
        self.progress.setRange(0, 100)
        self.progress.setValue(percent)
        self.progress.setFormat(f"{percent}%")
        if message:
            lower_message = message.lower()
            if "preparando acesso" in lower_message or "validando certificado" in lower_message:
                self._set_step("certificado", f"Em andamento ({percent}%)", "#2563eb")
            elif "abrindo portal" in lower_message or "portal carregado" in lower_message:
                self._set_step("portal", f"Em andamento ({percent}%)", "#2563eb")
            elif "período" in lower_message or "periodo" in lower_message or "consulta" in lower_message or "página" in lower_message or "pagina" in lower_message:
                self._set_step("periodo", f"Em andamento ({percent}%)", "#2563eb")
            if "baixando xml" in lower_message or "item" in lower_message:
                self._set_step("download", f"Em andamento ({percent}%)", "#2563eb")
            if "importando xml" in lower_message or "banco de dados" in lower_message:
                self._set_step("importacao", f"Em andamento ({percent}%)", "#2563eb")
            imported_hint = self._extract_download_hint(message)
            self._update_running_row(percent, f"EXECUTANDO {percent}%", imported_hint)
            self.status_label.setText(f"{message}\nProgresso do job: {percent}%")
            self.status_label.setStyleSheet("color: #2563eb; font-weight: bold;")

    def _on_download_finished(self, result: JobExecutionSummary):
        self._last_download_dir = result.download_dir
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if result.success else 0)
        self.progress.setFormat("100%" if result.success else "0%")
        color = "#166534" if result.success else "#b45309"
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.status_label.setText(
            f"{result.message}\n"
            f"Pasta monitorada: {result.download_dir}\n"
            f"Varridos: {result.files_scanned} | Importados: {result.files_imported} | Atualizados: {result.files_updated} | Inválidos: {result.files_invalid}"
        )
        self._update_summary_cards(result)

        if result.login_attempted:
            self._set_step("certificado", "Acesso iniciado", "#166534")
        else:
            self._set_step("certificado", "Seleção assistida", "#166534" if result.opened_portal else "#b45309")
        self._set_step("portal", "Portal tratado", "#166534" if result.opened_portal else "#b45309")
        self._set_step("periodo", "Período consultado", "#166534" if result.files_scanned or result.success else "#b45309")
        self._set_step("download", f"{result.files_imported + result.files_updated} XML(s)", "#166534" if (result.files_imported + result.files_updated) else "#b45309")
        self._set_step("importacao", "Concluída" if result.success else "Sem novos XMLs", "#166534" if result.success else "#b45309")

        self.results_table.setRowCount(1)
        period_str = f"{self.data_inicial.date().toString('dd/MM/yyyy')} a {self.data_final.date().toString('dd/MM/yyyy')}"
        values = [
            str(result.job_id),
            result.empresa_nome,
            period_str,
            self.tipo_combo.currentText(),
            str(result.files_imported),
            str(result.files_updated),
            "PORTAL",
            "CONCLUÍDO" if result.success else "SEM XML",
        ]
        for col, value in enumerate(values):
            self.results_table.setItem(0, col, QTableWidgetItem(value))
        app_signals.companies_changed.emit(self.empresa_combo.currentData())

    def _on_download_error(self, error_message: str):
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("0%")
        self._update_running_row(0, "ERRO", "-")
        self._set_step("certificado", "Falhou", "#b91c1c")
        self._set_step("portal", "Falhou", "#b91c1c")
        self._set_step("periodo", "Interrompido", "#b91c1c")
        self._set_step("download", "Interrompido", "#b91c1c")
        self._set_step("importacao", "Interrompida", "#b91c1c")
        self.status_label.setText(f"Falha ao executar o job: {error_message}")
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
        PortalAutomationService.request_cancel(self._current_job_id)
        self.status_label.setText(
            f"Solicitação de cancelamento enviada para o job {self._current_job_id}. O sistema vai interromper no próximo ponto seguro."
        )
        self.status_label.setStyleSheet("color: #f44336; font-weight: bold;")
        log.info(f"Solicitação de cancelamento enviada ao job {self._current_job_id}")
