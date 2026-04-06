"""Diálogo de ajuda contextual."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextBrowser, QPushButton, QHBoxLayout

from app.ui.help_content import topic_html, topic_title, build_topics_index_html


class HelpDialog(QDialog):
    def __init__(self, parent=None, topic: str = "geral"):
        super().__init__(parent)
        self.setWindowTitle(topic_title(topic))
        self.resize(900, 720)

        layout = QVBoxLayout(self)
        title = QLabel(topic_title(topic))
        title.setStyleSheet("font-size: 20px; font-weight: bold; margin-bottom: 8px;")
        layout.addWidget(title)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(topic_html(topic) + build_topics_index_html())
        layout.addWidget(browser, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton("Fechar")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
