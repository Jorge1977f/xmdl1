"""Página de ajuda e manual geral."""
from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QComboBox, QTextBrowser

from app.ui.help_content import topic_html, topic_title


class AjudaPage(QWidget):
    TOPICS = [
        ("Manual Geral", "geral"),
        ("Dashboard", "dashboard"),
        ("Empresas", "empresas"),
        ("Download", "download"),
        ("XMLs", "xmls"),
        ("Manifestação", "manifestacao"),
        ("Logs", "logs"),
        ("Relatórios", "relatorios"),
        ("Configurações", "configuracoes"),
        ("Licenças", "licencas"),
        ("Limpeza e Backup", "limpeza_backup"),
    ]

    def __init__(self):
        super().__init__()
        self.help_topic = "geral"
        layout = QVBoxLayout(self)

        title = QLabel("Ajuda e Manual")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)

        subtitle = QLabel("Use F1 em qualquer tela para abrir a ajuda contextual correspondente.")
        subtitle.setStyleSheet("color: #64748b; margin-bottom: 6px;")
        layout.addWidget(subtitle)

        top = QHBoxLayout()
        top.addWidget(QLabel("Seção:"))
        self.topic_combo = QComboBox()
        for label, key in self.TOPICS:
            self.topic_combo.addItem(label, key)
        self.topic_combo.currentIndexChanged.connect(self._render_current_topic)
        top.addWidget(self.topic_combo, 1)
        layout.addLayout(top)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        layout.addWidget(self.browser, 1)
        self._render_current_topic()

    def _render_current_topic(self, *_args):
        topic = self.topic_combo.currentData() or "geral"
        self.help_topic = topic
        self.browser.setHtml(topic_html(topic))

    def show_topic(self, topic: str):
        idx = self.topic_combo.findData(topic)
        if idx >= 0:
            self.topic_combo.setCurrentIndex(idx)
        else:
            self.topic_combo.setCurrentIndex(0)

    def on_page_activated(self):
        self._render_current_topic()
