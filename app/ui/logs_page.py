"""
Página de visualização de logs
"""
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel, QComboBox
)

from app.utils.logger import log
from config.settings import LOGS_DIR


class LogsPage(QWidget):
    """Página de visualização de logs."""

    def __init__(self):
        super().__init__()
        self._loaded_once = False

        layout = QVBoxLayout(self)

        title = QLabel("Logs do Sistema")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)

        controls_layout = QHBoxLayout()

        self.log_file_combo = QComboBox()
        self.log_file_combo.currentIndexChanged.connect(self.refresh_logs)
        controls_layout.addWidget(QLabel("Arquivo:"))
        controls_layout.addWidget(self.log_file_combo)

        btn_refresh = QPushButton("🔄 Atualizar")
        btn_refresh.clicked.connect(self.refresh_logs)
        controls_layout.addWidget(btn_refresh)

        btn_clear = QPushButton("🗑️ Limpar")
        btn_clear.clicked.connect(self.clear_logs)
        controls_layout.addWidget(btn_clear)

        controls_layout.addStretch()
        layout.addLayout(controls_layout)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: 'Courier New';
                font-size: 10px;
            }
        """)
        self.text_edit.setText("Abra a aba de logs para carregar o conteúdo mais recente.")
        layout.addWidget(self.text_edit)

        log.info("Página de logs inicializada")

    def on_page_activated(self):
        self.load_log_files()
        self.refresh_logs()

    def load_log_files(self):
        current_path = self.log_file_combo.currentData()
        self.log_file_combo.blockSignals(True)
        self.log_file_combo.clear()
        for log_file in sorted(LOGS_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True):
            self.log_file_combo.addItem(log_file.name, str(log_file))
        if current_path:
            idx = self.log_file_combo.findData(current_path)
            if idx >= 0:
                self.log_file_combo.setCurrentIndex(idx)
        self.log_file_combo.blockSignals(False)

    def _read_tail(self, log_path: Path, max_bytes: int = 200_000) -> str:
        if not log_path.exists():
            return "Arquivo de log não encontrado"
        size = log_path.stat().st_size
        with open(log_path, 'rb') as f:
            if size > max_bytes:
                f.seek(-max_bytes, 2)
            data = f.read()
        text = data.decode('utf-8', errors='replace')
        lines = text.splitlines()
        if len(lines) > 1000:
            lines = lines[-1000:]
        return '\n'.join(lines)

    def refresh_logs(self):
        if self.log_file_combo.count() == 0:
            self.text_edit.setText("Nenhum arquivo de log encontrado")
            return

        log_path = Path(self.log_file_combo.currentData())
        try:
            content = self._read_tail(log_path)
            self.text_edit.setPlainText(content)
            bar = self.text_edit.verticalScrollBar()
            bar.setValue(bar.maximum())
            self._loaded_once = True
        except Exception as e:
            self.text_edit.setText(f"Erro ao ler log: {str(e)}")

    def clear_logs(self):
        if self.log_file_combo.count() == 0:
            self.text_edit.setText("Nenhum arquivo de log encontrado")
            return
        log_path = Path(self.log_file_combo.currentData())
        try:
            log_path.write_text("", encoding='utf-8')
            self.text_edit.setText("Log limpo com sucesso")
            log.info("Log limpo pelo usuário")
        except Exception as e:
            self.text_edit.setText(f"Erro ao limpar log: {str(e)}")