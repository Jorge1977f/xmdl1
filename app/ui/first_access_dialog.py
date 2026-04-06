"""Diálogo de aviso com sequência de uso e opção de desabilitar."""
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextBrowser, QPushButton, QHBoxLayout, QCheckBox
from PySide6.QtCore import Qt


class FirstAccessDialog(QDialog):
    """Diálogo de aviso que aparece ao entrar no sistema."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚠️ SEQUÊNCIA RECOMENDADA DE USO")
        self.resize(800, 700)
        self.dont_show_again = False
        
        layout = QVBoxLayout(self)
        
        # Título em destaque
        title = QLabel("⚠️ LEIA COM ATENÇÃO - SEQUÊNCIA RECOMENDADA")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #c92a2a; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # Conteúdo HTML com aviso em destaque
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml("""
        <div style="background: #fff3cd; border: 3px solid #ff6b6b; border-radius: 10px; padding: 15px; margin-bottom: 15px;">
            <h3 style="color: #c92a2a; margin-top: 0;">Bem-vindo ao XML Downloader!</h3>
            <p style="font-size: 14px; color: #333; line-height: 1.6;">
                Este programa foi desenvolvido para automatizar o download de documentos fiscais (NFS-e) 
                de forma inteligente e segura. <b>Siga os passos abaixo nesta ordem para começar:</b>
            </p>
        </div>
        
        <h3 style="color: #1565c0; margin-top: 15px;">📋 Sequência Recomendada de Uso:</h3>
        <ol style="font-size: 14px; line-height: 1.8;">
            <li><b>Licenças</b> - Cadastre uma licença (temporária de 7 dias ou adquira uma)</li>
            <li><b>Empresas</b> - Cadastre os dados da sua empresa (Razão Social, CNPJ, UF)</li>
            <li><b>Configurações</b> - Configure o certificado digital e acesso ao portal</li>
            <li><b>Download</b> - Realize o primeiro download de documentos</li>
            <li><b>XMLs</b> - Revise os documentos importados</li>
            <li><b>Relatórios</b> - Gere relatórios conforme necessário</li>
        </ol>
        
        <h3 style="color: #1565c0;">⭐ Dicas Importantes:</h3>
        <ul style="font-size: 14px; line-height: 1.8;">
            <li>Configure o <b>certificado digital ANTES</b> de tentar fazer o primeiro download</li>
            <li>Use <b>F1</b> em qualquer tela para obter ajuda contextual detalhada</li>
            <li>Consulte o módulo <b>Ajuda</b> para manual completo com todas as funcionalidades</li>
            <li>Se tiver dúvidas, acesse os <b>Logs</b> para entender o que aconteceu</li>
        </ul>
        
        <p style="background: #e3f2fd; border-left: 4px solid #1976d2; padding: 10px; margin-top: 15px; font-size: 13px;">
            <b>✓ Próximo passo:</b> Clique em "OK" e vá para o módulo <b>Licenças</b> para começar.
        </p>
        """)
        layout.addWidget(browser, 1)
        
        # Checkbox para não exibir mais
        self.checkbox_dont_show = QCheckBox("Não exibir mais este aviso")
        self.checkbox_dont_show.setStyleSheet("font-size: 12px; margin-top: 10px;")
        layout.addWidget(self.checkbox_dont_show)
        
        # Botão OK
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_ok = QPushButton("✓ OK, Entendi!")
        btn_ok.setMinimumWidth(150)
        btn_ok.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #1976D2; }
            QPushButton:pressed { background-color: #1565C0; }
        """)
        btn_ok.clicked.connect(self.on_ok_clicked)
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)
    
    def on_ok_clicked(self):
        """Captura o estado do checkbox antes de fechar."""
        self.dont_show_again = self.checkbox_dont_show.isChecked()
        self.accept()
