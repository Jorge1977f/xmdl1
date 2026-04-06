"""Página de visualização de XMLs."""
from __future__ import annotations

from pathlib import Path
from datetime import datetime
import shutil
import zipfile


from PySide6.QtCore import QUrl, QDate, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QLineEdit, QMessageBox,
    QFileDialog, QDateEdit
)

from app.utils.logger import log
from app.db import get_db_session, EmpresaRepository, DocumentoRepository, CredencialRepository
from app.core import app_signals
from app.services.xml_pdf_service import XMLPDFService
from app.services.xml_import_service import XMLImportService, ImportSummary
from config.settings import DOWNLOADS_DIR, XML_DIR


def brl(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class XMLsPage(QWidget):
    """Página de visualização de XMLs"""

    def __init__(self):
        super().__init__()
        self.session = get_db_session()
        self.empresa_repo = EmpresaRepository(self.session)
        self.doc_repo = DocumentoRepository(self.session)
        self.cred_repo = CredencialRepository(self.session)
        self.import_service = XMLImportService(self.session)
        self.current_documents = []
        self.selected_empresa_id = None
        self.selected_empresa_text = "Nenhuma empresa selecionada"
        self._pending_search = True

        layout = QVBoxLayout(self)
        title = QLabel("Visualizar XMLs")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 4px;")
        layout.addWidget(title)

        self.empresa_combo = QComboBox()
        self.empresa_combo.setMinimumWidth(380)
        self.empresa_combo.currentIndexChanged.connect(self._combo_changed)
        self.empresa_combo.hide()

        self.empresa_label = QLabel(self.selected_empresa_text)
        self.empresa_label.hide()

        filter_layout = QHBoxLayout()

        self.data_inicio = QDateEdit()
        self.data_inicio.setCalendarPopup(True)
        self.data_inicio.setDate(QDate.currentDate().addMonths(-1))
        self.data_inicio.dateChanged.connect(self.search)
        filter_layout.addWidget(QLabel("De:"))
        filter_layout.addWidget(self.data_inicio)

        self.data_fim = QDateEdit()
        self.data_fim.setCalendarPopup(True)
        self.data_fim.setDate(QDate.currentDate())
        self.data_fim.dateChanged.connect(self.search)
        filter_layout.addWidget(QLabel("Até:"))
        filter_layout.addWidget(self.data_fim)

        self.situacao_combo = QComboBox()
        self.situacao_combo.setMinimumWidth(170)
        self.situacao_combo.addItems(["Todas", "Somente válidas", "Somente canceladas"])
        self.situacao_combo.currentIndexChanged.connect(self.search)
        filter_layout.addWidget(QLabel("Situação:"))
        filter_layout.addWidget(self.situacao_combo)

        self.tipo_combo = QComboBox()
        self.tipo_combo.setMinimumWidth(190)
        self.tipo_combo.addItems(["Todos", "NFS-e Tomada", "NFS-e Prestada"])
        self.tipo_combo.currentIndexChanged.connect(self.search)
        filter_layout.addWidget(QLabel("Tipo:"))
        filter_layout.addWidget(self.tipo_combo)

        self.status_combo = QComboBox()
        self.status_combo.setMinimumWidth(170)
        self.status_combo.addItems(["Todos", "LOCAL_XML_VALIDO", "XML_PROCESSADO", "XML_INVALIDO", "NAO_LOCALIZADO", "CONCLUIDO"])
        self.status_combo.currentIndexChanged.connect(self.search)
        filter_layout.addWidget(QLabel("Status:"))
        filter_layout.addWidget(self.status_combo)

        self.search_input = QLineEdit()
        self.search_input.setMinimumWidth(340)
        self.search_input.setPlaceholderText("Buscar por chave, número, emitente, destinatário, CPF/CNPJ...")
        self.search_input.textChanged.connect(self.search)
        filter_layout.addWidget(self.search_input, 2)

        btn_buscar = QPushButton("🔍 Buscar")
        btn_buscar.clicked.connect(self.search)
        filter_layout.addWidget(btn_buscar)

        btn_refresh = QPushButton("↻ Atualizar Lista")
        btn_refresh.clicked.connect(self.search)
        filter_layout.addWidget(btn_refresh)

        btn_sync = QPushButton("🔄 Sincronizar Pasta")
        btn_sync.clicked.connect(self.sync_and_search)
        filter_layout.addWidget(btn_sync)
        
        btn_importar = QPushButton("📥 Importar XMLs")
        btn_importar.clicked.connect(self.import_manual_xmls)
        filter_layout.addWidget(btn_importar)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        btn_layout = QHBoxLayout()
        btn_abrir = QPushButton("📂 Abrir Pasta")
        btn_abrir.clicked.connect(self.open_folder)
        btn_layout.addWidget(btn_abrir)

        btn_visualizar = QPushButton("👁️ Visualizar XML/PDF")
        btn_visualizar.clicked.connect(self.view_xml)
        btn_layout.addWidget(btn_visualizar)

        btn_excluir = QPushButton("🗑️ Excluir XML")
        btn_excluir.clicked.connect(self.delete_selected_xmls)
        btn_layout.addWidget(btn_excluir)

        btn_exportar = QPushButton("📦 Exportar período (ZIP)")
        btn_exportar.clicked.connect(self.export_period_zip)
        btn_layout.addWidget(btn_exportar)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        from PySide6.QtWidgets import QAbstractItemView
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(["Chave", "Número", "Data", "Emitente/Destinatário", "Valor", "Situação", "Status", "Origem"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.cellClicked.connect(self._sync_row_selection)
        self.table.cellDoubleClicked.connect(self._open_row_document)
        layout.addWidget(self.table)

        app_signals.company_selected.connect(self.set_selected_empresa)
        app_signals.companies_changed.connect(self.refresh_empresas)
        self.refresh_empresas()
        log.info("Página de XMLs inicializada")

    def refresh_empresas(self, select_company_id=None):
        empresas = self.empresa_repo.list_all()
        current_id = select_company_id if select_company_id is not None else self.selected_empresa_id
        self.empresa_combo.blockSignals(True)
        self.empresa_combo.clear()
        self.empresa_combo.addItem("Selecione uma empresa", None)
        for empresa in empresas:
            self.empresa_combo.addItem(f"{empresa.razao_social} - {empresa.cnpj}", empresa.id)
        idx = self.empresa_combo.findData(current_id)
        if idx >= 0:
            self.empresa_combo.setCurrentIndex(idx)
            self.selected_empresa_id = current_id
        else:
            fallback_index = 1 if empresas else 0
            self.empresa_combo.setCurrentIndex(fallback_index)
            self.selected_empresa_id = self.empresa_combo.currentData()
        self.empresa_combo.blockSignals(False)
        self._refresh_company_label()

    def _refresh_company_label(self):
        empresa_id = self.selected_empresa_id or self.empresa_combo.currentData()
        empresa = self.empresa_repo.get_by_id(empresa_id) if empresa_id else None
        if empresa:
            self.selected_empresa_id = empresa.id
            self.selected_empresa_text = f"{empresa.razao_social} - {empresa.cnpj}"
        else:
            self.selected_empresa_text = "Nenhuma empresa selecionada"
        self._pending_search = True
        self.empresa_label.setText(self.selected_empresa_text)

    def set_selected_empresa(self, empresa_id):
        idx = self.empresa_combo.findData(empresa_id)
        self.empresa_combo.blockSignals(True)
        if idx >= 0:
            self.empresa_combo.setCurrentIndex(idx)
            self.selected_empresa_id = empresa_id
        elif self.empresa_combo.count():
            self.empresa_combo.setCurrentIndex(0)
            self.selected_empresa_id = self.empresa_combo.currentData()
        self.empresa_combo.blockSignals(False)
        self._refresh_company_label()
        self._pending_search = True
        if self.isVisible():
            self.search()
            self._pending_search = False

    def on_page_activated(self):
        self.refresh_empresas(self.selected_empresa_id or self.empresa_combo.currentData())
        if self._pending_search or not self.current_documents:
            self.search()
            self._pending_search = False

    def _combo_changed(self, *_args):
        self.selected_empresa_id = self.empresa_combo.currentData()
        self._refresh_company_label()
        app_signals.company_selected.emit(self.empresa_combo.currentData())

    def _display_party_name(self, doc) -> str:
        tipo = (doc.tipo_documento or '').lower()
        if any(token in tipo for token in ('saída', 'saida', 'emitida', 'emitidas', 'prestada', 'prestadas')):
            return doc.destinatario_nome or doc.emitente_nome or ''
        return doc.emitente_nome or doc.destinatario_nome or ''

    def _matches_search(self, doc, search_term: str) -> bool:
        haystack = ' '.join([
            doc.chave or '',
            doc.numero or '',
            doc.emitente_nome or '',
            doc.destinatario_nome or '',
            doc.emitente_cnpj or '',
            doc.destinatario_cnpj or '',
            doc.tipo_documento or '',
            doc.situacao or '',
            doc.status or '',
        ]).lower()
        return search_term.lower() in haystack

    def _candidate_directories(self, empresa) -> list[Path]:
        if not empresa:
            return []
        cnpj = (empresa.cnpj or '').strip()
        candidates: list[Path] = []

        cred_portal = self.cred_repo.get_ativo_by_empresa(empresa.id, 'PORTAL')
        base_download = Path(cred_portal.downloads_dir) if cred_portal and cred_portal.downloads_dir else Path(DOWNLOADS_DIR)
        for candidate in [
            Path(XML_DIR) / cnpj,
            Path(DOWNLOADS_DIR) / cnpj,
            base_download,
            base_download / cnpj,
        ]:
            try:
                resolved = candidate.resolve()
            except Exception:
                resolved = candidate
            if resolved not in candidates:
                candidates.append(resolved)

        return [path for path in candidates if path.exists()]

    def sync_company_files(self, show_feedback: bool = False) -> ImportSummary | None:
        empresa_id = self.selected_empresa_id or self.empresa_combo.currentData()
        if not empresa_id:
            return None

        empresa = self.empresa_repo.get_by_id(empresa_id)
        if not empresa:
            return None

        total = ImportSummary()
        scanned_paths: list[str] = []
        for directory in self._candidate_directories(empresa):
            scanned_paths.append(str(directory))
            result = self.import_service.import_company_directory(empresa.id, empresa.cnpj, directory)
            total.scanned += result.scanned
            total.imported += result.imported
            total.updated += result.updated
            total.invalid += result.invalid
            total.duplicates += result.duplicates

        if show_feedback:
            if scanned_paths:
                message = (
                    "Pastas verificadas:\n- " + "\n- ".join(scanned_paths) +
                    f"\n\nVarridos: {total.scanned}\nImportados: {total.imported}\n"
                    f"Atualizados: {total.updated}\nDuplicados: {total.duplicates}\nInválidos: {total.invalid}"
                )
                QMessageBox.information(self, 'Sincronização', message)
            else:
                QMessageBox.information(self, 'Sincronização', 'Nenhuma pasta existente foi encontrada para esta empresa ainda.')

        if scanned_paths:
            log.info(
                f"Sincronização XML empresa {empresa.cnpj}: pastas={scanned_paths} | "
                f"varridos={total.scanned} importados={total.imported} atualizados={total.updated} "
                f"duplicados={total.duplicates} inválidos={total.invalid}"
            )
        return total

    def sync_and_search(self):
        self.sync_company_files(show_feedback=True)
        self.search()

    def search(self, *_args):
        empresa_id = self.selected_empresa_id or self.empresa_combo.currentData()
        if not empresa_id:
            self.current_documents = []
            self.table.setRowCount(0)
            return

        status = self.status_combo.currentText()
        tipo = self.tipo_combo.currentText()
        situacao_filtro = self.situacao_combo.currentText()
        search_term = self.search_input.text().strip()
        start_dt = datetime.combine(self.data_inicio.date().toPython(), datetime.min.time())
        end_dt = datetime.combine(self.data_fim.date().toPython(), datetime.max.time())

        documentos = self.doc_repo.list_by_empresa(empresa_id) if status == "Todos" else self.doc_repo.list_by_status(empresa_id, status)

        documentos = [
            d for d in documentos
            if (d.data_emissao is None or (start_dt <= d.data_emissao <= end_dt))
        ]

        if tipo != "Todos":
            documentos = [d for d in documentos if d.tipo_documento == tipo]

        if situacao_filtro == "Somente canceladas":
            documentos = [d for d in documentos if (d.situacao or '').strip().upper() == 'CANCELADA']
        elif situacao_filtro == "Somente válidas":
            documentos = [d for d in documentos if (d.situacao or 'VALIDO').strip().upper() != 'CANCELADA']

        if search_term:
            documentos = [d for d in documentos if self._matches_search(d, search_term)]

        documentos.sort(key=lambda d: ((d.data_emissao or d.criado_em) or 0, d.id or 0), reverse=True)
        self.current_documents = documentos
        self.table.setRowCount(len(documentos))
        for row, doc in enumerate(documentos):
            party = self._display_party_name(doc)
            self.table.setItem(row, 0, QTableWidgetItem(doc.chave or ""))
            self.table.setItem(row, 1, QTableWidgetItem(doc.numero or ""))
            self.table.setItem(row, 2, QTableWidgetItem(doc.data_emissao.strftime("%d/%m/%Y") if doc.data_emissao else ""))
            party_item = QTableWidgetItem(party)
            party_item.setToolTip(party)
            self.table.setItem(row, 3, party_item)
            self.table.setItem(row, 4, QTableWidgetItem(brl(doc.valor_total or 0)))
            self.table.setItem(row, 5, QTableWidgetItem(doc.situacao or "VALIDO"))
            self.table.setItem(row, 6, QTableWidgetItem(doc.status or ""))
            self.table.setItem(row, 7, QTableWidgetItem(doc.origem_captura or ""))

        self.table.resizeColumnsToContents()
        for column, minimum in {0: 220, 1: 90, 2: 90, 3: 250, 4: 95, 5: 110, 6: 140, 7: 90}.items():
            self.table.setColumnWidth(column, max(minimum, self.table.columnWidth(column)))


    def _export_folder_name(self, empresa, docs: list) -> str:
        start_txt = self.data_inicio.date().toString("ddMMyyyy")
        end_txt = self.data_fim.date().toString("ddMMyyyy")
        if docs:
            dates = [doc.data_emissao for doc in docs if doc.data_emissao]
            if dates:
                start_txt = min(dates).strftime("%d%m%Y")
                end_txt = max(dates).strftime("%d%m%Y")
        return f"{(empresa.cnpj or 'empresa').strip()}_{start_txt}_a_{end_txt}"

    def _type_folder_for_doc(self, doc) -> str:
        tipo = (doc.tipo_documento or '').lower()
        if 'prestada' in tipo or 'emitida' in tipo or 'saida' in tipo or 'saída' in tipo:
            return 'Prestadas'
        return 'Tomadas'

    def export_period_zip(self):
        empresa_id = self.selected_empresa_id or self.empresa_combo.currentData()
        if not empresa_id:
            QMessageBox.warning(self, "Exportar XMLs", "Selecione uma empresa primeiro.")
            return

        docs = [doc for doc in self.current_documents if (doc.arquivo_xml or '').strip()]
        valid_docs = []
        missing = 0
        for doc in docs:
            path = Path((doc.arquivo_xml or '').strip())
            if path.exists() and path.is_file():
                valid_docs.append((doc, path))
            else:
                missing += 1

        if not valid_docs:
            QMessageBox.information(self, "Exportar XMLs", "Não há XMLs válidos na tela para exportar nesse período.")
            return

        empresa = self.empresa_repo.get_by_id(empresa_id)
        base_name = self._export_folder_name(empresa, [doc for doc, _ in valid_docs])
        destino = QFileDialog.getExistingDirectory(self, "Escolher pasta de destino da exportação")
        if not destino:
            return

        destino_root = Path(destino) / base_name
        zip_path = Path(destino) / f"{base_name}.zip"
        counters: dict[Path, int] = {}
        copied = 0

        try:
            if destino_root.exists():
                shutil.rmtree(destino_root)
            destino_root.mkdir(parents=True, exist_ok=True)

            for doc, src in valid_docs:
                tipo_dir = destino_root / self._type_folder_for_doc(doc)
                tipo_dir.mkdir(parents=True, exist_ok=True)
                target = tipo_dir / src.name
                if target.exists():
                    stem = src.stem
                    suffix = src.suffix
                    counters[target.parent] = counters.get(target.parent, 1) + 1
                    target = tipo_dir / f"{stem}_{counters[target.parent]}{suffix}"
                shutil.copy2(src, target)
                copied += 1

            if zip_path.exists():
                zip_path.unlink()
            with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                for file_path in destino_root.rglob('*'):
                    if file_path.is_file():
                        zf.write(file_path, arcname=file_path.relative_to(destino_root.parent))

            message = (
                f"Exportação concluída.\n\n"
                f"Pasta criada: {destino_root}\n"
                f"ZIP criado: {zip_path}\n"
                f"XMLs copiados: {copied}"
            )
            if missing:
                message += f"\nArquivos não encontrados e ignorados: {missing}"
            QMessageBox.information(self, "Exportar XMLs", message)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(destino_root.resolve())))
        except Exception as exc:
            log.exception(f"Falha ao exportar XMLs por período: {exc}")
            QMessageBox.critical(self, "Exportar XMLs", f"Falha ao exportar XMLs: {exc}")

    def _find_official_pdf(self, doc, xml_path: Path) -> Path | None:
        candidates: list[Path] = []
        stem = xml_path.stem
        chave = (doc.chave or '').strip()

        def add(candidate: Path | None):
            if not candidate:
                return
            if candidate not in candidates:
                candidates.append(candidate)

        for candidate in [
            xml_path.with_name(f"{stem}_oficial.pdf"),
            xml_path.with_name(f"{stem}_danfe_oficial.pdf"),
            xml_path.with_name(f"{stem}_danfse_oficial.pdf"),
            xml_path.with_suffix('.pdf'),
        ]:
            add(candidate)

        searchable_tokens = [token for token in [chave, stem] if token and len(token) >= 16]
        if searchable_tokens:
            for directory in [xml_path.parent, *self._candidate_directories(self.empresa_repo.get_by_id(doc.empresa_id))]:
                if not directory or not directory.exists():
                    continue
                for token in searchable_tokens:
                    for pattern in [f"*{token}*_oficial.pdf", f"*{token}_danfe*.pdf", f"*{token}_danfse*.pdf", f"*{token}.pdf"]:
                        try:
                            for match in directory.rglob(pattern):
                                if match.is_file():
                                    add(match)
                        except Exception:
                            continue

        for candidate in candidates:
            try:
                if candidate.exists() and candidate.is_file():
                    return candidate
            except Exception:
                continue
        return None

    def open_folder(self):
        empresa_id = self.selected_empresa_id or self.empresa_combo.currentData()
        if not empresa_id:
            QMessageBox.warning(self, "XMLs", "Selecione uma empresa primeiro.")
            return
        empresa = self.empresa_repo.get_by_id(empresa_id)
        for path in self._candidate_directories(empresa):
            if path.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
                log.info(f"Pasta aberta: {path}")
                return
        QMessageBox.information(self, "XMLs", "Nenhuma pasta de XML/download foi encontrada para esta empresa ainda.")

    def _selected_rows(self) -> list[int]:
        model = self.table.selectionModel()
        if not model:
            return []
        return sorted(index.row() for index in model.selectedRows())

    def _get_selected_document(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.current_documents):
            return None
        return self.current_documents[row]


    def _sync_row_selection(self, row: int, column: int):
        try:
            self.table.setCurrentCell(row, column)
            self.table.selectRow(row)
        except Exception:
            pass

    def _open_row_document(self, row: int, _column: int):
        self.view_xml(rows=[row])

    def view_xml(self, rows: list[int] | None = None):
        if rows is not None:
            selected_rows = rows
        else:
            current_row = self.table.currentRow()
            selected_rows = [current_row] if current_row >= 0 else []
        if not selected_rows:
            QMessageBox.warning(self, "XMLs", "Selecione um XML na lista primeiro.")
            return

        for row in selected_rows:
            if row < 0 or row >= len(self.current_documents):
                continue
            doc = self.current_documents[row]
            xml_path = (doc.arquivo_xml or '').strip()
            if not xml_path:
                log.warning(f"Registro {doc.id} não possui arquivo XML vinculado.")
                continue
                
            path = Path(xml_path)
            if not path.exists():
                log.warning(f"Arquivo não encontrado: {xml_path}")
                continue

            official_pdf = self._find_official_pdf(doc, path)
            if official_pdf and official_pdf.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(official_pdf.resolve())))
                log.info(f"PDF oficial aberto: {official_pdf}")
                continue

            pdf_path = XMLPDFService.ensure_pdf(path)
            if pdf_path and pdf_path.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(pdf_path.resolve())))
                log.info(f"PDF gerado aberto: {pdf_path}")
                continue

            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
            log.info(f"XML aberto: {xml_path}")
            
    def _associated_files_for_delete(self, doc, xml_path: Path) -> list[Path]:
        files: list[Path] = []

        def add_file(candidate: Path | None):
            if not candidate:
                return
            try:
                resolved = candidate.resolve()
            except Exception:
                resolved = candidate
            if resolved not in files:
                files.append(resolved)

        add_file(xml_path)

        raw_path = (doc.arquivo_raw or '').strip()
        if raw_path:
            add_file(Path(raw_path))

        for candidate in [
            xml_path.with_suffix('.pdf'),
            xml_path.with_name(f"{xml_path.stem}_oficial.pdf"),
            xml_path.with_name(f"{xml_path.stem}_danfe_oficial.pdf"),
            xml_path.with_name(f"{xml_path.stem}_danfse_oficial.pdf"),
        ]:
            add_file(candidate)

        official_pdf = self._find_official_pdf(doc, xml_path)
        add_file(official_pdf)
        return files

    def delete_selected_xmls(self):
        selected_rows = self._selected_rows()
        if not selected_rows:
            QMessageBox.warning(self, "Excluir XML", "Selecione um ou mais XMLs na lista primeiro.")
            return

        confirm = QMessageBox.question(
            self,
            "Excluir XML",
            f"Deseja excluir {len(selected_rows)} XML(s) selecionado(s) do banco de dados e da pasta salva?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        deleted_docs = 0
        deleted_files = 0
        missing_files = 0
        errors: list[str] = []

        for row in reversed(selected_rows):
            if row < 0 or row >= len(self.current_documents):
                continue
            doc = self.current_documents[row]
            xml_path_str = (doc.arquivo_xml or '').strip()
            xml_path = Path(xml_path_str) if xml_path_str else None

            for file_path in self._associated_files_for_delete(doc, xml_path) if xml_path else []:
                try:
                    if file_path.exists() and file_path.is_file():
                        file_path.unlink()
                        deleted_files += 1
                    else:
                        missing_files += 1
                except Exception as exc:
                    errors.append(f"{file_path}: {exc}")

            if self.doc_repo.delete(doc.id):
                deleted_docs += 1
            else:
                errors.append(f"Documento {doc.id} não pôde ser removido do banco.")

        self.search()
        message = (
            f"Registros removidos do banco: {deleted_docs}\n"
            f"Arquivos apagados: {deleted_files}\n"
            f"Arquivos não encontrados: {missing_files}"
        )
        if errors:
            message += "\n\nOcorreram alguns avisos:\n" + "\n".join(errors[:10])
        QMessageBox.information(self, "Excluir XML", message)

    def import_manual_xmls(self):
        import shutil
        import uuid
        
        empresa_id = self.selected_empresa_id or self.empresa_combo.currentData()
        if not empresa_id:
            QMessageBox.warning(self, "Importar", "Selecione uma empresa primeiro.")
            return
            
        empresa = self.empresa_repo.get_by_id(empresa_id)
        
        files, _ = QFileDialog.getOpenFileNames(self, "Selecionar XMLs para Importar", "", "XML Files (*.xml)")
        if not files:
            return
            
        # Criar diretório seguro para importação manual
        target_dir = Path(XML_DIR) / empresa.cnpj / "importados_manualmente"
        target_dir.mkdir(parents=True, exist_ok=True)
        
        imported_count = 0
        for file_path in files:
            src = Path(file_path)
            # Usar UUID para evitar sobrescrever arquivos com mesmo nome
            dst = target_dir / f"{uuid.uuid4().hex[:8]}_{src.name}"
            try:
                shutil.copy2(src, dst)
                imported_count += 1
            except Exception as e:
                log.error(f"Erro ao copiar {src}: {e}")
                
        if imported_count > 0:
            QMessageBox.information(self, "Importação", f"{imported_count} arquivos copiados. Iniciando sincronização...")
            self.sync_company_files(show_feedback=True)
            self.search()
