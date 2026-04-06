"""
Página de gerenciamento de manifestação
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QMessageBox
)
from app.utils.logger import log
from app.db import get_db_session, EmpresaRepository
from app.db.models import FilaManifestacao
from app.core import app_signals


class ManifestacaoPage(QWidget):
    """Página de gerenciamento de manifestação"""

    def __init__(self):
        super().__init__()
        self.session = get_db_session()
        self.empresa_repo = EmpresaRepository(self.session)
        self._pending_load = True

        layout = QVBoxLayout(self)
        title = QLabel("Manifestação de NF-e")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)

        filter_layout = QHBoxLayout()
        self.empresa_combo = QComboBox()
        self.empresa_combo.currentIndexChanged.connect(self._combo_changed)
        filter_layout.addWidget(QLabel("Empresa:"))
        filter_layout.addWidget(self.empresa_combo)

        btn_carregar = QPushButton("🔄 Carregar")
        btn_carregar.clicked.connect(self.load_manifestacoes)
        filter_layout.addWidget(btn_carregar)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        btn_layout = QHBoxLayout()
        btn_manifestar = QPushButton("✋ Manifestar")
        btn_manifestar.clicked.connect(self.manifestar)
        btn_layout.addWidget(btn_manifestar)
        btn_reprocessar = QPushButton("🔁 Reprocessar")
        btn_reprocessar.clicked.connect(self.reprocessar)
        btn_layout.addWidget(btn_reprocessar)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Chave", "Status", "Tentativas", "Próxima Tentativa", "Último Retorno"])
        layout.addWidget(self.table)

        app_signals.company_selected.connect(self.set_selected_empresa)
        app_signals.companies_changed.connect(self.refresh_empresas)
        self.refresh_empresas()
        log.info("Página de manifestação inicializada")

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
        self._pending_load = True
        if self.isVisible():
            self.load_manifestacoes()
            self._pending_load = False

    def set_selected_empresa(self, empresa_id):
        idx = self.empresa_combo.findData(empresa_id)
        self.empresa_combo.blockSignals(True)
        if idx >= 0:
            self.empresa_combo.setCurrentIndex(idx)
        elif self.empresa_combo.count():
            self.empresa_combo.setCurrentIndex(0)
        self.empresa_combo.blockSignals(False)
        self._pending_load = True
        if self.isVisible():
            self.load_manifestacoes()
            self._pending_load = False

    def on_page_activated(self):
        self.refresh_empresas(self.empresa_combo.currentData())
        if self._pending_load:
            self.load_manifestacoes()
            self._pending_load = False

    def _combo_changed(self):
        app_signals.company_selected.emit(self.empresa_combo.currentData())
        self.load_manifestacoes()

    def load_manifestacoes(self):
        empresa_id = self.empresa_combo.currentData()
        if not empresa_id:
            self.table.setRowCount(0)
            return
        itens = self.session.query(FilaManifestacao).filter(FilaManifestacao.empresa_id == empresa_id).order_by(FilaManifestacao.criado_em.desc()).all()
        self.table.setRowCount(len(itens))
        for row, item in enumerate(itens):
            self.table.setItem(row, 0, QTableWidgetItem(item.chave or ""))
            self.table.setItem(row, 1, QTableWidgetItem(item.status or ""))
            self.table.setItem(row, 2, QTableWidgetItem(str(item.tentativas or 0)))
            self.table.setItem(row, 3, QTableWidgetItem(item.proxima_tentativa_em.strftime("%d/%m/%Y %H:%M") if item.proxima_tentativa_em else ""))
            self.table.setItem(row, 4, QTableWidgetItem(item.ultimo_retorno or ""))
        log.info("Manifestações carregadas")

    def manifestar(self):
        QMessageBox.information(self, "Manifestação", "O envio de manifestação ainda não foi implementado.")
        log.info("Manifestação não implementada ainda")

    def reprocessar(self):
        QMessageBox.information(self, "Manifestação", "O reprocessamento ainda não foi implementado.")
        log.info("Reprocessamento não implementado ainda")
