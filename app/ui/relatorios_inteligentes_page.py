"""Página de Relatórios Inteligentes - Análises profissionais automáticas."""
from __future__ import annotations

from datetime import datetime, date, time
from pathlib import Path
from decimal import Decimal

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QTableWidget,
    QTableWidgetItem, QPushButton, QMessageBox, QGroupBox, QFormLayout,
    QComboBox, QDateEdit, QProgressBar, QHeaderView, QFileDialog,
    QLineEdit, QDialog, QAbstractItemView
)
from PySide6.QtGui import QColor, QFont

from app.utils.logger import log
from app.db import get_db_session, EmpresaRepository, DocumentoRepository
from app.services.intelligent_reports import RelatoriosInteligentes
from app.services.excel_exporter import ExcelExporter
from app.utils.ui_state import get_settings, save_qdate, load_qdate
from config.settings import DOWNLOADS_DIR


class RelatóriosInteligentesPage(QWidget):
    """Página com 6 tipos de relatórios inteligentes"""

    def __init__(self):
        super().__init__()
        self.session = get_db_session()
        self.empresa_repo = EmpresaRepository(self.session)
        self.doc_repo = DocumentoRepository(self.session)
        self.settings = get_settings()
        self.relatorios = None
        self.dados_notas = []
        self._resultados_cliente = []
        self._resultados_servico = []
        self._resultados_cancelamentos = []

        layout = QVBoxLayout(self)

        # Título
        title = QLabel("📊 Relatórios Inteligentes")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Análises profissionais automáticas de suas notas fiscais. "
            "Selecione uma empresa e período para gerar os relatórios."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #64748b; margin-bottom: 10px;")
        layout.addWidget(subtitle)

        # Painel de filtros
        filter_group = QGroupBox("Filtros")
        filter_layout = QFormLayout(filter_group)

        self.empresa_combo = QComboBox()
        self.empresa_combo.currentIndexChanged.connect(self._on_empresa_changed)
        filter_layout.addRow("Empresa:", self.empresa_combo)

        self.data_inicial = QDateEdit()
        self.data_inicial.setDate(QDate.currentDate().addMonths(-1))
        self.data_inicial.setCalendarPopup(True)
        self.data_inicial.setDisplayFormat("dd/MM/yyyy")
        filter_layout.addRow("Data Inicial:", self.data_inicial)

        self.data_final = QDateEdit()
        self.data_final.setDate(QDate.currentDate())
        self.data_final.setCalendarPopup(True)
        self.data_final.setDisplayFormat("dd/MM/yyyy")
        filter_layout.addRow("Data Final:", self.data_final)

        layout.addWidget(filter_group)

        # Botões de ação
        btn_layout = QHBoxLayout()
        self.btn_gerar = QPushButton("🔄 Gerar Relatórios")
        self.btn_gerar.clicked.connect(self._gerar_relatorios)
        btn_layout.addWidget(self.btn_gerar)

        self.btn_exportar = QPushButton("📥 Exportar para Excel")
        self.btn_exportar.clicked.connect(self._exportar_excel)
        self.btn_exportar.setEnabled(False)
        btn_layout.addWidget(self.btn_exportar)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Pesquisa inteligente da aba atual
        search_layout = QHBoxLayout()
        search_label = QLabel("Pesquisa da aba atual:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Digite qualquer texto para pesquisar somente na aba aberta...")
        self.search_input.textChanged.connect(self._aplicar_pesquisa_aba_atual)
        self.btn_limpar_pesquisa = QPushButton("Limpar pesquisa")
        self.btn_limpar_pesquisa.clicked.connect(self._limpar_pesquisa)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input, 1)
        search_layout.addWidget(self.btn_limpar_pesquisa)
        layout.addLayout(search_layout)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # Abas de relatórios
        self.tabs = QTabWidget()

        self.tab_financeiro = self._criar_tab_financeiro()
        self.tab_clientes = self._criar_tab_clientes()
        self.tab_servicos = self._criar_tab_servicos()
        self.tab_impostos = self._criar_tab_impostos()
        self.tab_tendencias = self._criar_tab_tendencias()
        self.tab_cancelamentos = self._criar_tab_cancelamentos()

        self.tabs.addTab(self.tab_financeiro, "📈 Financeiro")
        self.tabs.addTab(self.tab_clientes, "👥 Clientes")
        self.tabs.addTab(self.tab_servicos, "🛠️ Serviços")
        self.tabs.addTab(self.tab_impostos, "💰 Impostos")
        self.tabs.addTab(self.tab_tendencias, "📊 Tendências")
        self.tabs.addTab(self.tab_cancelamentos, "⚠️ Cancelamentos")
        self.tabs.currentChanged.connect(lambda _idx: self._aplicar_pesquisa_aba_atual())

        layout.addWidget(self.tabs)

        # Status
        self.status_label = QLabel("Pronto para gerar relatórios")
        self.status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        layout.addWidget(self.status_label)

        self._carregar_empresas()
        log.info("Página de relatórios inteligentes inicializada")

    def _criar_tab_financeiro(self) -> QWidget:
        """Cria aba de relatório financeiro"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Resumo em cards
        cards_layout = QHBoxLayout()
        self.card_total_notas = self._criar_card("Total de Notas", "0")
        self.card_total_valor = self._criar_card("Valor Total", "R$ 0,00")
        self.card_valor_medio = self._criar_card("Valor Médio", "R$ 0,00")
        self.card_canceladas = self._criar_card("Canceladas", "0 (0%)")

        cards_layout.addWidget(self.card_total_notas)
        cards_layout.addWidget(self.card_total_valor)
        cards_layout.addWidget(self.card_valor_medio)
        cards_layout.addWidget(self.card_canceladas)
        layout.addLayout(cards_layout)

        # Tabela detalhada
        self.table_financeiro = QTableWidget()
        self.table_financeiro.setColumnCount(2)
        self.table_financeiro.setHorizontalHeaderLabels(["Métrica", "Valor"])
        self._configurar_tabela(self.table_financeiro)
        layout.addWidget(self.table_financeiro)

        return widget

    def _criar_tab_clientes(self) -> QWidget:
        """Cria aba de relatório de clientes"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.card_total_clientes = self._criar_card("Total de Clientes", "0")
        self.card_maior_valor = self._criar_card("Maior Valor", "R$ 0,00")

        cards_layout = QHBoxLayout()
        cards_layout.addWidget(self.card_total_clientes)
        cards_layout.addWidget(self.card_maior_valor)
        layout.addLayout(cards_layout)

        self.table_clientes = QTableWidget()
        self.table_clientes.setColumnCount(4)
        self.table_clientes.setHorizontalHeaderLabels(["Cliente", "Valor Total", "Qtd Notas", "Valor Médio"])
        self._configurar_tabela(self.table_clientes)
        self.table_clientes.cellClicked.connect(self._abrir_detalhe_cliente)
        layout.addWidget(self.table_clientes)

        return widget

    def _criar_tab_servicos(self) -> QWidget:
        """Cria aba de relatório de serviços"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.card_total_servicos = self._criar_card("Total de Serviços", "0")
        self.card_servico_top = self._criar_card("Mais Faturado", "R$ 0,00")

        cards_layout = QHBoxLayout()
        cards_layout.addWidget(self.card_total_servicos)
        cards_layout.addWidget(self.card_servico_top)
        layout.addLayout(cards_layout)

        self.table_servicos = QTableWidget()
        self.table_servicos.setColumnCount(3)
        self.table_servicos.setHorizontalHeaderLabels(["Serviço", "Valor Total", "Qtd Notas"])
        self._configurar_tabela(self.table_servicos)
        self.table_servicos.cellClicked.connect(self._abrir_detalhe_servico)
        layout.addWidget(self.table_servicos)

        return widget

    def _criar_tab_impostos(self) -> QWidget:
        """Cria aba de relatório de impostos"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.card_total_issqn = self._criar_card("Total ISSQN", "R$ 0,00")
        self.card_total_retencoes = self._criar_card("Total Retenções", "R$ 0,00")
        self.card_pct_retencoes = self._criar_card("% Retenções", "0%")

        cards_layout = QHBoxLayout()
        cards_layout.addWidget(self.card_total_issqn)
        cards_layout.addWidget(self.card_total_retencoes)
        cards_layout.addWidget(self.card_pct_retencoes)
        layout.addLayout(cards_layout)

        self.table_impostos = QTableWidget()
        self.table_impostos.setColumnCount(2)
        self.table_impostos.setHorizontalHeaderLabels(["Imposto", "Valor"])
        self._configurar_tabela(self.table_impostos)
        layout.addWidget(self.table_impostos)

        return widget

    def _criar_tab_tendencias(self) -> QWidget:
        """Cria aba de relatório de tendências"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.card_media_diaria = self._criar_card("Média Diária", "R$ 0,00")
        self.card_pico = self._criar_card("Pico de Faturamento", "R$ 0,00")
        self.card_vale = self._criar_card("Vale de Faturamento", "R$ 0,00")

        cards_layout = QHBoxLayout()
        cards_layout.addWidget(self.card_media_diaria)
        cards_layout.addWidget(self.card_pico)
        cards_layout.addWidget(self.card_vale)
        layout.addLayout(cards_layout)

        self.table_tendencias = QTableWidget()
        self.table_tendencias.setColumnCount(2)
        self.table_tendencias.setHorizontalHeaderLabels(["Data", "Valor"])
        self._configurar_tabela(self.table_tendencias)
        layout.addWidget(self.table_tendencias)

        return widget

    def _criar_tab_cancelamentos(self) -> QWidget:
        """Cria aba de relatório de cancelamentos"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.card_total_validas = self._criar_card("Notas Válidas", "0")
        self.card_total_canceladas = self._criar_card("Notas Canceladas", "0")
        self.card_taxa_cancelamento = self._criar_card("Taxa de Cancelamento", "0%")

        cards_layout = QHBoxLayout()
        cards_layout.addWidget(self.card_total_validas)
        cards_layout.addWidget(self.card_total_canceladas)
        cards_layout.addWidget(self.card_taxa_cancelamento)
        layout.addLayout(cards_layout)

        info = QLabel("Clique em uma nota cancelada para ver os detalhes do documento.")
        info.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(info)

        self.table_cancelamentos = QTableWidget()
        self.table_cancelamentos.setColumnCount(6)
        self.table_cancelamentos.setHorizontalHeaderLabels(["Número", "Data", "Cliente", "Serviço", "Valor", "Chave"])
        self._configurar_tabela(self.table_cancelamentos)
        self.table_cancelamentos.cellClicked.connect(self._abrir_detalhe_cancelamento)
        layout.addWidget(self.table_cancelamentos)

        return widget

    def _criar_card(self, titulo: str, valor: str) -> QWidget:
        """Cria um card de informação"""
        card = QWidget()
        card.setStyleSheet("background: white; border: 1px solid #e5e7eb; border-radius: 10px; padding: 15px;")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        title_label = QLabel(titulo)
        title_label.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 600;")

        value_label = QLabel(valor)
        value_label.setStyleSheet("font-size: 16px; font-weight: 700; color: #0f172a;")
        value_label.setObjectName(f"card_value_{titulo.lower().replace(' ', '_')}")

        layout.addWidget(title_label)
        layout.addWidget(value_label)

        return card

    def _configurar_tabela(self, table: QTableWidget):
        """Aplica configuração visual padrão às tabelas."""
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)

    def _format_currency(self, valor) -> str:
        try:
            numero = float(valor or 0)
        except Exception:
            numero = 0.0
        texto = f"{numero:,.2f}"
        texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {texto}"

    def _format_data(self, data_valor) -> str:
        if not data_valor:
            return ""
        if isinstance(data_valor, datetime):
            return data_valor.strftime("%d/%m/%Y")
        if isinstance(data_valor, date):
            return data_valor.strftime("%d/%m/%Y")
        return str(data_valor)

    def _texto_cliente(self, nota) -> str:
        return (
            nota.get("tomador_razao_social")
            or nota.get("destinatario_nome")
            or nota.get("emitente_nome")
            or "Desconhecido"
        )

    def _texto_servico(self, nota) -> str:
        # Priorizar descrição real do serviço
        descricao = (
            nota.get("descricao_servico")
            or nota.get("servico_descricao")
        )
        if descricao and str(descricao).strip() and str(descricao) not in ("NFS-e Prestada", "NFS-e Tomada"):
            return descricao
        # Se não houver descrição, usar tipo de documento
        tipo = nota.get("tipo_documento")
        if tipo and str(tipo).strip():
            return tipo
        return "Serviço Genérico"

    def _nota_cancelada(self, nota) -> bool:
        status = str(nota.get("status") or nota.get("situacao") or "").upper()
        return "CANCEL" in status or bool(nota.get("status_cancelada"))

    def _obter_tabela_aba_atual(self):
        aba_atual = self.tabs.currentWidget()
        mapa = {
            self.tab_financeiro: self.table_financeiro,
            self.tab_clientes: self.table_clientes,
            self.tab_servicos: self.table_servicos,
            self.tab_impostos: self.table_impostos,
            self.tab_tendencias: self.table_tendencias,
            self.tab_cancelamentos: self.table_cancelamentos,
        }
        return mapa.get(aba_atual)

    def _aplicar_pesquisa_aba_atual(self, *_args):
        table = self._obter_tabela_aba_atual()
        if table is None:
            return
        termo = (self.search_input.text() or "").strip().lower()
        for row in range(table.rowCount()):
            mostrar = not termo
            if termo:
                for col in range(table.columnCount()):
                    item = table.item(row, col)
                    if item and termo in (item.text() or "").lower():
                        mostrar = True
                        break
            table.setRowHidden(row, not mostrar)
        if termo:
            self.status_label.setText(f"🔎 Pesquisa aplicada na aba atual: {self.search_input.text()}")
            self.status_label.setStyleSheet("color: #2563eb; font-weight: bold;")
        elif self.relatorios:
            self.status_label.setText("✅ Relatórios gerados com sucesso!")
            self.status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        else:
            self.status_label.setText("Pronto para gerar relatórios")
            self.status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")

    def _limpar_pesquisa(self):
        self.search_input.clear()
        self._aplicar_pesquisa_aba_atual()

    def _mostrar_dialogo_notas(self, titulo: str, notas: list[dict], subtitulo: str | None = None):
        dialog = QDialog(self)
        dialog.setWindowTitle(titulo)
        dialog.resize(1100, 520)

        layout = QVBoxLayout(dialog)
        if subtitulo:
            label = QLabel(subtitulo)
            label.setWordWrap(True)
            label.setStyleSheet("color: #64748b; font-size: 12px;")
            layout.addWidget(label)

        resumo = QLabel(f"Total de notas: {len(notas)} | Valor total: {self._format_currency(sum(float(n.get('valor_total') or 0) for n in notas))}")
        resumo.setStyleSheet("font-weight: 600; color: #0f172a;")
        layout.addWidget(resumo)

        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels(["Número", "Data", "Cliente", "Serviço", "Valor", "Status", "Chave"])
        self._configurar_tabela(table)
        table.setRowCount(len(notas))

        for idx, nota in enumerate(notas):
            valores = [
                str(nota.get("numero") or ""),
                self._format_data(nota.get("data_emissao")),
                self._texto_cliente(nota),
                self._texto_servico(nota),
                self._format_currency(nota.get("valor_total")),
                str(nota.get("status") or nota.get("situacao") or ""),
                str(nota.get("chave") or ""),
            ]
            for col, valor in enumerate(valores):
                table.setItem(idx, col, QTableWidgetItem(valor))

        layout.addWidget(table)
        dialog.exec()

    def _abrir_detalhe_cliente(self, row: int, _column: int):
        if row < 0 or row >= len(self._resultados_cliente):
            return
        cliente = self._resultados_cliente[row]
        nome = cliente.get("cliente")
        notas = [nota for nota in self.dados_notas if self._texto_cliente(nota) == nome]
        self._mostrar_dialogo_notas(
            f"Notas do cliente: {nome}",
            notas,
            "Lista das notas que compõem o total do cliente selecionado.",
        )

    def _abrir_detalhe_servico(self, row: int, _column: int):
        if row < 0 or row >= len(self._resultados_servico):
            return
        servico = self._resultados_servico[row]
        nome = servico.get("servico")
        notas = [nota for nota in self.dados_notas if self._texto_servico(nota) == nome]
        self._mostrar_dialogo_notas(
            f"Notas do serviço: {nome}",
            notas,
            "Lista completa das notas vinculadas ao serviço selecionado.",
        )

    def _abrir_detalhe_cancelamento(self, row: int, _column: int):
        if row < 0 or row >= len(self._resultados_cancelamentos):
            return
        nota = self._resultados_cancelamentos[row]
        identificador = nota.get("numero") or nota.get("chave") or "Documento cancelado"
        self._mostrar_dialogo_notas(
            f"Detalhes do cancelamento: {identificador}",
            [nota],
            "Documento cancelado encontrado dentro do período selecionado.",
        )

    def _carregar_empresas(self):
        """Carrega lista de empresas"""
        self.empresa_combo.clear()
        try:
            empresas = self.empresa_repo.get_all()
            for empresa in empresas:
                self.empresa_combo.addItem(f"{empresa.razao_social} - {empresa.cnpj}", empresa.id)
        except Exception as exc:
            log.error(f"Erro ao carregar empresas: {exc}")

    def _on_empresa_changed(self):
        """Callback quando empresa muda"""
        self._save_state()

    def _save_state(self):
        """Salva estado dos filtros"""
        self.settings.setValue("relatorios/empresa", self.empresa_combo.currentData() or "")
        save_qdate(self.settings, "relatorios/data_inicial", self.data_inicial.date())
        save_qdate(self.settings, "relatorios/data_final", self.data_final.date())

    def _as_report_item(self, documento):
        """Normaliza Documento em estrutura compatível com os relatórios inteligentes."""
        class _ReportItem(dict):
            def __getattr__(self, item):
                try:
                    return self[item]
                except KeyError as exc:
                    raise AttributeError(item) from exc

            __setattr__ = dict.__setitem__
            __delattr__ = dict.__delitem__

        tipo_documento = (getattr(documento, "tipo_documento", "") or "").strip()
        situacao = (getattr(documento, "situacao", "") or "").strip()
        status_base = (getattr(documento, "status", "") or "").strip() or situacao or "VALIDO"
        status_upper = status_base.upper()
        situacao_upper = situacao.upper()
        cancelada = "CANCEL" in status_upper or "CANCEL" in situacao_upper
        valor_total = float(getattr(documento, "valor_total", 0) or 0)

        cliente = getattr(documento, "destinatario_nome", None) or getattr(documento, "emitente_nome", None) or "Desconhecido"
        if "TOMADA" in tipo_documento.upper() or "ENTRADA" in tipo_documento.upper():
            cliente = getattr(documento, "emitente_nome", None) or getattr(documento, "destinatario_nome", None) or "Desconhecido"

        servico_descricao = tipo_documento or getattr(documento, "schema", None) or getattr(documento, "modelo", None) or "Documento fiscal"
        data_emissao = getattr(documento, "data_emissao", None)
        if isinstance(data_emissao, date) and not hasattr(data_emissao, 'hour'):
            data_emissao = datetime.combine(data_emissao, time.min)

        return _ReportItem(
            id=getattr(documento, "id", None),
            empresa_id=getattr(documento, "empresa_id", None),
            tipo_documento=tipo_documento,
            chave=getattr(documento, "chave", None),
            numero=getattr(documento, "numero", None),
            serie=getattr(documento, "serie", None),
            modelo=getattr(documento, "modelo", None),
            data_emissao=data_emissao,
            emitente_cnpj=getattr(documento, "emitente_cnpj", None),
            emitente_nome=getattr(documento, "emitente_nome", None),
            destinatario_cnpj=getattr(documento, "destinatario_cnpj", None),
            destinatario_nome=getattr(documento, "destinatario_nome", None),
            valor_total=valor_total,
            valor_servico=valor_total,
            situacao=situacao or status_base,
            status="CANCELADA" if cancelada else (situacao or status_base or "VALIDO"),
            status_cancelada=cancelada,
            tomador_razao_social=cliente,
            descricao_servico=servico_descricao,
            servico_descricao=servico_descricao,
            valor_issqn=0.0,
            valor_ir=0.0,
            valor_pis=0.0,
            valor_cofins=0.0,
            valor_csll=0.0,
            issqn_valor=0.0,
            irrf_valor=0.0,
            pis_valor=0.0,
            cofins_valor=0.0,
            csll_valor=0.0,
            origem_captura=getattr(documento, "origem_captura", None),
            schema=getattr(documento, "schema", None),
            arquivo_xml=getattr(documento, "arquivo_xml", None),
        )

    def _carregar_dados_relatorios(self, empresa_id, data_ini, data_fim):
        """Carrega dados de relatório com fallback para instalações antigas."""
        metodo_periodo = getattr(self.doc_repo, "get_by_empresa_and_period", None)
        if callable(metodo_periodo):
            return metodo_periodo(empresa_id, data_ini, data_fim)

        log.warning(
            "DocumentoRepository sem get_by_empresa_and_period; usando fallback compatível na tela de relatórios inteligentes."
        )
        documentos = self.doc_repo.list_by_empresa(empresa_id)
        itens = []
        for documento in documentos:
            data_emissao = getattr(documento, "data_emissao", None)
            if isinstance(data_emissao, datetime):
                data_base = data_emissao.date()
            else:
                data_base = data_emissao
            if data_ini and data_base and data_base < data_ini:
                continue
            if data_fim and data_base and data_base > data_fim:
                continue
            itens.append(self._as_report_item(documento))
        itens.sort(key=lambda item: ((item.get('data_emissao') or datetime.min), item.get('id') or 0))
        return itens

    def _gerar_relatorios(self):
        """Gera todos os relatórios"""
        if not self.empresa_combo.currentData():
            QMessageBox.warning(self, "Validação", "Selecione uma empresa")
            return

        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.btn_gerar.setEnabled(False)
        self.status_label.setText("Gerando relatórios...")
        self.status_label.setStyleSheet("color: #2563eb;")

        try:
            empresa_id = self.empresa_combo.currentData()
            data_ini = self.data_inicial.date().toPython()
            data_fim = self.data_final.date().toPython()

            # Carregar dados
            self.dados_notas = self._carregar_dados_relatorios(empresa_id, data_ini, data_fim)
            self.progress.setValue(20)

            # Gerar relatórios
            self.relatorios = RelatoriosInteligentes(self.dados_notas)

            rel_fin = self.relatorios.gerar_relatorio_financeiro()
            self.progress.setValue(40)
            self._atualizar_tab_financeiro(rel_fin)

            rel_cli = self.relatorios.gerar_relatorio_clientes()
            self.progress.setValue(60)
            self._atualizar_tab_clientes(rel_cli)

            rel_srv = self.relatorios.gerar_relatorio_servicos()
            self.progress.setValue(70)
            self._atualizar_tab_servicos(rel_srv)

            rel_imp = self.relatorios.gerar_relatorio_impostos()
            self.progress.setValue(80)
            self._atualizar_tab_impostos(rel_imp)

            rel_ten = self.relatorios.gerar_relatorio_tendencias()
            self.progress.setValue(90)
            self._atualizar_tab_tendencias(rel_ten)

            rel_can = self.relatorios.gerar_relatorio_atrasos()
            self.progress.setValue(100)
            self._atualizar_tab_cancelamentos(rel_can)

            self.btn_exportar.setEnabled(True)
            self.status_label.setText("✅ Relatórios gerados com sucesso!")
            self.status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
            self._aplicar_pesquisa_aba_atual()

        except Exception as exc:
            log.exception(f"Erro ao gerar relatórios: {exc}")
            self.status_label.setText(f"❌ Erro: {exc}")
            self.status_label.setStyleSheet("color: #b91c1c;")
            QMessageBox.critical(self, "Erro", f"Erro ao gerar relatórios: {exc}")

        finally:
            self.progress.setVisible(False)
            self.btn_gerar.setEnabled(True)

    def _atualizar_tab_financeiro(self, rel):
        """Atualiza aba financeira"""
        self.card_total_notas.findChild(QLabel, "card_value_total_de_notas").setText(str(rel.total_notas))
        self.card_total_valor.findChild(QLabel, "card_value_valor_total").setText(f"R$ {rel.total_valor:,.2f}".replace(",", "."))
        self.card_valor_medio.findChild(QLabel, "card_value_valor_médio").setText(f"R$ {rel.valor_medio:,.2f}".replace(",", "."))
        self.card_canceladas.findChild(QLabel, "card_value_canceladas").setText(f"{rel.notas_canceladas} ({rel.percentual_canceladas:.1f}%)")

        self.table_financeiro.setRowCount(6)
        rows = [
            ("Total de Notas", str(rel.total_notas)),
            ("Valor Total", f"R$ {rel.total_valor:,.2f}"),
            ("Valor Médio", f"R$ {rel.valor_medio:,.2f}"),
            ("Valor Mínimo", f"R$ {rel.valor_minimo:,.2f}"),
            ("Valor Máximo", f"R$ {rel.valor_maximo:,.2f}"),
            ("Taxa de Cancelamento", f"{rel.percentual_canceladas:.1f}%"),
        ]
        for idx, (metrica, valor) in enumerate(rows):
            self.table_financeiro.setItem(idx, 0, QTableWidgetItem(metrica))
            self.table_financeiro.setItem(idx, 1, QTableWidgetItem(valor))

    def _atualizar_tab_clientes(self, rel):
        """Atualiza aba de clientes"""
        self.card_total_clientes.findChild(QLabel, "card_value_total_de_clientes").setText(str(rel.total_clientes_unicos))
        if rel.cliente_maior_valor:
            self.card_maior_valor.findChild(QLabel, "card_value_maior_valor").setText(f"R$ {rel.cliente_maior_valor['valor_total']:,.2f}")

        self._resultados_cliente = list(rel.top_clientes)
        self.table_clientes.setRowCount(len(rel.top_clientes))
        for idx, cliente in enumerate(rel.top_clientes):
            self.table_clientes.setItem(idx, 0, QTableWidgetItem(cliente['cliente']))
            self.table_clientes.setItem(idx, 1, QTableWidgetItem(f"R$ {cliente['valor_total']:,.2f}"))
            self.table_clientes.setItem(idx, 2, QTableWidgetItem(str(cliente['quantidade_notas'])))
            self.table_clientes.setItem(idx, 3, QTableWidgetItem(f"R$ {cliente['valor_medio']:,.2f}"))

    def _atualizar_tab_servicos(self, rel):
        """Atualiza aba de serviços"""
        self.card_total_servicos.findChild(QLabel, "card_value_total_de_serviços").setText(str(rel.total_servicos_unicos))
        if rel.servico_mais_faturado:
            self.card_servico_top.findChild(QLabel, "card_value_mais_faturado").setText(f"R$ {rel.servico_mais_faturado['valor_total']:,.2f}")

        self._resultados_servico = list(rel.top_servicos)
        self.table_servicos.setRowCount(len(rel.top_servicos))
        for idx, servico in enumerate(rel.top_servicos):
            self.table_servicos.setItem(idx, 0, QTableWidgetItem(servico['servico']))
            self.table_servicos.setItem(idx, 1, QTableWidgetItem(f"R$ {servico['valor_total']:,.2f}"))
            self.table_servicos.setItem(idx, 2, QTableWidgetItem(str(servico['quantidade_notas'])))

    def _atualizar_tab_impostos(self, rel):
        """Atualiza aba de impostos"""
        self.card_total_issqn.findChild(QLabel, "card_value_total_issqn").setText(f"R$ {rel.total_issqn:,.2f}")
        self.card_total_retencoes.findChild(QLabel, "card_value_total_retenções").setText(f"R$ {rel.total_retencoes:,.2f}")
        self.card_pct_retencoes.findChild(QLabel, "card_value_%_retenções").setText(f"{rel.percentual_retencoes:.1f}%")

        self.table_impostos.setRowCount(5)
        rows = [
            ("ISSQN", f"R$ {rel.total_issqn:,.2f}"),
            ("IRRF", f"R$ {rel.total_irrf:,.2f}"),
            ("PIS", f"R$ {rel.total_pis:,.2f}"),
            ("COFINS", f"R$ {rel.total_cofins:,.2f}"),
            ("CSLL", f"R$ {rel.total_csll:,.2f}"),
        ]
        for idx, (imposto, valor) in enumerate(rows):
            self.table_impostos.setItem(idx, 0, QTableWidgetItem(imposto))
            self.table_impostos.setItem(idx, 1, QTableWidgetItem(valor))

    def _atualizar_tab_tendencias(self, rel):
        """Atualiza aba de tendências"""
        self.card_media_diaria.findChild(QLabel, "card_value_média_diária").setText(f"R$ {rel.media_diaria:,.2f}")
        if rel.pico_faturamento:
            self.card_pico.findChild(QLabel, "card_value_pico_de_faturamento").setText(f"R$ {rel.pico_faturamento['valor']:,.2f}")
        if rel.vale_faturamento:
            self.card_vale.findChild(QLabel, "card_value_vale_de_faturamento").setText(f"R$ {rel.vale_faturamento['valor']:,.2f}")

        self.table_tendencias.setRowCount(len(rel.periodos))
        for idx, periodo in enumerate(rel.periodos):
            self.table_tendencias.setItem(idx, 0, QTableWidgetItem(periodo['data']))
            self.table_tendencias.setItem(idx, 1, QTableWidgetItem(f"R$ {periodo['valor']:,.2f}"))

    def _atualizar_tab_cancelamentos(self, rel):
        """Atualiza aba de cancelamentos"""
        self.card_total_validas.findChild(QLabel, "card_value_notas_válidas").setText(str(rel.total_validas))
        self.card_total_canceladas.findChild(QLabel, "card_value_notas_canceladas").setText(str(rel.total_canceladas))
        self.card_taxa_cancelamento.findChild(QLabel, "card_value_taxa_de_cancelamento").setText(f"{rel.taxa_cancelamento:.1f}%")

        self._resultados_cancelamentos = [nota for nota in self.dados_notas if self._nota_cancelada(nota)]
        self.table_cancelamentos.setRowCount(len(self._resultados_cancelamentos))
        for idx, nota in enumerate(self._resultados_cancelamentos):
            self.table_cancelamentos.setItem(idx, 0, QTableWidgetItem(str(nota.get('numero') or '')))
            self.table_cancelamentos.setItem(idx, 1, QTableWidgetItem(self._format_data(nota.get('data_emissao'))))
            self.table_cancelamentos.setItem(idx, 2, QTableWidgetItem(self._texto_cliente(nota)))
            self.table_cancelamentos.setItem(idx, 3, QTableWidgetItem(self._texto_servico(nota)))
            self.table_cancelamentos.setItem(idx, 4, QTableWidgetItem(self._format_currency(nota.get('valor_total'))))
            self.table_cancelamentos.setItem(idx, 5, QTableWidgetItem(str(nota.get('chave') or '')))

    def _exportar_excel(self):
        """Exporta relatórios para Excel"""
        if not self.relatorios:
            QMessageBox.warning(self, "Validação", "Gere os relatórios primeiro")
            return

        try:
            empresa_nome = self.empresa_combo.currentText()
            caminho_padrao = Path(DOWNLOADS_DIR) / f"Relatorio_{empresa_nome}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

            caminho, _ = QFileDialog.getSaveFileName(
                self,
                "Salvar Relatório",
                str(caminho_padrao),
                "Excel Files (*.xlsx)"
            )

            if not caminho:
                return

            # Criar exportador
            exporter = ExcelExporter(f"Relatório {empresa_nome}")

            # Adicionar dados dos relatórios (simplificado)
            # Em produção, seria necessário implementar os métodos específicos

            if exporter.salvar(caminho):
                QMessageBox.information(self, "Sucesso", f"Relatório salvo em:\n{caminho}")
                log.info(f"Relatório exportado: {caminho}")
            else:
                QMessageBox.critical(self, "Erro", "Erro ao salvar relatório")

        except Exception as exc:
            log.exception(f"Erro ao exportar: {exc}")
            QMessageBox.critical(self, "Erro", f"Erro ao exportar: {exc}")
