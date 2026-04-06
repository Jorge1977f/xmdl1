"""Detector avançado de status de notas fiscais com análise profunda de XML."""
from __future__ import annotations

import re
from typing import Optional, Tuple
from lxml import etree

from app.utils.logger import log


class AdvancedStatusDetector:
    """Detecta status de notas com análise profunda e heurísticas robustas."""

    CANCELAMENTO_KEYWORDS = {
        'cancelada', 'cancelado', 'cancelamento', 'canc.', 'canc',
        'cancelled', 'canceled', 'annulled',
    }

    CANCELAMENTO_CODES = {'2', 'C', '03', '03000', 'CANCELADA'}

    STATUS_ATTRIBUTES = [
        'Situacao', 'situacao', 'Status', 'status', 'StatusNfse',
        'SituacaoNfse', 'DescricaoSituacao', 'DescricaoStatus',
        'tpSit', 'cSit', 'Situ', 'situ'
    ]

    CANCELAMENTO_ELEMENTS = [
        'Cancelamento', 'NfseCancel', 'PedidoCancelamento',
        'ConfirmacaoCancelamento', 'CancelamentoPedido', 'NfseCancelada',
        'EvtCancNFe', 'procCancelamento', 'infCanc'
    ]

    @staticmethod
    def detect_status(xml_content: bytes) -> Tuple[str, float]:
        """
        Detecta o status de uma nota fiscal.

        Returns:
            Tupla (status, confiança)
        """
        try:
            root = etree.fromstring(xml_content)
        except Exception as exc:
            log.error(f"Erro ao parsear XML: {exc}")
            return 'VALIDO', 0.0

        strategies = [
            AdvancedStatusDetector._check_status_elements,
            AdvancedStatusDetector._check_cancelamento_elements,
            AdvancedStatusDetector._check_attributes,
            AdvancedStatusDetector._check_text_content,
            AdvancedStatusDetector._check_event_elements,
        ]

        results = []
        for strategy in strategies:
            status, confidence = strategy(root, xml_content)
            if status == 'CANCELADA' and confidence > 0.5:
                results.append((status, confidence))

        if results:
            avg_confidence = sum(c for _, c in results) / len(results)
            return 'CANCELADA', min(avg_confidence + 0.1, 1.0)

        return 'VALIDO', 0.8

    @staticmethod
    def _check_status_elements(root: etree._Element, xml_content: bytes) -> Tuple[str, float]:
        """Verifica elementos de status diretos."""
        try:
            for attr in AdvancedStatusDetector.STATUS_ATTRIBUTES:
                elements = root.xpath(f'//*[local-name()="{attr}"]')
                for elem in elements:
                    text = (elem.text or '').strip().upper()
                    if text:
                        if AdvancedStatusDetector._is_cancelamento_text(text):
                            return 'CANCELADA', 0.9
        except Exception as exc:
            log.debug(f"Erro ao verificar status elements: {exc}")

        return 'VALIDO', 0.0

    @staticmethod
    def _check_cancelamento_elements(root: etree._Element, xml_content: bytes) -> Tuple[str, float]:
        """Verifica presença de elementos de cancelamento."""
        try:
            for elem_name in AdvancedStatusDetector.CANCELAMENTO_ELEMENTS:
                elements = root.xpath(f'//*[local-name()="{elem_name}"]')
                if elements:
                    return 'CANCELADA', 0.95
        except Exception as exc:
            log.debug(f"Erro ao verificar cancelamento elements: {exc}")

        return 'VALIDO', 0.0

    @staticmethod
    def _check_attributes(root: etree._Element, xml_content: bytes) -> Tuple[str, float]:
        """Verifica atributos XML que indicam cancelamento."""
        try:
            for elem in root.iter():
                for attr_name, attr_value in elem.attrib.items():
                    attr_upper = attr_value.upper()
                    if AdvancedStatusDetector._is_cancelamento_text(attr_upper):
                        return 'CANCELADA', 0.85
        except Exception as exc:
            log.debug(f"Erro ao verificar attributes: {exc}")

        return 'VALIDO', 0.0

    @staticmethod
    def _check_text_content(root: etree._Element, xml_content: bytes) -> Tuple[str, float]:
        """Verifica conteúdo de texto do XML."""
        try:
            xml_text = etree.tostring(root, encoding='unicode', with_tail=False).upper()

            patterns = [
                r'<\w*SITUACAO[^>]*>CANCELADA</\w*SITUACAO>',
                r'<\w*STATUS[^>]*>CANCELADA</\w*STATUS>',
                r'NFSE\s+CANCELADA',
                r'NFS-E\s+CANCELADA',
                r'NOTA\s+FISCAL\s+CANCELADA',
                r'<\w*CANCELAMENTO[^>]*>',
            ]

            for pattern in patterns:
                if re.search(pattern, xml_text):
                    return 'CANCELADA', 0.8

        except Exception as exc:
            log.debug(f"Erro ao verificar text content: {exc}")

        return 'VALIDO', 0.0

    @staticmethod
    def _check_event_elements(root: etree._Element, xml_content: bytes) -> Tuple[str, float]:
        """Verifica elementos de evento que indicam cancelamento."""
        try:
            events = root.xpath('//*[local-name()="infEvento"]')
            for event in events:
                tipo_evento = event.xpath('.//*[local-name()="tpEvento"]')
                if tipo_evento:
                    evento_text = (tipo_evento[0].text or '').strip()
                    if evento_text in {'110111', '110110', '210111', '210110'}:
                        return 'CANCELADA', 0.95

            proc_status = root.xpath('//*[local-name()="cStat"]')
            for status_elem in proc_status:
                status_code = (status_elem.text or '').strip()
                if status_code in {'101', '135'}:
                    return 'CANCELADA', 0.9

        except Exception as exc:
            log.debug(f"Erro ao verificar event elements: {exc}")

        return 'VALIDO', 0.0

    @staticmethod
    def _is_cancelamento_text(text: str) -> bool:
        """Verifica se um texto indica cancelamento."""
        text_upper = text.upper().strip()

        for keyword in AdvancedStatusDetector.CANCELAMENTO_KEYWORDS:
            if keyword.upper() in text_upper:
                return True

        if text_upper in AdvancedStatusDetector.CANCELAMENTO_CODES:
            return True

        if re.search(r'CANC[A-Z]*', text_upper):
            return True

        return False
