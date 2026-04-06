"""
Página de gerenciamento de empresas
"""
import requests
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QDialog, QLabel, QLineEdit, QComboBox, QFormLayout,
    QFileDialog, QMessageBox, QCheckBox, QScrollArea
)
from PySide6.QtCore import Qt
from app.utils.logger import log
from app.utils.cnpj_pdf_parser import CnpjPdfParser
from app.db import get_db_session, EmpresaRepository
from app.core import app_signals
from config.settings import TAX_REGIMES


class EmpresasPage(QWidget):
    """Página de gerenciamento de empresas"""

    def __init__(self):
        super().__init__()
        self.session = get_db_session()
        self.empresa_repo = EmpresaRepository(self.session)

        layout = QVBoxLayout(self)
        title = QLabel("Gerenciamento de Empresas")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)

        btn_layout = QHBoxLayout()
        btn_novo = QPushButton("➕ Nova Empresa")
        btn_novo.clicked.connect(self.open_new_empresa_dialog)
        btn_layout.addWidget(btn_novo)

        btn_editar = QPushButton("✏️ Editar")
        btn_editar.clicked.connect(self.edit_empresa)
        btn_layout.addWidget(btn_editar)

        btn_deletar = QPushButton("🗑️ Deletar")
        btn_deletar.clicked.connect(self.delete_empresa)
        btn_layout.addWidget(btn_deletar)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "ID", "CNPJ", "Razão Social", "Fantasia", "Município/UF", "Regime", "Situação", "Status"
        ])
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 260)
        self.table.setColumnWidth(3, 220)
        self.table.setColumnWidth(4, 180)
        self.table.setColumnWidth(5, 160)
        layout.addWidget(self.table)

        self.load_empresas()
        log.info("Página de empresas inicializada")

    def on_page_activated(self):
        self.load_empresas()

    def load_empresas(self):
        empresas = self.empresa_repo.list_all(ativo_only=False)
        self.table.setRowCount(len(empresas))
        for row, empresa in enumerate(empresas):
            self.table.setItem(row, 0, QTableWidgetItem(str(empresa.id)))
            self.table.setItem(row, 1, QTableWidgetItem(self._format_cnpj(empresa.cnpj)))
            self.table.setItem(row, 2, QTableWidgetItem(empresa.razao_social or ""))
            self.table.setItem(row, 3, QTableWidgetItem(empresa.nome_fantasia or ""))
            municipio_uf = f"{empresa.municipio or ''}/{empresa.uf or ''}".strip("/")
            self.table.setItem(row, 4, QTableWidgetItem(municipio_uf))
            self.table.setItem(row, 5, QTableWidgetItem(empresa.regime_tributario or ""))
            self.table.setItem(row, 6, QTableWidgetItem(empresa.situacao_cadastral or ""))
            self.table.setItem(row, 7, QTableWidgetItem("Ativa" if empresa.ativo else "Inativa"))

    @staticmethod
    def _format_cnpj(cnpj: str) -> str:
        cnpj = ''.join(ch for ch in (cnpj or '') if ch.isdigit())
        if len(cnpj) != 14:
            return cnpj
        return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"

    def open_new_empresa_dialog(self):
        dialog = EmpresaDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.load_empresas()
            log.info("Empresa adicionada com sucesso")

    def _get_selected_empresa(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        empresa_id_item = self.table.item(row, 0)
        if not empresa_id_item:
            return None
        return self.empresa_repo.get_by_id(int(empresa_id_item.text()))

    def edit_empresa(self):
        empresa = self._get_selected_empresa()
        if not empresa:
            QMessageBox.warning(self, "Empresas", "Selecione uma empresa para editar.")
            return
        dialog = EmpresaDialog(self, empresa)
        if dialog.exec() == QDialog.Accepted:
            self.load_empresas()
            log.info(f"Empresa {empresa.cnpj} atualizada")

    def delete_empresa(self):
        empresa = self._get_selected_empresa()
        if not empresa:
            QMessageBox.warning(self, "Empresas", "Selecione uma empresa para deletar.")
            return

        confirm = QMessageBox.question(
            self,
            "Confirmar exclusão",
            f"Deseja realmente excluir a empresa {empresa.razao_social}?",
        )
        if confirm != QMessageBox.Yes:
            return

        deleted = self.empresa_repo.delete(empresa.id)
        if deleted:
            self.load_empresas()
            app_signals.companies_changed.emit(None)
            log.info(f"Empresa {empresa.cnpj} deletada")


class EmpresaDialog(QDialog):
    """Diálogo para criar/editar empresa"""

    FIELD_SPECS = [
        ("Razão Social", "razao_social"),
        ("Nome Fantasia", "nome_fantasia"),
        ("CNPJ", "cnpj"),
        ("IE", "inscricao_estadual"),
        ("IM", "inscricao_municipal"),
        ("Matriz/Filial", "matriz_filial"),
        ("Data de Abertura", "data_abertura"),
        ("Porte", "porte"),
        ("Natureza Jurídica", "natureza_juridica"),
        ("Atividade Principal", "atividade_principal"),
        ("Atividades Secundárias", "atividades_secundarias"),
        ("Logradouro", "logradouro"),
        ("Número", "numero"),
        ("Complemento", "complemento"),
        ("CEP", "cep"),
        ("Bairro", "bairro"),
        ("Município", "municipio"),
        ("UF", "uf"),
        ("Email", "email"),
        ("Telefone", "telefone"),
        ("Situação Cadastral", "situacao_cadastral"),
        ("Data Situação Cadastral", "data_situacao_cadastral"),
        ("Motivo Situação Cadastral", "motivo_situacao_cadastral"),
        ("Situação Especial", "situacao_especial"),
        ("Data Situação Especial", "data_situacao_especial"),
        ("EFR", "efr"),
    ]

    def __init__(self, parent=None, empresa=None):
        super().__init__(parent)
        self.setWindowTitle("Empresa")
        self.setGeometry(180, 120, 760, 760)
        self.setMinimumSize(980, 720)
        self.setWindowState(self.windowState() | Qt.WindowMaximized)
        self.empresa = empresa
        self.session = get_db_session()
        self.empresa_repo = EmpresaRepository(self.session)
        self.inputs = {}
        self.init_ui()

    def init_ui(self):
        root_layout = QVBoxLayout(self)

        info_label = QLabel("Você pode cadastrar manualmente ou importar o PDF do comprovante do CNPJ.")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #555; margin-bottom: 8px;")
        root_layout.addWidget(info_label)

        import_layout = QHBoxLayout()
        self.btn_import_pdf = QPushButton("📄 Importar PDF do CNPJ")
        self.btn_import_pdf.clicked.connect(self.importar_pdf_cnpj)
        import_layout.addWidget(self.btn_import_pdf)
        self.btn_lookup_online = QPushButton("🌐 Consultar CNPJ online")
        self.btn_lookup_online.clicked.connect(self.consultar_cnpj_online)
        import_layout.addWidget(self.btn_lookup_online)
        import_layout.addStretch()
        root_layout.addLayout(import_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QFormLayout(container)

        for label, key in self.FIELD_SPECS:
            widget = QLineEdit()
            if key == "atividade_principal" or key == "atividades_secundarias" or key == "motivo_situacao_cadastral":
                widget.setMinimumHeight(52)
            self.inputs[key] = widget
            layout.addRow(f"{label}:", widget)

        self.regime = QComboBox()
        self.regime.addItems(TAX_REGIMES.values())
        layout.addRow("Regime:", self.regime)

        self.ativo = QCheckBox("Empresa ativa")
        self.ativo.setChecked(True)
        layout.addRow("Status:", self.ativo)

        scroll.setWidget(container)
        root_layout.addWidget(scroll, 1)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("Salvar")
        btn_ok.clicked.connect(self.save)
        btn_layout.addWidget(btn_ok)
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        btn_layout.addStretch()
        root_layout.addLayout(btn_layout)

        self.inputs["cnpj"].setPlaceholderText("Somente números ou formato 00.000.000/0000-00")
        self.inputs["uf"].setPlaceholderText("Ex.: SC")
        self.inputs["municipio"].setPlaceholderText("Ex.: Maravilha")

        if self.empresa:
            for _, key in self.FIELD_SPECS:
                self.inputs[key].setText(str(getattr(self.empresa, key) or ""))
            self.inputs["cnpj"].setReadOnly(True)
            self.ativo.setChecked(bool(self.empresa.ativo))
            if self.empresa.regime_tributario:
                idx = self.regime.findText(self.empresa.regime_tributario, Qt.MatchFixedString)
                if idx >= 0:
                    self.regime.setCurrentIndex(idx)

    def importar_pdf_cnpj(self):
        pdf_path, _ = QFileDialog.getOpenFileName(self, "Selecionar comprovante CNPJ", "", "Arquivos PDF (*.pdf)")
        if not pdf_path:
            return
        try:
            dados = CnpjPdfParser.parse(pdf_path)
        except Exception as exc:
            log.exception(f"Erro ao importar PDF de CNPJ: {exc}")
            QMessageBox.critical(self, "Importação de PDF", f"Não foi possível ler o PDF informado.\n\nDetalhes: {exc}")
            return
        if not dados.get("cnpj") or not dados.get("razao_social"):
            QMessageBox.warning(self, "Importação de PDF", "O PDF foi lido, mas não encontrei CNPJ e razão social.")
            return

        for _, key in self.FIELD_SPECS:
            if key == "cnpj" and self.empresa:
                continue
            self.inputs[key].setText(dados.get(key, ""))

        mensagem = (
            "Dados importados do PDF com sucesso.\n\n"
            f"CNPJ: {dados.get('cnpj_mascara') or dados.get('cnpj')}\n"
            f"Razão Social: {dados.get('razao_social', '')}\n"
            f"Fantasia: {dados.get('nome_fantasia', '') or 'Não informado'}\n"
            f"Município/UF: {dados.get('municipio', '')}/{dados.get('uf', '')}\n"
            f"Email: {dados.get('email', '') or 'Não informado'}"
        )
        QMessageBox.information(self, "Importação de PDF", mensagem)
        log.info(f"PDF de CNPJ importado: {pdf_path}")

    def _apply_online_company_data(self, dados: dict):
        mapping = {
            "razao_social": dados.get("razao_social") or "",
            "nome_fantasia": dados.get("nome_fantasia") or "",
            "cnpj": ''.join(ch for ch in str(dados.get("cnpj") or "") if ch.isdigit()),
            "inscricao_estadual": "",
            "inscricao_municipal": "",
            "matriz_filial": dados.get("descricao_identificador_matriz_filial") or dados.get("identificador_matriz_filial") or "",
            "data_abertura": dados.get("data_inicio_atividade") or dados.get("data_abertura") or "",
            "porte": dados.get("porte") or dados.get("porte_descricao") or "",
            "natureza_juridica": dados.get("natureza_juridica") or dados.get("descricao_natureza_juridica") or "",
            "atividade_principal": dados.get("cnae_fiscal_descricao") or dados.get("cnae_fiscal") or "",
            "atividades_secundarias": "; ".join([f"{item.get('codigo', '')} - {item.get('descricao', '')}".strip(' -') for item in (dados.get("cnaes_secundarios") or dados.get("cnaes_secundarias") or []) if isinstance(item, dict)]) if isinstance((dados.get("cnaes_secundarios") or dados.get("cnaes_secundarias") or []), list) else "",
            "logradouro": dados.get("logradouro") or "",
            "numero": dados.get("numero") or "",
            "complemento": dados.get("complemento") or "",
            "cep": dados.get("cep") or "",
            "bairro": dados.get("bairro") or "",
            "municipio": dados.get("municipio") or "",
            "uf": (dados.get("uf") or "").upper(),
            "email": dados.get("email") or "",
            "telefone": ''.join(filter(None, [str(dados.get("ddd_telefone_1") or ""), str(dados.get("telefone_1") or dados.get("ddd_telefone_2") or "")])).strip() or dados.get("telefone") or "",
            "situacao_cadastral": dados.get("descricao_situacao_cadastral") or dados.get("situacao_cadastral") or "",
            "data_situacao_cadastral": dados.get("data_situacao_cadastral") or "",
            "motivo_situacao_cadastral": dados.get("motivo_situacao_cadastral") or dados.get("descricao_motivo_situacao_cadastral") or "",
            "situacao_especial": dados.get("situacao_especial") or "",
            "data_situacao_especial": dados.get("data_situacao_especial") or "",
            "efr": dados.get("ente_federativo_responsavel") or dados.get("efr") or "",
        }
        for _, key in self.FIELD_SPECS:
            if key == "cnpj" and self.empresa:
                continue
            valor = mapping.get(key, "")
            if valor is None:
                valor = ""
            self.inputs[key].setText(str(valor))

    def consultar_cnpj_online(self):
        cnpj_informado = ''.join(ch for ch in self.inputs["cnpj"].text() if ch.isdigit())
        if len(cnpj_informado) != 14:
            QMessageBox.warning(self, "Consulta CNPJ", "Informe primeiro um CNPJ com 14 dígitos.")
            return
        try:
            resposta = requests.get(
                f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_informado}",
                timeout=20,
                headers={"Accept": "application/json", "User-Agent": "XMLDownloader/1.0"},
            )
            if resposta.status_code == 404:
                QMessageBox.warning(self, "Consulta CNPJ", "CNPJ não encontrado na consulta online.")
                return
            resposta.raise_for_status()
            dados = resposta.json() or {}
            self._apply_online_company_data(dados)
            QMessageBox.information(
                self,
                "Consulta CNPJ",
                "Dados carregados da consulta online. Revise as informações antes de salvar a empresa.",
            )
            log.info(f"Consulta online de CNPJ concluída: {cnpj_informado}")
        except Exception as exc:
            log.exception(f"Falha na consulta online do CNPJ {cnpj_informado}: {exc}")
            QMessageBox.warning(
                self,
                "Consulta CNPJ",
                "Não foi possível consultar o CNPJ online agora. Confira a internet e tente novamente.\n\n"
                f"Detalhes: {exc}",
            )

    def save(self):
        payload = {key: self.inputs[key].text().strip() for _, key in self.FIELD_SPECS}
        payload["cnpj"] = ''.join(ch for ch in payload["cnpj"] if ch.isdigit())
        payload["uf"] = payload["uf"].upper()
        payload["municipio"] = payload["municipio"].title()
        payload["email"] = payload["email"].lower()
        payload["regime_tributario"] = self.regime.currentText().strip()
        payload["ativo"] = self.ativo.isChecked()

        if not payload["razao_social"]:
            QMessageBox.warning(self, "Empresas", "Informe a razão social.")
            return
        if not self.empresa and len(payload["cnpj"]) != 14:
            QMessageBox.warning(self, "Empresas", "Informe um CNPJ válido com 14 dígitos.")
            return
        if not payload["uf"]:
            QMessageBox.warning(self, "Empresas", "Informe a UF da empresa.")
            return

        try:
            if self.empresa:
                empresa = self.empresa_repo.update(self.empresa.id, **payload)
            else:
                if self.empresa_repo.get_by_cnpj(payload["cnpj"]):
                    QMessageBox.warning(self, "Empresas", "Já existe uma empresa cadastrada com esse CNPJ.")
                    return
                empresa = self.empresa_repo.create(
                    razao_social=payload.pop("razao_social"),
                    cnpj=payload.pop("cnpj"),
                    uf=payload.pop("uf"),
                    **payload,
                )
            app_signals.companies_changed.emit(empresa.id if empresa else None)
            self.accept()
        except Exception as exc:
            log.exception(f"Erro ao salvar empresa: {exc}")
            QMessageBox.critical(self, "Empresas", f"Erro ao salvar empresa:\n{exc}")
