"""
Página de Limpeza, Backup e Restauração de dados.

Interface para gerenciar XMLs, PDFs e JSONs com funcionalidades de:
- Limpeza por período
- Backup automático
- Restauração de dados
- Histórico de operações
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Any

from PySide6.QtCore import QDate, QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QPushButton,
    QDateEdit, QCheckBox, QTableWidget, QTableWidgetItem, QMessageBox,
    QTabWidget, QHeaderView, QFileDialog, QProgressBar,
)
from PySide6.QtGui import QColor

from app.services.cleanup_backup_service import CleanupBackupService
from app.utils.logger import log
from config.settings import DATA_DIR
from app.core import app_signals
from app.db import get_db_session, EmpresaRepository


class ServiceWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], Any], parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            result = self._fn()
            self.completed.emit(result)
        except Exception as e:
            self.failed.emit(str(e))


class LimpezaBackupPage(QWidget):
    """Página de gerenciamento de limpeza, backup e restauração."""

    def __init__(self):
        super().__init__()
        self.service = CleanupBackupService(Path(DATA_DIR))
        self.session = get_db_session()
        self.empresa_repo = EmpresaRepository(self.session)
        self.selected_empresa_id = None
        self._workers: list[ServiceWorker] = []
        self._progress_target: str | None = None
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(200)
        self._progress_timer.timeout.connect(self._refresh_progress)
        app_signals.company_selected.connect(self.set_selected_empresa)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("🗑️ Limpeza, Backup e Restauração")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Gerencie seus dados: faça backup, limpe arquivos antigos e restaure quando necessário."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #64748b; margin-bottom: 10px;")
        layout.addWidget(subtitle)

        self.label_empresa_contexto = QLabel("Empresa ativa para backup/restauração: Todas")
        self.label_empresa_contexto.setStyleSheet("color: #334155; font-weight: bold; margin-bottom: 8px;")
        layout.addWidget(self.label_empresa_contexto)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._criar_aba_limpeza(), "🧹 Limpeza")
        self.tabs.addTab(self._criar_aba_backup(), "💾 Backup")
        self.tabs.addTab(self._criar_aba_restauracao(), "↩️ Restauração")
        self.tabs.addTab(self._criar_aba_historico(), "📋 Histórico")
        layout.addWidget(self.tabs)
        layout.addStretch()

    def set_selected_empresa(self, empresa_id):
        self.selected_empresa_id = empresa_id
        try:
            if empresa_id:
                empresa = self.empresa_repo.get_by_id(int(empresa_id))
                if empresa:
                    nome = f"{empresa.razao_social} - {empresa.cnpj}"
                else:
                    nome = f"ID {empresa_id}"
            else:
                nome = "Todas"
            if hasattr(self, 'label_empresa_contexto'):
                self.label_empresa_contexto.setText(f"Empresa ativa para backup/restauração: {nome}")
        except Exception as e:
            log.warning(f"Não foi possível atualizar contexto da empresa na limpeza/backup: {e}")

    def _start_worker(self, fn: Callable[[], Any], on_success: Callable[[Any], None], on_error: Callable[[str], None]):
        worker = ServiceWorker(fn, self)
        self._workers.append(worker)

        def cleanup_worker():
            try:
                self._workers.remove(worker)
            except ValueError:
                pass
            worker.deleteLater()

        def success_handler(result):
            cleanup_worker()
            on_success(result)

        def error_handler(message):
            cleanup_worker()
            on_error(message)

        worker.completed.connect(success_handler)
        worker.failed.connect(error_handler)
        worker.start()

    def _progress_widgets(self):
        widgets = {}
        pairs = {
            'limpeza': ('progress_limpeza', 'label_resultado_limpeza'),
            'backup': ('progress_backup', 'label_resultado_backup'),
            'restauracao': ('progress_restauracao', 'label_resultado_restauracao'),
        }
        for key, (bar_name, label_name) in pairs.items():
            bar = getattr(self, bar_name, None)
            label = getattr(self, label_name, None)
            if bar is not None and label is not None:
                widgets[key] = (bar, label)
        return widgets

    def _start_progress_monitor(self, target: str):
        widgets = self._progress_widgets()
        if target not in widgets:
            log.warning(f'Widget de progresso não encontrado para: {target}')
            self._progress_target = None
            return
        self._progress_target = target
        for key, (bar, _) in widgets.items():
            if key == target:
                bar.setVisible(True)
                bar.setRange(0, 0)
                bar.setValue(0)
            else:
                bar.setVisible(False)
        self._progress_timer.start()

    def _stop_progress_monitor(self):
        self._progress_timer.stop()
        self._progress_target = None
        for bar, _ in self._progress_widgets().values():
            bar.setVisible(False)
            bar.setValue(0)

    def _refresh_progress(self):
        if not self._progress_target:
            return
        progress = self.service.get_progress()
        widgets = self._progress_widgets()
        if self._progress_target not in widgets:
            self._stop_progress_monitor()
            return
        bar, label = widgets[self._progress_target]
        total = int(progress.get('total') or 0)
        current = int(progress.get('current') or 0)
        phase = str(progress.get('phase') or '').strip()
        detail = str(progress.get('detail') or '').strip()
        if total > 0:
            bar.setRange(0, total)
            bar.setValue(min(current, total))
            percent = int(progress.get('percent') or 0)
            bar.setFormat(f"{percent}%")
        else:
            bar.setRange(0, 0)
            bar.setFormat("Processando...")
        if phase:
            suffix = f"\n📄 {detail}" if detail else ''
            label.setText(f"⏳ {phase}{suffix}")
            label.setStyleSheet("color: #1976d2; font-weight: bold;")
        if not progress.get('active') and total > 0:
            bar.setRange(0, max(total, 1))
            bar.setValue(min(current, max(total, 1)))

    def _criar_aba_limpeza(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        aviso = QGroupBox("⚠️ Aviso Importante")
        aviso_layout = QVBoxLayout(aviso)
        aviso_label = QLabel(
            "A limpeza irá DELETAR permanentemente os arquivos selecionados.\n"
            "Um backup será criado automaticamente antes da limpeza."
        )
        aviso_label.setStyleSheet("color: #d32f2f; font-weight: bold;")
        aviso_layout.addWidget(aviso_label)
        layout.addWidget(aviso)

        filtros = QGroupBox("Filtros de Limpeza")
        filtros_layout = QVBoxLayout(filtros)

        periodo_layout = QHBoxLayout()
        periodo_layout.addWidget(QLabel("Período:"))
        self.data_inicio_limpeza = QDateEdit()
        self.data_inicio_limpeza.setDate(QDate.currentDate().addMonths(-1))
        self.data_inicio_limpeza.setCalendarPopup(True)
        self.data_inicio_limpeza.setDisplayFormat("dd/MM/yyyy")
        periodo_layout.addWidget(QLabel("De:"))
        periodo_layout.addWidget(self.data_inicio_limpeza)

        self.data_fim_limpeza = QDateEdit()
        self.data_fim_limpeza.setDate(QDate.currentDate())
        self.data_fim_limpeza.setCalendarPopup(True)
        self.data_fim_limpeza.setDisplayFormat("dd/MM/yyyy")
        periodo_layout.addWidget(QLabel("Até:"))
        periodo_layout.addWidget(self.data_fim_limpeza)
        periodo_layout.addStretch()
        filtros_layout.addLayout(periodo_layout)

        tipos_layout = QHBoxLayout()
        tipos_layout.addWidget(QLabel("Tipos de arquivo:"))
        self.check_xml_limpeza = QCheckBox("XML")
        self.check_xml_limpeza.setChecked(True)
        self.check_pdf_limpeza = QCheckBox("PDF")
        self.check_pdf_limpeza.setChecked(True)
        self.check_json_limpeza = QCheckBox("JSON")
        self.check_json_limpeza.setChecked(True)
        tipos_layout.addWidget(self.check_xml_limpeza)
        tipos_layout.addWidget(self.check_pdf_limpeza)
        tipos_layout.addWidget(self.check_json_limpeza)
        tipos_layout.addStretch()
        filtros_layout.addLayout(tipos_layout)
        layout.addWidget(filtros)

        btn_layout = QHBoxLayout()
        self.btn_limpar = QPushButton("🗑️ Limpar Arquivos")
        self.btn_limpar.setStyleSheet("background-color: #d32f2f; color: white; font-weight: bold; padding: 8px;")
        self.btn_limpar.clicked.connect(self._executar_limpeza)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_limpar)
        layout.addLayout(btn_layout)

        self.progress_limpeza = QProgressBar()
        self.progress_limpeza.setVisible(False)
        self.progress_limpeza.setTextVisible(True)
        self.progress_limpeza.setFormat("%p%")
        layout.addWidget(self.progress_limpeza)

        self.label_resultado_limpeza = QLabel("")
        self.label_resultado_limpeza.setWordWrap(True)
        layout.addWidget(self.label_resultado_limpeza)
        layout.addStretch()
        return widget

    def _criar_aba_backup(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        info = QGroupBox("Criar Backup")
        info_layout = QVBoxLayout(info)
        info_label = QLabel(
            "Crie um backup de seus dados para proteção.\n"
            "Selecione o local onde o arquivo ZIP será salvo. JSON inclui também dados internos do sistema."
        )
        info_layout.addWidget(info_label)
        layout.addWidget(info)

        filtros = QGroupBox("Filtros de Backup")
        filtros_layout = QVBoxLayout(filtros)

        periodo_layout = QHBoxLayout()
        periodo_layout.addWidget(QLabel("Período (opcional):"))
        self.data_inicio_backup = QDateEdit()
        self.data_inicio_backup.setDate(QDate.currentDate().addMonths(-3))
        self.data_inicio_backup.setCalendarPopup(True)
        self.data_inicio_backup.setDisplayFormat("dd/MM/yyyy")
        periodo_layout.addWidget(QLabel("De:"))
        periodo_layout.addWidget(self.data_inicio_backup)

        self.data_fim_backup = QDateEdit()
        self.data_fim_backup.setDate(QDate.currentDate())
        self.data_fim_backup.setCalendarPopup(True)
        self.data_fim_backup.setDisplayFormat("dd/MM/yyyy")
        periodo_layout.addWidget(QLabel("Até:"))
        periodo_layout.addWidget(self.data_fim_backup)
        periodo_layout.addStretch()
        filtros_layout.addLayout(periodo_layout)

        tipos_layout = QHBoxLayout()
        tipos_layout.addWidget(QLabel("Tipos de arquivo:"))
        self.check_xml_backup = QCheckBox("XML")
        self.check_xml_backup.setChecked(True)
        self.check_pdf_backup = QCheckBox("PDF")
        self.check_pdf_backup.setChecked(True)
        self.check_json_backup = QCheckBox("JSON + dados internos")
        self.check_json_backup.setChecked(True)
        tipos_layout.addWidget(self.check_xml_backup)
        tipos_layout.addWidget(self.check_pdf_backup)
        tipos_layout.addWidget(self.check_json_backup)
        tipos_layout.addStretch()
        filtros_layout.addLayout(tipos_layout)
        layout.addWidget(filtros)

        btn_layout = QHBoxLayout()
        self.btn_backup = QPushButton("💾 Criar Backup Agora")
        self.btn_backup.setStyleSheet("background-color: #1976d2; color: white; font-weight: bold; padding: 8px;")
        self.btn_backup.clicked.connect(self._executar_backup)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_backup)
        layout.addLayout(btn_layout)

        self.progress_backup = QProgressBar()
        self.progress_backup.setVisible(False)
        self.progress_backup.setTextVisible(True)
        self.progress_backup.setFormat("%p%")
        layout.addWidget(self.progress_backup)

        self.label_resultado_backup = QLabel("")
        self.label_resultado_backup.setWordWrap(True)
        layout.addWidget(self.label_resultado_backup)
        layout.addStretch()
        return widget

    def _criar_aba_restauracao(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        info = QGroupBox("Restaurar Backup")
        info_layout = QVBoxLayout(info)
        info_label = QLabel(
            "Selecione um backup para restaurar seus dados.\n"
            "Os arquivos restaurados irão sobrescrever os existentes."
        )
        info_layout.addWidget(info_label)
        layout.addWidget(info)

        backups_group = QGroupBox("Backups Disponíveis")
        backups_layout = QVBoxLayout(backups_group)
        self.table_backups = QTableWidget()
        self.table_backups.setColumnCount(4)
        self.table_backups.setHorizontalHeaderLabels(["Nome", "Data", "Tamanho (MB)", "Ações"])
        self.table_backups.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_backups.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_backups.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_backups.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        backups_layout.addWidget(self.table_backups)
        layout.addWidget(backups_group)

        btn_layout = QHBoxLayout()
        self.btn_escolher_arquivo_restauracao = QPushButton("📂 Escolher arquivo ZIP...")
        self.btn_escolher_arquivo_restauracao.clicked.connect(self._escolher_backup_para_restaurar)
        btn_layout.addWidget(self.btn_escolher_arquivo_restauracao)
        self.btn_atualizar_backups = QPushButton("🔄 Atualizar Lista")
        self.btn_atualizar_backups.clicked.connect(self._atualizar_lista_backups)
        btn_layout.addWidget(self.btn_atualizar_backups)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.progress_restauracao = QProgressBar()
        self.progress_restauracao.setVisible(False)
        self.progress_restauracao.setTextVisible(True)
        self.progress_restauracao.setFormat("%p%")
        layout.addWidget(self.progress_restauracao)

        self.label_resultado_restauracao = QLabel("")
        self.label_resultado_restauracao.setWordWrap(True)
        layout.addWidget(self.label_resultado_restauracao)

        self._atualizar_lista_backups()
        layout.addStretch()
        return widget

    def _criar_aba_historico(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        historico_group = QGroupBox("Histórico de Operações")
        historico_layout = QVBoxLayout(historico_group)
        self.table_historico = QTableWidget()
        self.table_historico.setColumnCount(7)
        self.table_historico.setHorizontalHeaderLabels([
            "Tipo", "Data", "Período", "Quantidade", "Tamanho (MB)", "Status", "Mensagem"
        ])
        self.table_historico.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        historico_layout.addWidget(self.table_historico)
        layout.addWidget(historico_group)

        btn_layout = QHBoxLayout()
        self.btn_atualizar_historico = QPushButton("🔄 Atualizar Histórico")
        self.btn_atualizar_historico.clicked.connect(self._atualizar_historico)
        btn_layout.addWidget(self.btn_atualizar_historico)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self._atualizar_historico()
        return widget

    def _tipos_backup(self) -> list[str]:
        tipos = []
        if self.check_xml_backup.isChecked():
            tipos.append('XML')
        if self.check_pdf_backup.isChecked():
            tipos.append('PDF')
        if self.check_json_backup.isChecked():
            tipos.append('JSON')
        return tipos

    def _tipos_limpeza(self) -> list[str]:
        tipos = []
        if self.check_xml_limpeza.isChecked():
            tipos.append('XML')
        if self.check_pdf_limpeza.isChecked():
            tipos.append('PDF')
        if self.check_json_limpeza.isChecked():
            tipos.append('JSON')
        return tipos

    def _executar_limpeza(self):
        resposta = QMessageBox.question(
            self,
            "Confirmar Limpeza",
            "Tem certeza que deseja limpar os arquivos selecionados?\n\n"
            "Um backup será criado automaticamente antes da limpeza.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if resposta != QMessageBox.Yes:
            return

        tipos = self._tipos_limpeza()
        if not tipos:
            QMessageBox.warning(self, "Validação", "Selecione pelo menos um tipo de arquivo")
            return

        self.btn_limpar.setEnabled(False)
        self.label_resultado_limpeza.setStyleSheet("color: #1976d2; font-weight: bold;")
        self.label_resultado_limpeza.setText("⏳ Executando limpeza em segundo plano...")
        self._start_progress_monitor('limpeza')

        def task():
            return self.service.limpar_arquivos(
                periodo_inicio=self.data_inicio_limpeza.date().toPython(),
                periodo_fim=self.data_fim_limpeza.date().toPython(),
                tipos=tipos,
                empresa_id=self.selected_empresa_id,
            )

        def ok(result):
            self._stop_progress_monitor()
            self.btn_limpar.setEnabled(True)
            sucesso, mensagem, quantidade = result
            del quantidade
            if sucesso:
                self.label_resultado_limpeza.setText(f"✅ {mensagem}")
                self.label_resultado_limpeza.setStyleSheet("color: #4CAF50; font-weight: bold;")
                QMessageBox.information(self, "Sucesso", mensagem)
                self._refresh_after_operation(include_backups=True)
            else:
                self.label_resultado_limpeza.setText(f"❌ {mensagem}")
                self.label_resultado_limpeza.setStyleSheet("color: #d32f2f; font-weight: bold;")
                QMessageBox.warning(self, "Erro", mensagem)

        def fail(message):
            self._stop_progress_monitor()
            self.btn_limpar.setEnabled(True)
            msg = f"Erro ao limpar arquivos: {message}"
            self.label_resultado_limpeza.setText(f"❌ {msg}")
            self.label_resultado_limpeza.setStyleSheet("color: #d32f2f; font-weight: bold;")
            QMessageBox.critical(self, "Erro", msg)
            log.error(msg)

        self._start_worker(task, ok, fail)

    def _executar_backup(self):
        tipos = self._tipos_backup()
        if not tipos:
            QMessageBox.warning(self, "Validação", "Selecione pelo menos um tipo de arquivo")
            return

        default_path = self.service.backup_dir / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        caminho, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar backup como",
            str(default_path),
            "Arquivos ZIP (*.zip)",
        )
        if not caminho:
            return

        self.btn_backup.setEnabled(False)
        self.label_resultado_backup.setStyleSheet("color: #1976d2; font-weight: bold;")
        self.label_resultado_backup.setText(f"⏳ Gerando backup em segundo plano...\n📁 Destino: {caminho}")
        self._start_progress_monitor('backup')

        def task():
            return self.service.criar_backup(
                periodo_inicio=self.data_inicio_backup.date().toPython(),
                periodo_fim=self.data_fim_backup.date().toPython(),
                tipos=tipos,
                empresa_id=self.selected_empresa_id,
                destino_path=caminho,
            )

        def ok(result):
            self._stop_progress_monitor()
            self.btn_backup.setEnabled(True)
            sucesso, mensagem, backup_path = result
            if sucesso:
                self.label_resultado_backup.setText(f"✅ {mensagem}\n📁 Salvo em: {backup_path}")
                self.label_resultado_backup.setStyleSheet("color: #4CAF50; font-weight: bold;")
                QMessageBox.information(self, "Sucesso", f"{mensagem}\n\nSalvo em:\n{backup_path}")
                self._refresh_after_operation(include_backups=True)
            else:
                self.label_resultado_backup.setText(f"❌ {mensagem}")
                self.label_resultado_backup.setStyleSheet("color: #d32f2f; font-weight: bold;")
                QMessageBox.warning(self, "Erro", mensagem)

        def fail(message):
            self._stop_progress_monitor()
            self.btn_backup.setEnabled(True)
            msg = f"Erro ao criar backup: {message}"
            self.label_resultado_backup.setText(f"❌ {msg}")
            self.label_resultado_backup.setStyleSheet("color: #d32f2f; font-weight: bold;")
            QMessageBox.critical(self, "Erro", msg)
            log.error(msg)

        self._start_worker(task, ok, fail)

    def _escolher_backup_para_restaurar(self):
        caminho, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar backup para restaurar",
            str(self.service.backup_dir),
            "Arquivos ZIP (*.zip)",
        )
        if caminho:
            self._restaurar_backup(caminho)

    def _refresh_after_operation(self, include_backups: bool = False):
        def do_refresh():
            try:
                self._atualizar_historico()
                if include_backups:
                    self._atualizar_lista_backups()
            except Exception as e:
                log.error(f"Erro ao atualizar tela após operação: {e}")
        QTimer.singleShot(50, do_refresh)

    def _atualizar_lista_backups(self):
        try:
            backups = self.service.listar_backups()
            self.table_backups.setRowCount(len(backups))
            for idx, backup in enumerate(backups):
                self.table_backups.setItem(idx, 0, QTableWidgetItem(backup['nome']))
                self.table_backups.setItem(idx, 1, QTableWidgetItem(backup['data_criacao'].strftime('%d/%m/%Y %H:%M:%S')))
                self.table_backups.setItem(idx, 2, QTableWidgetItem(f"{backup['tamanho_mb']:.2f}"))
                btn_restaurar = QPushButton("↩️ Restaurar")
                btn_restaurar.clicked.connect(lambda checked=False, bp=backup['caminho']: self._restaurar_backup(bp))
                self.table_backups.setCellWidget(idx, 3, btn_restaurar)
        except Exception as e:
            log.error(f"Erro ao atualizar lista de backups: {e}")

    def _restaurar_backup(self, backup_path: str):
        resposta = QMessageBox.question(
            self,
            "Confirmar Restauração",
            "Tem certeza que deseja restaurar este backup?\n\n"
            "Os arquivos existentes serão sobrescritos.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if resposta != QMessageBox.Yes:
            return

        self.btn_escolher_arquivo_restauracao.setEnabled(False)
        self.btn_atualizar_backups.setEnabled(False)
        self.label_resultado_restauracao.setStyleSheet("color: #1976d2; font-weight: bold;")
        self.label_resultado_restauracao.setText(f"⏳ Restaurando backup em segundo plano...\n📁 Arquivo: {backup_path}")
        self._start_progress_monitor('restauracao')

        def task():
            return self.service.restaurar_backup(backup_path, empresa_id=self.selected_empresa_id)

        def ok(result):
            self._stop_progress_monitor()
            self.btn_escolher_arquivo_restauracao.setEnabled(True)
            self.btn_atualizar_backups.setEnabled(True)
            sucesso, mensagem, quantidade = result
            del quantidade
            if sucesso:
                self.label_resultado_restauracao.setText(f"✅ {mensagem}\n📁 Arquivo: {backup_path}")
                self.label_resultado_restauracao.setStyleSheet("color: #4CAF50; font-weight: bold;")
                QMessageBox.information(self, "Sucesso", mensagem)
                self._refresh_after_operation(include_backups=False)
            else:
                self.label_resultado_restauracao.setText(f"❌ {mensagem}")
                self.label_resultado_restauracao.setStyleSheet("color: #d32f2f; font-weight: bold;")
                QMessageBox.warning(self, "Erro", mensagem)

        def fail(message):
            self._stop_progress_monitor()
            self.btn_escolher_arquivo_restauracao.setEnabled(True)
            self.btn_atualizar_backups.setEnabled(True)
            msg = f"Erro ao restaurar backup: {message}"
            self.label_resultado_restauracao.setText(f"❌ {msg}")
            self.label_resultado_restauracao.setStyleSheet("color: #d32f2f; font-weight: bold;")
            QMessageBox.critical(self, "Erro", msg)
            log.error(msg)

        self._start_worker(task, ok, fail)

    def _atualizar_historico(self):
        try:
            historico = self.service.obter_historico_operacoes()
            self.table_historico.setRowCount(len(historico))
            for idx, op in enumerate(historico):
                self.table_historico.setItem(idx, 0, QTableWidgetItem(op['tipo']))
                self.table_historico.setItem(idx, 1, QTableWidgetItem(op['data']))
                self.table_historico.setItem(idx, 2, QTableWidgetItem(op['periodo']))
                self.table_historico.setItem(idx, 3, QTableWidgetItem(str(op['quantidade'])))
                self.table_historico.setItem(idx, 4, QTableWidgetItem(f"{op['tamanho_mb']:.2f}"))
                status_item = QTableWidgetItem(op['status'])
                if op['status'] == 'SUCESSO':
                    status_item.setForeground(QColor('#4CAF50'))
                elif op['status'] == 'PARCIAL':
                    status_item.setForeground(QColor('#FF9800'))
                else:
                    status_item.setForeground(QColor('#d32f2f'))
                self.table_historico.setItem(idx, 5, status_item)
                self.table_historico.setItem(idx, 6, QTableWidgetItem(op['mensagem']))
        except Exception as e:
            log.error(f"Erro ao atualizar histórico: {e}")
