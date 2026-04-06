"""Página de cadastro do comprador, trial e licenciamento."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QFrame, QGroupBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSpinBox, QTextEdit, QVBoxLayout, QWidget
)

from app.services import LicensingService
from app.utils.logger import log
from app.utils.validators import Validators
from config.settings import LICENSE_DISCOUNT_RATE, LICENSE_DISCOUNT_START_FROM, LICENSE_PRICE_PER_MACHINE


class LicencasPage(QWidget):
    """Módulo visual de licença e ativação."""

    def __init__(self):
        super().__init__()
        self.service = LicensingService()
        self._payment_visible = False

        layout = QVBoxLayout(self)
        title = QLabel("Licenças")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Cadastre o comprador do software, acompanhe o teste de 7 dias e gere o Pix para liberar novos downloads. "
            "Após o fim do trial, os XMLs já baixados continuam disponíveis, mas o sistema bloqueia novas capturas no portal."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #64748b; margin-bottom: 6px;")
        layout.addWidget(subtitle)

        self.status_banner = QLabel()
        self.status_banner.setWordWrap(True)
        self.status_banner.setStyleSheet(
            "background: #eff6ff; border: 1px solid #bfdbfe; color: #1d4ed8; border-radius: 8px; padding: 10px;"
        )
        layout.addWidget(self.status_banner)

        cadastro_group = QGroupBox("Cadastro do comprador")
        cadastro_layout = QFormLayout(cadastro_group)
        self.nome_edit = QLineEdit()
        self.documento_edit = QLineEdit()
        self.documento_edit.setPlaceholderText("Digite um CPF ou CNPJ válido")
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("nome@dominio.com")
        self.telefone_edit = QLineEdit()
        self.telefone_edit.setPlaceholderText("(49) 99999-9999")
        self.telefone_edit.textChanged.connect(self._apply_phone_mask)
        self.machine_label = QLabel("-")
        self.machine_label.setWordWrap(True)
        cadastro_layout.addRow("Nome:", self.nome_edit)
        cadastro_layout.addRow("CPF/CNPJ:", self.documento_edit)
        cadastro_layout.addRow("E-mail:", self.email_edit)
        cadastro_layout.addRow("Telefone:", self.telefone_edit)
        cadastro_layout.addRow("Máquina atual:", self.machine_label)
        layout.addWidget(cadastro_group)

        cadastro_buttons = QHBoxLayout()
        self.btn_salvar = QPushButton("💾 Salvar cadastro")
        self.btn_salvar.clicked.connect(self.save_buyer)
        cadastro_buttons.addWidget(self.btn_salvar)
        self.btn_sync = QPushButton("🔄 Atualizar status")
        self.btn_sync.clicked.connect(lambda: self.refresh_status(force_sync=True))
        cadastro_buttons.addWidget(self.btn_sync)
        cadastro_buttons.addStretch()
        layout.addLayout(cadastro_buttons)

        compra_group = QGroupBox("Compra de licenças")
        compra_layout = QFormLayout(compra_group)
        self.qtd_spin = QSpinBox()
        self.qtd_spin.setMinimum(1)
        self.qtd_spin.setMaximum(999)
        self.qtd_spin.setValue(1)
        self.qtd_spin.valueChanged.connect(self.update_price_preview)
        self.price_label = QLabel()
        self.price_label.setWordWrap(True)
        self.info_label = QLabel(
            f"Valor base: R$ {LICENSE_PRICE_PER_MACHINE:.2f} por computador. "
            f"A partir da {LICENSE_DISCOUNT_START_FROM}ª licença, cada nova recebe {int(LICENSE_DISCOUNT_RATE * 100)}% de desconto."
        )
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: #64748b;")
        compra_layout.addRow("Quantidade:", self.qtd_spin)
        compra_layout.addRow("Resumo:", self.price_label)
        compra_layout.addRow("Regra:", self.info_label)
        layout.addWidget(compra_group)

        compra_buttons = QHBoxLayout()
        self.btn_pix = QPushButton("💸 Gerar Pix")
        self.btn_pix.clicked.connect(self.create_pix_order)
        compra_buttons.addWidget(self.btn_pix)
        self.btn_toggle_pix = QPushButton("👁 Mostrar cobrança Pix")
        self.btn_toggle_pix.clicked.connect(self.toggle_payment_visibility)
        self.btn_toggle_pix.setEnabled(False)
        compra_buttons.addWidget(self.btn_toggle_pix)
        self.btn_copy = QPushButton("📋 Copiar Pix")
        self.btn_copy.clicked.connect(self.copy_pix_code)
        self.btn_copy.setEnabled(False)
        compra_buttons.addWidget(self.btn_copy)
        compra_buttons.addStretch()
        layout.addLayout(compra_buttons)

        pix_group = QGroupBox("Cobrança Pix")
        pix_layout = QVBoxLayout(pix_group)
        self.pix_status_label = QLabel("Nenhum pedido Pix gerado ainda.")
        self.pix_status_label.setWordWrap(True)
        self.pix_hint_label = QLabel("A cobrança fica oculta por segurança e só aparece quando você pedir.")
        self.pix_hint_label.setWordWrap(True)
        self.pix_hint_label.setStyleSheet("color: #64748b;")

        self.payment_details = QWidget()
        payment_details_layout = QVBoxLayout(self.payment_details)
        payment_details_layout.setContentsMargins(0, 0, 0, 0)
        payment_details_layout.setSpacing(8)

        self.pix_qr_label = QLabel()
        self.pix_qr_label.setAlignment(Qt.AlignCenter)
        self.pix_qr_label.setMinimumHeight(160)
        self.pix_qr_label.setStyleSheet("border: 1px dashed #cbd5e1; border-radius: 8px; color: #94a3b8;")
        self.pix_text = QTextEdit()
        self.pix_text.setReadOnly(True)
        self.pix_text.setPlaceholderText("O código Pix copia e cola aparece aqui quando o backend gerar o pedido.")
        payment_details_layout.addWidget(self.pix_qr_label)
        payment_details_layout.addWidget(self.pix_text)

        pix_layout.addWidget(self.pix_status_label)
        pix_layout.addWidget(self.pix_hint_label)
        pix_layout.addWidget(self.payment_details)
        layout.addWidget(pix_group)

        footer = QFrame()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        self.server_mode_label = QLabel()
        self.server_mode_label.setStyleSheet("color: #64748b; font-size: 11px;")
        footer_layout.addWidget(self.server_mode_label)
        footer_layout.addStretch()
        layout.addWidget(footer)

        self.update_price_preview()
        self._apply_payment_visibility()
        self.refresh_status(force_sync=False)
        log.info("Página de licenças inicializada")

    def on_page_activated(self):
        self.refresh_status(force_sync=False)

    def update_price_preview(self):
        resumo = self.service.calculate_price(self.qtd_spin.value())
        text = (
            f"{resumo['quantity']} licença(s) · total R$ {resumo['total']:.2f}. "
            f"Até a 5ª: R$ {resumo['base_unit_price']:.2f} cada. "
            f"Da 6ª em diante: R$ {resumo['discounted_unit_price']:.2f} cada."
        )
        if resumo["discounted_quantity"] <= 0:
            text = f"{resumo['quantity']} licença(s) · total R$ {resumo['total']:.2f}."
        self.price_label.setText(text.replace('.', ','))

    def _apply_phone_mask(self):
        formatted = Validators.format_phone(self.telefone_edit.text())
        if formatted != self.telefone_edit.text():
            cursor = len(formatted)
            self.telefone_edit.blockSignals(True)
            self.telefone_edit.setText(formatted)
            self.telefone_edit.setCursorPosition(cursor)
            self.telefone_edit.blockSignals(False)

    def _validate_buyer_fields(self) -> tuple[bool, str]:
        nome = (self.nome_edit.text() or "").strip()
        documento = (self.documento_edit.text() or "").strip()
        email = (self.email_edit.text() or "").strip()
        telefone = (self.telefone_edit.text() or "").strip()

        if not nome:
            return False, "Informe o nome do comprador."
        if not Validators.validate_cpf_or_cnpj(documento):
            return False, "Informe um CPF ou CNPJ válido."
        if not Validators.validate_email(email):
            return False, "Informe um e-mail válido."
        if not Validators.validate_phone(telefone):
            return False, "Informe um telefone válido com DDD."
        return True, ""

    def save_buyer(self):
        ok, error = self._validate_buyer_fields()
        if not ok:
            QMessageBox.warning(self, "Licenças", error)
            return

        self.documento_edit.setText(Validators.only_digits(self.documento_edit.text()))
        self.telefone_edit.setText(Validators.format_phone(self.telefone_edit.text()))

        snapshot = self.service.save_buyer(
            self.nome_edit.text(),
            self.documento_edit.text(),
            self.email_edit.text(),
            self.telefone_edit.text(),
        )
        self.apply_snapshot(snapshot)
        QMessageBox.information(self, "Licenças", "Cadastro salvo. O status do teste/licença foi atualizado.")

    def refresh_status(self, force_sync: bool = False):
        snapshot = self.service.get_snapshot(force_sync=force_sync)
        self.apply_snapshot(snapshot)

    def create_pix_order(self):
        ok, message, snapshot = self.service.create_pix_order(self.qtd_spin.value())
        self._payment_visible = False
        self.apply_snapshot(snapshot)
        if ok:
            QMessageBox.information(
                self,
                "Licenças",
                message + "\n\nA cobrança Pix foi mantida oculta na tela por segurança. Use 'Mostrar cobrança Pix' apenas quando precisar."
            )
        else:
            QMessageBox.warning(self, "Licenças", message)

    def toggle_payment_visibility(self):
        has_payment = bool(self.pix_text.toPlainText().strip()) or bool(self.pix_qr_label.pixmap())
        if not has_payment and not self.btn_toggle_pix.isEnabled():
            QMessageBox.information(self, "Licenças", "Ainda não há uma cobrança Pix pendente para exibir.")
            return
        self._payment_visible = not self._payment_visible
        self._apply_payment_visibility()

    def _apply_payment_visibility(self):
        self.payment_details.setVisible(self._payment_visible)
        self.btn_toggle_pix.setText("🙈 Ocultar cobrança Pix" if self._payment_visible else "👁 Mostrar cobrança Pix")
        if self.btn_toggle_pix.isEnabled():
            self.pix_hint_label.setText(
                "Cobrança visível nesta tela. Oculte quando terminar."
                if self._payment_visible
                else "Cobrança oculta por segurança. Use 'Mostrar cobrança Pix' apenas quando precisar copiar ou exibir o QR Code."
            )
        else:
            self.pix_hint_label.setText("Nenhuma cobrança Pix pendente no momento.")

    def copy_pix_code(self):
        code = self.pix_text.toPlainText().strip()
        if not code:
            QMessageBox.information(self, "Licenças", "Ainda não há um código Pix para copiar.")
            return
        QApplication.clipboard().setText(code)
        QMessageBox.information(self, "Licenças", "Código Pix copiado para a área de transferência.")

    def apply_snapshot(self, snapshot):
        self.nome_edit.setText(snapshot.buyer_name)
        self.documento_edit.setText(snapshot.documento)
        self.email_edit.setText(snapshot.email)
        self.telefone_edit.setText(Validators.format_phone(snapshot.telefone))
        machine_text = snapshot.machine_name or "máquina-desconhecida"
        if snapshot.machine_id:
            machine_text += f" · ID {snapshot.machine_id[:12]}..."
        self.machine_label.setText(machine_text)
        if not snapshot.backend_configured:
            server_mode_text = "Backend não configurado: o app está em modo local de desenvolvimento."
        elif snapshot.offline_error:
            server_mode_text = f"Backend configurado, com falha recente de comunicação: {snapshot.offline_error}"
        else:
            server_mode_text = "Controle por backend ativo."
        self.server_mode_label.setText(server_mode_text)

        banner_color = "#eff6ff"
        border_color = "#bfdbfe"
        text_color = "#1d4ed8"
        if snapshot.status == "ATIVA":
            banner_color = "#ecfdf5"
            border_color = "#86efac"
            text_color = "#166534"
        elif snapshot.status in {"TRIAL_EXPIRADO", "PAGAMENTO_PENDENTE", "BLOQUEADA"}:
            banner_color = "#fff7ed"
            border_color = "#fdba74"
            text_color = "#c2410c"
        self.status_banner.setStyleSheet(
            f"background: {banner_color}; border: 1px solid {border_color}; color: {text_color}; border-radius: 8px; padding: 10px;"
        )

        extra = []
        if snapshot.trial_expires_at:
            extra.append(f"Trial até {snapshot.trial_expires_at.strftime('%d/%m/%Y %H:%M')}")
        if snapshot.last_sync_at:
            extra.append(f"Última sincronização {snapshot.last_sync_at.strftime('%d/%m/%Y %H:%M')}")
        if snapshot.licenses_total:
            extra.append(f"Máquinas em uso {snapshot.licenses_in_use}/{snapshot.licenses_total}")
        header = f"{snapshot.status_label}"
        if extra:
            header += " · " + " · ".join(extra)
        self.status_banner.setText(header + "\n" + snapshot.message)

        has_payment = bool(snapshot.pending_order_id)
        pix_message = "Nenhum pedido Pix gerado ainda."
        if has_payment:
            pix_message = f"Pedido {snapshot.pending_order_id}"
            if snapshot.pix_expires_at:
                pix_message += f" · vence em {snapshot.pix_expires_at.strftime('%d/%m/%Y %H:%M')}"
        self.pix_status_label.setText(pix_message)
        self.pix_text.setPlainText(snapshot.pix_copy_paste or "")

        qr_data = self.service.decode_qr_code(snapshot.pix_qr_code_base64)
        if qr_data:
            pixmap = QPixmap()
            pixmap.loadFromData(qr_data)
            self.pix_qr_label.setPixmap(pixmap.scaled(220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.pix_qr_label.setText("")
        else:
            self.pix_qr_label.setPixmap(QPixmap())
            self.pix_qr_label.setText("QR Code Pix aparecerá aqui")

        self.btn_toggle_pix.setEnabled(has_payment)
        self.btn_copy.setEnabled(bool(snapshot.pix_copy_paste))
        if not has_payment:
            self._payment_visible = False
        self._apply_payment_visibility()
