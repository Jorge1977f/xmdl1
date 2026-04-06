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
    QFormLayout, QMessageBox, QFrame, QGridLayout, QHeaderView, QSizePolicy, QLineEdit
)

from app.utils.logger import log
from app.db import get_db_session, EmpresaRepository, JobDownloadRepository, CredencialRepository
from app.core import app_signals
from app.services import PortalAutomationService, JobExecutionSummary, LicensingService
from app.services.nfse_api_sync import SincronizadorNFSEAPI
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
            if self.download_manager:
                service.download_manager = self.download_manager
            result = service.execute_job(self.job_id)
            self.finished.emit(result)
        except Exception as exc:
            log.exception(f"Falha no worker do job {self.job_id}: {exc}")
            self.error.emit(str(exc))


class ApiSyncWorker(QObject):
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(int, str)

    def __init__(
        self,
        empresa_id: int,
        cert_path: str,
        cert_password: str,
        ambiente: str,
        job_id: int,
        credencial_id: int | None = None,
        nsu_inicial: int = 0,
        max_documentos: int = 100,
        tipo_nota: str | None = None,
        data_inicial: str | None = None,
        data_final: str | None = None,
        cursor_scope: str | None = None,
    ):
        super().__init__()
        self.empresa_id = empresa_id
        self.cert_path = cert_path
        self.cert_password = cert_password
        self.ambiente = ambiente
        self.job_id = job_id
        self.credencial_id = credencial_id
        self.nsu_inicial = nsu_inicial
        self.max_documentos = max_documentos
        self.tipo_nota = tipo_nota
        self.data_inicial = data_inicial
        self.data_final = data_final
        self.cursor_scope = cursor_scope or "geral"

    def _emit_progress(self, percent: int, message: str):
        self.progress.emit(int(percent), str(message or ""))

    def run(self):
        try:
            sync = SincronizadorNFSEAPI(
                empresa_id=self.empresa_id,
                cert_path=self.cert_path,
                cert_password=self.cert_password,
                ambiente=self.ambiente,
                job_id=self.job_id,
                credencial_id=self.credencial_id,
                progress_callback=self._emit_progress,
            )
            result = sync.sincronizar_dfe(
                nsu_inicial=self.nsu_inicial,
                max_documentos=self.max_documentos,
                max_vazios_consecutivos=2,
                tipo_nota=self.tipo_nota,
                data_inicial=self.data_inicial,
                data_final=self.data_final,
                cursor_scope=self.cursor_scope,
            )
            self.finished.emit(result)
        except Exception as exc:
            log.exception(f"Falha na sincronização API do job {self.job_id}: {exc}")
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
        self.credencial_repo = CredencialRepository(self.session)
        self.settings = get_settings()
        self.licensing_service = LicensingService(self.session)
        self._worker_thread = None
        self._worker = None
        self._restoring_state = False
        self._last_download_dir = None
        self._current_job_id = None
        # ✨ NOVO: Gerenciador de downloads seguro
        self.download_manager = SafeDownloadManager(max_workers=5, preserve_on_cancel=True)

        layout = QVBoxLayout(self)
        title = QLabel("Download de XMLs")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Escolha a empresa, o período e o tipo de nota. Depois use a API ou o portal para baixar os XMLs."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #64748b; margin-bottom: 4px;")
        layout.addWidget(subtitle)

        self.context_label = QLabel("Empresa ativa: nenhuma")
        self.context_label.setStyleSheet("color: #64748b;")
        self.context_label.hide()

        self.license_banner = QLabel()
        self.license_banner.setWordWrap(True)
        self.license_banner.setStyleSheet("background: #eff6ff; border: 1px solid #bfdbfe; color: #1d4ed8; border-radius: 8px; padding: 8px;")
        layout.addWidget(self.license_banner)

        self.step_labels = {}
        self.summary_labels = {}

        config_group = QGroupBox("Baixar XMLs")
        config_layout = QGridLayout(config_group)
        config_layout.setSpacing(12)
        config_layout.setContentsMargins(15, 15, 15, 15)

        empresa_label = QLabel("Empresa:")
        empresa_label.setStyleSheet("font-weight: 600; color: #0f172a;")
        self.empresa_combo = QComboBox()
        self._prepare_form_widget(self.empresa_combo, min_width=560, popup_width=620)
        self.empresa_combo.currentIndexChanged.connect(self._combo_changed)
        config_layout.addWidget(empresa_label, 0, 0)
        config_layout.addWidget(self.empresa_combo, 0, 1, 1, 3)

        data_ini_label = QLabel("Data inicial:")
        data_ini_label.setStyleSheet("font-weight: 600; color: #0f172a;")
        self.data_inicial = QDateEdit()
        self._prepare_form_widget(self.data_inicial, min_width=180)
        self.data_inicial.setDate(QDate.currentDate().addMonths(-1))
        self.data_inicial.setCalendarPopup(True)
        self.data_inicial.setDisplayFormat("dd/MM/yyyy")
        self.data_inicial.dateChanged.connect(self._save_state)

        data_fim_label = QLabel("Data final:")
        data_fim_label.setStyleSheet("font-weight: 600; color: #0f172a;")
        self.data_final = QDateEdit()
        self._prepare_form_widget(self.data_final, min_width=180)
        self.data_final.setDate(QDate.currentDate())
        self.data_final.setCalendarPopup(True)
        self.data_final.setDisplayFormat("dd/MM/yyyy")
        self.data_final.dateChanged.connect(self._save_state)

        tipo_label = QLabel("Tipo:")
        tipo_label.setStyleSheet("font-weight: 600; color: #0f172a;")
        self.tipo_combo = QComboBox()
        self._prepare_form_widget(self.tipo_combo, min_width=220, popup_width=240)
        self.tipo_combo.addItems(["NFS-e Tomada", "NFS-e Prestada", "NFS-e Ambas"])
        self.tipo_combo.currentIndexChanged.connect(self._save_state)
        self.tipo_combo.currentTextChanged.connect(self._on_tipo_combo_changed)

        config_layout.addWidget(data_ini_label, 1, 0)
        config_layout.addWidget(self.data_inicial, 1, 1)
        config_layout.addWidget(data_fim_label, 1, 2)
        config_layout.addWidget(self.data_final, 1, 3)
        config_layout.addWidget(tipo_label, 2, 0)
        config_layout.addWidget(self.tipo_combo, 2, 1)

        nsu_label = QLabel("NSU inicial API:")
        nsu_label.setStyleSheet("font-weight: 600; color: #0f172a;")
        self.api_nsu_input = QLineEdit()
        self._prepare_form_widget(self.api_nsu_input, min_width=180)
        self.api_nsu_input.setPlaceholderText("Ex.: 12345")
        self.api_nsu_input.editingFinished.connect(self._save_state)

        qtd_nsu_label = QLabel("Quantidade de consulta:")
        qtd_nsu_label.setStyleSheet("font-weight: 600; color: #0f172a;")
        self.api_lote_input = QLineEdit()
        self._prepare_form_widget(self.api_lote_input, min_width=140)
        self.api_lote_input.setPlaceholderText("100")
        self.api_lote_input.setText("100")
        self.api_lote_input.editingFinished.connect(self._save_state)

        config_layout.addWidget(nsu_label, 2, 2)
        config_layout.addWidget(self.api_nsu_input, 2, 3)
        config_layout.addWidget(qtd_nsu_label, 3, 0)
        config_layout.addWidget(self.api_lote_input, 3, 1)

        self.modo_combo = QComboBox()
        self.modo_combo.addItems(EXECUTION_MODES.values())
        self.modo_combo.setCurrentIndex(0)
        self.modo_combo.hide()
        self.situacao_combo = QComboBox()
        self.situacao_combo.addItems(["Todas", "Somente ativas", "Somente canceladas"])
        self.situacao_combo.setCurrentText("Todas")
        self.situacao_combo.hide()

        self.download_mode_label = QLabel("Somente XML")
        self.download_mode_label.setStyleSheet("font-weight: 600; color: #0f172a;")
        self.api_nsu_hint = QLabel("Ao trocar de empresa, o sistema tenta carregar o último NSU salvo no banco.")
        self.api_nsu_hint.setWordWrap(True)
        self.api_nsu_hint.setStyleSheet("color: #64748b;")
        config_layout.addWidget(self.download_mode_label, 3, 2)
        config_layout.addWidget(self.api_nsu_hint, 3, 3)

        layout.addWidget(config_group)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        # Botões de execução
        self.btn_sincronizar_api = QPushButton("⚡ Baixar via API")
        self.btn_sincronizar_api.clicked.connect(self._sincronizar_via_api)
        btn_layout.addWidget(self.btn_sincronizar_api)
        
        self.btn_executar = QPushButton("⬇️ Baixar pelo portal")
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
        box.setMinimumHeight(120)  # Restaurar altura mínima
        layout = QHBoxLayout(box)
        layout.setSpacing(12)  # Aumentar espaçamento entre etapas
        layout.setContentsMargins(15, 15, 15, 15)  # Aumentar margens
        self.step_labels = {}
        for key, text in self.STEP_TITLES:
            frame = QFrame()
            frame.setStyleSheet("background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px;")
            frame.setMinimumHeight(90)  # Altura mínima para cada frame
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(12, 12, 12, 12)  # Aumentar margens internas
            frame_layout.setSpacing(8)  # Espaço entre elementos
            title = QLabel(text)
            title.setStyleSheet("font-weight: 700; color: #0f172a; font-size: 12px;")
            status = QLabel("Aguardando")
            status.setStyleSheet("color: #64748b; font-size: 11px;")
            frame_layout.addWidget(title)
            frame_layout.addWidget(status)
            frame_layout.addStretch()  # Adicionar espaço flexível
            self.step_labels[key] = status
            layout.addWidget(frame)
        parent_layout.addWidget(box)

    def _build_summary_panel(self, parent_layout: QVBoxLayout):
        box = QGroupBox("Resumo da última execução")
        box.setMinimumHeight(140)  # Restaurar altura mínima
        grid = QGridLayout(box)
        grid.setSpacing(15)  # Aumentar espaçamento entre cards
        grid.setContentsMargins(15, 15, 15, 15)  # Aumentar margens
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
            card.setStyleSheet("background: white; border: 1px solid #e5e7eb; border-radius: 10px; padding: 12px;")
            card.setMinimumHeight(80)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 12, 12, 12)
            card_layout.setSpacing(8)
            label_title = QLabel(title)
            label_title.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 600;")
            label_value = QLabel("-")
            label_value.setStyleSheet("font-size: 18px; font-weight: 700; color: #0f172a;")
            label_value.setWordWrap(True)
            card_layout.addWidget(label_title)
            card_layout.addWidget(label_value)
            card_layout.addStretch()
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
        if not self.summary_labels:
            return
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
            label = self.summary_labels.get(key)
            if label:
                label.setText(value)

    def _restore_state(self):
        self._restoring_state = True
        self.tipo_combo.setCurrentText(self.settings.value("download/tipo", "NFS-e Tomada") or "NFS-e Tomada")
        self.modo_combo.setCurrentText(self.settings.value("download/modo", list(EXECUTION_MODES.values())[0]) or list(EXECUTION_MODES.values())[0])
        self.situacao_combo.setCurrentText(self.settings.value("download/situacao_filtro", "Todas") or "Todas")
        self.data_inicial.setDate(load_qdate(self.settings, "download/data_inicial", QDate.currentDate().addMonths(-1)))
        self.data_final.setDate(load_qdate(self.settings, "download/data_final", QDate.currentDate()))
        self.api_lote_input.setText(str(self.settings.value("download/api_lote_nsu", "100") or "100"))
        remembered_company = self.settings.value("download/empresa_id")
        if remembered_company not in (None, "", "None"):
            try:
                idx = self.empresa_combo.findData(int(remembered_company))
                if idx >= 0:
                    self.empresa_combo.setCurrentIndex(idx)
            except Exception:
                pass
        remembered_nsu = self.settings.value("download/api_nsu_inicial")
        if remembered_nsu not in (None, "None"):
            self.api_nsu_input.setText(str(remembered_nsu or ""))
        self._restoring_state = False
        self._load_api_nsu_for_selected_company()

    def _save_state(self, *_args):
        if self._restoring_state:
            return
        self.settings.setValue("download/empresa_id", "" if self.empresa_combo.currentData() is None else str(self.empresa_combo.currentData()))
        self.settings.setValue("download/tipo", self.tipo_combo.currentText())
        self.settings.setValue("download/modo", self.modo_combo.currentText())
        self.settings.setValue("download/situacao_filtro", self.situacao_combo.currentText())
        self.settings.setValue("download/api_nsu_inicial", self.api_nsu_input.text().strip())
        self.settings.setValue("download/api_lote_nsu", self.api_lote_input.text().strip() or "100")
        save_qdate(self.settings, "download/data_inicial", self.data_inicial.date())
        save_qdate(self.settings, "download/data_final", self.data_final.date())

    def _parse_positive_int(self, value, default: int = 0) -> int:
        raw = re.sub(r"\D", "", str(value or "").strip())
        if not raw:
            return int(default)
        try:
            return max(0, int(raw))
        except Exception:
            return int(default)

    def _cursor_scope_for_selected_type(self) -> str:
        tipo_texto = (self.tipo_combo.currentText() or "").lower()
        if "ambas" in tipo_texto or "todos" in tipo_texto:
            return "geral"
        if "tomad" in tipo_texto or "entrada" in tipo_texto:
            return "tomadas"
        if "prestad" in tipo_texto or "saída" in tipo_texto or "saida" in tipo_texto:
            return "prestadas"
        return "geral"

    def _saved_nsu_for_scope(self, credencial_cert, scope: str) -> int | None:
        if not credencial_cert:
            return None
        if scope == "prestadas":
            value = getattr(credencial_cert, "ultimo_nsu_api_prestadas", None)
            if value not in (None, ""):
                return int(value)
        elif scope == "tomadas":
            value = getattr(credencial_cert, "ultimo_nsu_api_tomadas", None)
            if value not in (None, ""):
                return int(value)
        value = getattr(credencial_cert, "ultimo_nsu_api", None)
        if value not in (None, ""):
            return int(value)
        return None

    def _scope_label(self, scope: str) -> str:
        return {
            "prestadas": "prestadas/saídas",
            "tomadas": "tomadas/entradas",
            "geral": "geral",
        }.get(scope, scope)

    def _on_tipo_combo_changed(self):
        self._load_api_nsu_for_selected_company()
        self._save_state()

    def _load_api_nsu_for_selected_company(self):
        empresa_id = self.empresa_combo.currentData()
        scope = self._cursor_scope_for_selected_type()
        scope_label = self._scope_label(scope)
        if not empresa_id:
            self.api_nsu_hint.setText("Ao trocar de empresa, o sistema tenta carregar o último NSU salvo no banco.")
            return

        credencial_cert = self.credencial_repo.get_ativo_by_empresa(empresa_id, "CERTIFICADO")
        if not credencial_cert:
            self.api_nsu_hint.setText("Sem certificado ativo para esta empresa. O NSU será informado manualmente.")
            return

        nsu_salvo = self._saved_nsu_for_scope(credencial_cert, scope)
        lote_salvo = getattr(credencial_cert, "lote_nsu_api", None)

        if nsu_salvo not in (None, ""):
            self.api_nsu_input.setText(str(nsu_salvo))
            self.api_nsu_hint.setText(f"Último NSU salvo no banco para {scope_label}: {nsu_salvo}")
        else:
            self.api_nsu_hint.setText(f"Nenhum NSU salvo ainda para {scope_label}. Informe o NSU inicial desejado.")

        if lote_salvo not in (None, ""):
            self.api_lote_input.setText(str(lote_salvo))

        self._save_state()

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
        self._load_api_nsu_for_selected_company()
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
        self._load_api_nsu_for_selected_company()
        self._save_state()

    def on_page_activated(self):
        self.refresh_empresas(self.empresa_combo.currentData())
        self._refresh_license_banner(force_sync=False)

    def _combo_changed(self):
        self._update_context_label()
        self._load_api_nsu_for_selected_company()
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
            QMessageBox.warning(self, "Download", "Selecione uma empresa antes de baixar pelo portal.")
            return
        if "Ambas" in (self.tipo_combo.currentText() or ""):
            QMessageBox.information(
                self,
                "Baixar pelo portal",
                "Para o portal, escolha NFS-e Tomada ou NFS-e Prestada.\n\n"
                "A opção NFS-e Ambas está disponível na sincronização via API."
            )
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
            f"Job {job.id} criado. O sistema vai acessar o portal da empresa, aplicar o período e tentar baixar os XMLs. "
            "Se houver certificado, faça somente a seleção e aguarde a continuação automática."
        )
        self.status_label.setStyleSheet("color: #2196F3; font-weight: bold;")
        self.btn_executar.setEnabled(False)

        self._worker_thread = QThread(self)
        # ✨ NOVO: Passar o gerenciador de downloads seguro
        self._worker = DownloadWorker(job.id, self.download_manager)
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

    def _on_api_progress(self, percent: int, message: str):
        percent = max(0, min(100, int(percent)))
        self.progress.setRange(0, 100)
        self.progress.setValue(percent)
        self.progress.setFormat(f"{percent}%")
        lower_message = (message or "").lower()
        if "certificado" in lower_message or "mtls" in lower_message:
            self._set_step("certificado", f"Em andamento ({percent}%)", "#2563eb")
        if "api" in lower_message or "adn" in lower_message or "nsu" in lower_message:
            self._set_step("portal", f"Em andamento ({percent}%)", "#2563eb")
            self._set_step("periodo", f"Em andamento ({percent}%)", "#2563eb")
        if "salvo" in lower_message or "documento" in lower_message or "retorno" in lower_message:
            self._set_step("download", f"Em andamento ({percent}%)", "#2563eb")
        self._update_running_row(percent, f"EXECUTANDO {percent}%", self._extract_download_hint(message))
        self.status_label.setText(message or "Sincronizando via API...")
        self.status_label.setStyleSheet("color: #2563eb; font-weight: bold;")

    def _on_api_finished(self, result: dict):
        documentos_salvos = int(result.get("documentos_salvos") or 0)
        documentos_filtrados = int(result.get("documentos_filtrados") or 0)
        importados = int(result.get("importados") or 0)
        atualizados = int(result.get("atualizados") or 0)
        consultas_api = int(result.get("consultas_api") or 0)
        parcial = bool(result.get("parcial"))
        sucesso = bool(result.get("sucesso"))
        pasta_saida = result.get("pasta_saida") or "-"
        self._last_download_dir = pasta_saida
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if documentos_salvos else 0)
        self.progress.setFormat("100%" if documentos_salvos else "0%")
        self._set_step("certificado", "mTLS validado", "#166534" if documentos_salvos or sucesso else "#b91c1c")
        self._set_step("portal", f"ADN consultado ({consultas_api} chamada(s))", "#166534" if documentos_salvos or sucesso else "#b91c1c")
        self._set_step("periodo", f"{documentos_filtrados} no período/filtro", "#166534" if documentos_filtrados else "#b45309")
        self._set_step("download", f"{documentos_salvos} XML(s) extraído(s)", "#166534" if documentos_salvos else "#b45309")
        self._set_step("importacao", f"{importados} importado(s) / {atualizados} atualizado(s)", "#166534" if importados or atualizados else "#b45309")
        cor = "#166534" if sucesso else ("#b45309" if parcial or documentos_salvos else "#b91c1c")
        self.status_label.setStyleSheet(f"color: {cor}; font-weight: bold;")
        nsu_final = result.get('nsu_final', '-')
        cursor_scope = result.get('cursor_scope') or self._cursor_scope_for_selected_type()
        self.api_nsu_input.setText(str(nsu_final))
        self.api_nsu_hint.setText(f"Último NSU salvo para {self._scope_label(cursor_scope)}: {nsu_final}")
        self.status_label.setText(
            f"{result.get('mensagem', 'Sincronização via API concluída.')}\n"
            f"Pasta saída: {pasta_saida}\n"
            f"Pasta XML: {result.get('pasta_xml', '-')} | Pasta filtro: {result.get('pasta_matched', '-')}\n"
            f"Manifesto: {result.get('manifesto', '-')}\n"
            f"NSU inicial: {result.get('nsu_inicial', '-')} | Último NSU salvo: {nsu_final} | Consultas API: {consultas_api} | Erros: {len(result.get('erros') or [])}"
        )
        self.results_table.setRowCount(1)
        period_str = f"{self.data_inicial.date().toString('dd/MM/yyyy')} a {self.data_final.date().toString('dd/MM/yyyy')}"
        values = [
            str(self._current_job_id or "-"),
            self.empresa_combo.currentText(),
            period_str,
            self.tipo_combo.currentText(),
            str(documentos_filtrados or documentos_salvos),
            str(len(result.get('erros') or [])),
            "API",
            "CONCLUÍDO" if sucesso else ("PARCIAL" if parcial or documentos_salvos else "SEM RETORNO"),
        ]
        for col, value in enumerate(values):
            self.results_table.setItem(0, col, QTableWidgetItem(value))
        resumo_periodo = result.get("resumo_periodo") or {}
        linhas_resumo = []
        if resumo_periodo.get("periodo_solicitado"):
            linhas_resumo.append(f"Período solicitado: {resumo_periodo['periodo_solicitado']}")
        if resumo_periodo.get("periodo_localizado"):
            linhas_resumo.append(f"Período localizado nos XMLs: {resumo_periodo['periodo_localizado']}")
        totais = resumo_periodo.get("totais") or {}
        if totais:
            linhas_resumo.append(
                "Encontradas no lote antes do filtro: "
                f"prestadas={totais.get('prestadas', 0)}, "
                f"tomadas={totais.get('tomadas', 0)}, "
                f"outras={totais.get('outras', 0)}"
            )
            linhas_resumo.append(
                "Aproveitadas pelo filtro selecionado: "
                f"total={totais.get('filtradas', 0)}, "
                f"prestadas={totais.get('filtradas_prestadas', 0)}, "
                f"tomadas={totais.get('filtradas_tomadas', 0)}, "
                f"outras={totais.get('filtradas_outras', 0)}"
            )
            linhas_resumo.append(f"Relatório salvo: {resumo_periodo['arquivo_txt']}")
        if linhas_resumo:
            self.status_label.setText(self.status_label.text() + "\n" + "\n".join(linhas_resumo))
            QMessageBox.information(self, "Resumo da importação via API", "\n".join(linhas_resumo))

    def _on_api_error(self, error_message: str):
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("0%")
        self._update_running_row(0, "ERRO", "-")
        self._set_step("certificado", "Falhou", "#b91c1c")
        self._set_step("portal", "Falhou", "#b91c1c")
        self._set_step("periodo", "Interrompido", "#b91c1c")
        self._set_step("download", "Interrompido", "#b91c1c")
        self._set_step("importacao", "Interrompida", "#b91c1c")
        self.status_label.setText(f"Falha na sincronização via API: {error_message}")
        self.status_label.setStyleSheet("color: #b91c1c; font-weight: bold;")
        if self._current_job_id:
            try:
                self.job_repo.update(self._current_job_id, status="ERRO", fim_em=datetime.utcnow(), log_resumo=error_message)
            except Exception:
                pass
        QMessageBox.critical(self, "API NFSe", error_message)

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
        self.btn_executar.setEnabled(True)
        self.btn_sincronizar_api.setEnabled(True)

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
        # NOVO: Cancelamento seguro que preserva downloads
        self.download_manager.request_cancel()
        PortalAutomationService.request_cancel(self._current_job_id)
        self.status_label.setText(
            f"Cancelamento solicitado. Os arquivos já baixados serão preservados..."
        )
        self.status_label.setStyleSheet("color: #f44336; font-weight: bold;")
        log.info(f"Cancelamento seguro solicitado para job {self._current_job_id}")

    def _sincronizar_via_api(self):
        """Sincroniza documentos diretamente no ADN da NFS-e."""
        try:
            empresa_id = self.empresa_combo.currentData()
            empresa_nome = self.empresa_combo.currentText()
            if not empresa_id or not empresa_nome or empresa_nome == "Selecione uma empresa":
                QMessageBox.warning(self, "Aviso", "Selecione uma empresa primeiro")
                return

            credencial_cert = self.credencial_repo.get_ativo_by_empresa(empresa_id, "CERTIFICADO")
            if not credencial_cert or not credencial_cert.cert_path:
                QMessageBox.warning(self, "API NFSe", "Configure primeiro o certificado digital da empresa na tela Configurações.")
                return
            if not credencial_cert.cert_senha:
                QMessageBox.warning(self, "API NFSe", "A senha do certificado não foi encontrada. Reabra Configurações e salve novamente o certificado.")
                return

            cert_path = Path(credencial_cert.cert_path)
            if not cert_path.exists():
                QMessageBox.critical(self, "API NFSe", f"O certificado salvo não foi encontrado:\n{cert_path}")
                return

            portal_cfg = self.credencial_repo.get_ativo_by_empresa(empresa_id, "PORTAL")
            ambiente = "homologacao" if (portal_cfg and (portal_cfg.ambiente or "").upper().startswith("HOMO")) else "producao"

            cursor_scope = self._cursor_scope_for_selected_type()
            nsu_padrao = self._saved_nsu_for_scope(credencial_cert, cursor_scope) or 0
            nsu_inicial = self._parse_positive_int(self.api_nsu_input.text(), default=nsu_padrao)
            max_documentos = self._parse_positive_int(self.api_lote_input.text(), default=getattr(credencial_cert, "lote_nsu_api", 100) or 100)
            max_documentos = max(1, max_documentos or 100)
            self.api_nsu_input.setText(str(nsu_inicial))
            self.api_lote_input.setText(str(max_documentos))
            self._save_state()

            tipo_texto = self.tipo_combo.currentText()
            if "Ambas" in tipo_texto:
                tipo_nota = None
            elif "Tomada" in tipo_texto:
                tipo_nota = "tomadas"
            else:
                tipo_nota = "prestadas"
            data_inicial = self.data_inicial.date().toString("yyyy-MM-dd")
            data_final = self.data_final.date().toString("yyyy-MM-dd")

            from datetime import datetime
            d_ini = datetime.strptime(data_inicial, "%Y-%m-%d")
            d_fim = datetime.strptime(data_final, "%Y-%m-%d")
            dias = (d_fim - d_ini).days + 1

            if d_fim < d_ini:
                QMessageBox.warning(
                    self,
                    "Período Inválido",
                    "A data final não pode ser menor que a data inicial."
                )
                return

            job = self.job_repo.create(
                empresa_id=empresa_id,
                tipo_documento=f"API {self.tipo_combo.currentText()}",
                data_inicial=d_ini,
                data_final=d_fim,
                modo_execucao="API_ADN",
                status="EXECUTANDO",
                inicio_em=datetime.utcnow(),
            )
            self._current_job_id = job.id
            period_str = f"{self.data_inicial.date().toString('dd/MM/yyyy')} a {self.data_final.date().toString('dd/MM/yyyy')}"
            self._ensure_running_row(job.id, empresa_nome, period_str, self.tipo_combo.currentText())
            self._reset_steps()
            self._set_step("certificado", "Validando mTLS", "#2563eb")
            self._set_step("portal", "API direta ADN", "#2563eb")
            self._set_step("periodo", "Consulta iniciada", "#2563eb")
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.progress.setFormat("0%")
            self.status_label.setText(
                f"Sincronização via API iniciada para {tipo_texto} ({data_inicial} a {data_final}, {dias} dia(s)).\n"
                f"Ambiente: {ambiente} | NSU inicial/base: {nsu_inicial} | próximos documentos/NSUs: {max_documentos}. Veja também a tela de Logs para o job {job.id}."
            )
            self.status_label.setStyleSheet("color: #2563eb; font-weight: bold;")
            self.btn_sincronizar_api.setEnabled(False)

            self._worker_thread = QThread(self)
            self._worker = ApiSyncWorker(
                empresa_id=empresa_id,
                cert_path=str(cert_path),
                cert_password=credencial_cert.cert_senha,
                ambiente=ambiente,
                job_id=job.id,
                credencial_id=credencial_cert.id,
                nsu_inicial=nsu_inicial,
                max_documentos=max_documentos,
                tipo_nota=(tipo_nota[:-1] if isinstance(tipo_nota, str) and tipo_nota.endswith('s') else tipo_nota),
                data_inicial=data_inicial,
                data_final=data_final,
                cursor_scope=cursor_scope,
            )
            self._worker.moveToThread(self._worker_thread)
            self._worker_thread.started.connect(self._worker.run)
            self._worker.progress.connect(self._on_api_progress)
            self._worker.finished.connect(self._on_api_finished)
            self._worker.error.connect(self._on_api_error)
            self._worker.finished.connect(self._worker_thread.quit)
            self._worker.error.connect(self._worker_thread.quit)
            self._worker_thread.finished.connect(self._cleanup_worker)
            self._worker_thread.start()
            log.info(f"Sincronização via API: {tipo_texto} de {data_inicial} a {data_final} | job={job.id} | ambiente={ambiente} | nsu_inicial={nsu_inicial} | max_documentos={max_documentos}")

        except Exception as e:
            log.exception(f"Erro ao sincronizar via API: {e}")
            QMessageBox.critical(self, "Erro", f"Erro ao sincronizar:\n{str(e)}")

    def _abrir_portal(self):
        """Abre o portal NFSE Nacional em novo navegador"""
        try:
            import webbrowser
            url = "https://www.nfse.gov.br/EmissorNacional"
            webbrowser.open(url)
            
            self.status_label.setText(
                "✓ Portal NFSE Nacional aberto no navegador. "
                "Faça login com seu certificado digital."
            )
            self.status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
            
            QMessageBox.information(
                self,
                "Portal Aberto",
                "O Portal NFSE Nacional foi aberto em seu navegador.\n\n"
                "1. Faça login com seu certificado digital\n"
                "2. Selecione o período desejado\n"
                "3. Baixe os XMLs\n"
                "4. Retorne ao XMDL e clique em 'Executar' para importar"
            )
            log.info("Portal NFSE Nacional aberto")
            
        except Exception as e:
            log.exception(f"Erro ao abrir portal: {e}")
            QMessageBox.critical(self, "Erro", f"Erro ao abrir portal:\n{str(e)}")
