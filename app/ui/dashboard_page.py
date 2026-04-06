"""
Página de dashboard com estatísticas
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QGridLayout, QTableWidget, QTableWidgetItem, QFrame
)
from app.utils.logger import log
from app.db import get_db_session, EmpresaRepository, DocumentoRepository, DatabaseConnection
from app.db.models import Documento
from app.core import app_signals


class DashboardPage(QWidget):
    """Página de dashboard com estatísticas"""

    def __init__(self):
        super().__init__()
        self.session = get_db_session()
        self.empresa_repo = EmpresaRepository(self.session)
        self.doc_repo = DocumentoRepository(self.session)
        self.selected_empresa_id = None

        layout = QVBoxLayout(self)

        title = QLabel("Dashboard")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 4px;")
        layout.addWidget(title)

        subtitle = QLabel("Visão geral do banco, da empresa ativa e dos últimos documentos gravados.")
        subtitle.setStyleSheet("color: #64748b; margin-bottom: 8px;")
        layout.addWidget(subtitle)

        info_card = QFrame()
        info_card.setStyleSheet("background: #fff; border: 1px solid #e5e7eb; border-radius: 10px;")
        info_layout = QVBoxLayout(info_card)
        self.company_info = QLabel("Empresa ativa: todas")
        self.db_info = QLabel("")
        self.db_info.setWordWrap(True)
        info_layout.addWidget(self.company_info)
        info_layout.addWidget(self.db_info)
        layout.addWidget(info_card)

        cards_layout = QGridLayout()
        self.card_empresas, self.value_empresas = self.create_stat_card("Empresas", "0")
        self.card_documentos, self.value_documentos = self.create_stat_card("Documentos", "0")
        self.card_sucesso, self.value_sucesso = self.create_stat_card("Processados", "0%")
        self.card_erros, self.value_erros = self.create_stat_card("Erros", "0")
        cards_layout.addWidget(self.card_empresas, 0, 0)
        cards_layout.addWidget(self.card_documentos, 0, 1)
        cards_layout.addWidget(self.card_sucesso, 0, 2)
        cards_layout.addWidget(self.card_erros, 0, 3)
        layout.addLayout(cards_layout)

        label = QLabel("Últimos Documentos")
        label.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 16px;")
        layout.addWidget(label)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Chave", "Empresa", "Tipo", "Data", "Valor", "Status"])
        layout.addWidget(self.table)

        app_signals.company_selected.connect(self.set_selected_empresa)
        app_signals.companies_changed.connect(lambda empresa_id=None: self.load_stats())
        self.load_stats()
        log.info("Dashboard inicializado")

    def create_stat_card(self, title: str, value: str):
        card = QGroupBox()
        card.setStyleSheet("""
            QGroupBox {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 10px;
                background-color: #ffffff;
            }
        """)
        layout = QVBoxLayout(card)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 12px; color: #666;")
        value_label = QLabel(value)
        value_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #2196F3;")
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.setContentsMargins(10, 10, 10, 10)
        return card, value_label

    def set_selected_empresa(self, empresa_id):
        self.selected_empresa_id = empresa_id
        self.load_stats()

    def on_page_activated(self):
        self.load_stats()

    def load_stats(self):
        empresas = self.empresa_repo.list_all()
        self.value_empresas.setText(str(len(empresas)))

        ok, detail = DatabaseConnection.test_connection()
        db_text = f"Banco: {'conectado' if ok else 'erro'} | {detail}"
        self.db_info.setText(db_text)

        empresa = None
        documentos = []
        if self.selected_empresa_id:
            empresa = self.empresa_repo.get_by_id(self.selected_empresa_id)
            if empresa:
                documentos = self.doc_repo.list_by_empresa(empresa.id)
                self.company_info.setText(f"Empresa ativa: {empresa.razao_social} - {empresa.cnpj}")
            else:
                self.company_info.setText("Empresa ativa: não encontrada")
        else:
            self.company_info.setText("Empresa ativa: todas")
            for item in empresas:
                documentos.extend(self.doc_repo.list_by_empresa(item.id))

        self.value_documentos.setText(str(len(documentos)))
        erros = len([d for d in documentos if (d.status or "").startswith("ERRO") or d.status == "XML_INVALIDO"])
        processados = len([d for d in documentos if d.status == "XML_PROCESSADO"])
        taxa = (processados / len(documentos) * 100) if documentos else 0
        self.value_sucesso.setText(f"{taxa:.1f}%")
        self.value_erros.setText(str(erros))

        self.load_recent_documents()

    def load_recent_documents(self):
        query = self.session.query(Documento)
        if self.selected_empresa_id:
            query = query.filter(Documento.empresa_id == self.selected_empresa_id)
        documentos = query.order_by(Documento.criado_em.desc()).limit(20).all()

        self.table.setRowCount(len(documentos))
        for row, doc in enumerate(documentos):
            empresa_nome = doc.empresa.razao_social if getattr(doc, "empresa", None) else ""
            self.table.setItem(row, 0, QTableWidgetItem(doc.chave or ""))
            self.table.setItem(row, 1, QTableWidgetItem(empresa_nome))
            self.table.setItem(row, 2, QTableWidgetItem(doc.tipo_documento or ""))
            self.table.setItem(row, 3, QTableWidgetItem(doc.data_emissao.strftime("%d/%m/%Y") if doc.data_emissao else ""))
            self.table.setItem(row, 4, QTableWidgetItem(f"R$ {doc.valor_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")))
            self.table.setItem(row, 5, QTableWidgetItem(doc.status or ""))
