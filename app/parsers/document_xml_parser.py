"""Parser genérico para NF-e e NFS-e."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any, Dict, Optional

from lxml import etree

from app.parsers.xml_parser_nfe import NFeParser
from app.utils.logger import log


class DocumentXMLParser:
    """Detecta e faz parse de NF-e ou NFS-e com heurísticas robustas."""

    @staticmethod
    def parse(xml_content: bytes) -> Optional[Dict[str, Any]]:
        try:
            root = etree.fromstring(xml_content)
        except Exception as exc:
            log.error(f"Erro ao abrir XML: {exc}")
            return None

        if DocumentXMLParser._looks_like_nfe(root):
            return NFeParser.parse(xml_content)
        return DocumentXMLParser._parse_nfse(root, xml_content)

    @staticmethod
    def _looks_like_nfe(root) -> bool:
        return bool(root.xpath('//*[local-name()="infNFe" or local-name()="NFe"]'))

    @staticmethod
    def _parse_nfse(root, xml_content: bytes) -> Optional[Dict[str, Any]]:
        emit_cnpj = DocumentXMLParser._find_text(
            root,
            [
                '//*[local-name()="emit"]/*[local-name()="CNPJ" or local-name()="Cnpj"]',
                '//*[contains(local-name(), "Prestador") or contains(local-name(), "Emit") or local-name()="IntermediarioServico"]/*[local-name()="CNPJ" or local-name()="Cnpj"]',
                '//*[local-name()="IdentificacaoPrestador"]//*[local-name()="CNPJ" or local-name()="Cnpj"]',
                '//*[local-name()="PrestadorServico"]//*[local-name()="CNPJ" or local-name()="Cnpj"]',
                '//*[local-name()="prest"]/*[local-name()="CNPJ" or local-name()="Cnpj"]',
            ],
        )
        emit_nome = DocumentXMLParser._find_text(
            root,
            [
                '//*[local-name()="emit"]/*[local-name()="xNome" or local-name()="RazaoSocial" or local-name()="NomeFantasia" or local-name()="Nome"]',
                '//*[contains(local-name(), "Prestador") or contains(local-name(), "Emit")]/*[local-name()="xNome" or local-name()="RazaoSocial" or local-name()="NomeFantasia" or local-name()="Nome"]',
                '//*[local-name()="PrestadorServico"]//*[local-name()="xNome" or local-name()="RazaoSocial" or local-name()="NomeFantasia" or local-name()="Nome"]',
                '//*[local-name()="prest"]/*[local-name()="xNome" or local-name()="RazaoSocial" or local-name()="NomeFantasia" or local-name()="Nome"]',
            ],
        )
        dest_cnpj = DocumentXMLParser._find_text(
            root,
            [
                '//*[local-name()="toma"]/*[local-name()="CNPJ" or local-name()="Cnpj" or local-name()="CPF" or local-name()="Cpf"]',
                '//*[contains(local-name(), "Tomador") or contains(local-name(), "Dest")]//*[local-name()="CNPJ" or local-name()="Cnpj" or local-name()="CPF" or local-name()="Cpf"]',
                '//*[local-name()="IdentificacaoTomador"]//*[local-name()="CNPJ" or local-name()="Cnpj" or local-name()="CPF" or local-name()="Cpf"]',
                '//*[local-name()="TomadorServico"]//*[local-name()="CpfCnpj"]//*[local-name()="CNPJ" or local-name()="Cnpj" or local-name()="CPF" or local-name()="Cpf"]',
            ],
        )
        dest_nome = DocumentXMLParser._find_text(
            root,
            [
                '//*[local-name()="toma"]/*[local-name()="xNome" or local-name()="RazaoSocial" or local-name()="Nome"]',
                '//*[contains(local-name(), "Tomador") or contains(local-name(), "Dest")]//*[local-name()="xNome" or local-name()="RazaoSocial" or local-name()="Nome"]',
                '//*[local-name()="TomadorServico"]//*[local-name()="xNome" or local-name()="RazaoSocial" or local-name()="Nome"]',
            ],
        )
        numero = DocumentXMLParser._find_text(
            root,
            [
                '//*[local-name()="Numero"]',
                '//*[local-name()="NumeroNfse"]',
                '//*[local-name()="nNFSe"]',
                '//*[local-name()="nDPS"]',
            ],
        )
        serie = DocumentXMLParser._find_text(root, ['//*[local-name()="Serie"]', '//*[local-name()="serie"]'])
        codigo_verificacao = DocumentXMLParser._find_text(
            root,
            [
                '//*[local-name()="CodigoVerificacao"]',
                '//*[local-name()="CodigoAutenticidade"]',
                '//*[local-name()="CodVerificacao"]',
                '//*[local-name()="cVerif"]',
            ],
        )
        data_emissao = DocumentXMLParser._parse_datetime(
            DocumentXMLParser._find_text(
                root,
                [
                    '//*[local-name()="DataEmissao"]',
                    '//*[local-name()="DataHoraEmissao"]',
                    '//*[local-name()="dhProc"]',
                    '//*[local-name()="dhEmi"]',
                    '//*[local-name()="Competencia"]',
                    '//*[local-name()="dCompet"]',
                    '//*[local-name()="dEmi"]',
                ],
            )
        )
        valor_total = DocumentXMLParser._parse_float(
            DocumentXMLParser._find_text(
                root,
                [
                    '//*[local-name()="vLiq"]',
                    '//*[local-name()="vNF"]',
                    '//*[local-name()="vBC"]',
                    '//*[local-name()="vServ"]',
                    '//*[local-name()="ValorServicos"]',
                    '//*[local-name()="ValorLiquidoNfse"]',
                    '//*[local-name()="ValorNfse"]',
                    '//*[local-name()="ValorTotal"]',
                ],
            )
        )

        chave = DocumentXMLParser._find_text(
            root,
            [
                '/*[local-name()="NFSe"]/*[local-name()="infNFSe"]/@Id',
                '//*[local-name()="infNFSe"]/@Id',
                '//*[local-name()="InfNfse"]/@Id',
                '//*[local-name()="chNFSe"]',
                '//*[local-name()="Id"]',
            ],
        )
        chave = DocumentXMLParser._normalize_nfse_key(chave) or DocumentXMLParser._build_nfse_key(
            numero=numero,
            codigo_verificacao=codigo_verificacao,
            emit_cnpj=emit_cnpj,
            dest_cnpj=dest_cnpj,
            data_emissao=data_emissao,
            valor_total=valor_total,
            xml_content=xml_content,
        )
        if not chave:
            log.warning('NFS-e ignorada por falta de chave sintética')
            return None

        situacao = DocumentXMLParser._detect_nfse_status(root)

        data = {
            'tipo': 'NFSE',
            'chave': chave,
            'numero': numero,
            'serie': serie,
            'modelo': 'NFSE',
            'data_emissao': data_emissao,
            'emitente': {'cnpj': DocumentXMLParser._only_digits(emit_cnpj), 'nome': emit_nome or ''},
            'destinatario': {'cnpj': DocumentXMLParser._only_digits(dest_cnpj), 'nome': dest_nome or ''},
            'valor_total': valor_total,
            'natureza': None,
            'cfop': None,
            'status': situacao,
        }
        log.info(f"NFS-e parseada com sucesso: {chave}")
        return data

    @staticmethod
    def _find_text(root, expressions: list[str]) -> Optional[str]:
        for expr in expressions:
            try:
                nodes = root.xpath(expr)
                for node in nodes:
                    text = ''.join(node.itertext()).strip() if hasattr(node, 'itertext') else str(node).strip()
                    if text:
                        return text
            except Exception:
                continue
        return None

    @staticmethod
    def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        value = value.strip().replace('Z', '+00:00')
        patterns = [
            '%Y-%m-%d', '%d/%m/%Y', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f',
            '%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M:%S'
        ]
        try:
            return datetime.fromisoformat(value).replace(tzinfo=None)
        except Exception:
            pass
        for pattern in patterns:
            try:
                return datetime.strptime(value, pattern)
            except Exception:
                continue
        return None

    @staticmethod
    def _parse_float(value: Optional[str]) -> float:
        if not value:
            return 0.0
        cleaned = re.sub(r'[^0-9,.-]', '', value.strip())
        if not cleaned:
            return 0.0

        if ',' in cleaned and '.' in cleaned:
            if cleaned.rfind(',') > cleaned.rfind('.'):
                cleaned = cleaned.replace('.', '').replace(',', '.')
            else:
                cleaned = cleaned.replace(',', '')
        elif ',' in cleaned:
            cleaned = cleaned.replace('.', '').replace(',', '.')

        try:
            return float(cleaned)
        except Exception:
            m = re.search(r'[-+]?[0-9]*\.?[0-9]+', cleaned)
            return float(m.group(0)) if m else 0.0

    @staticmethod
    def _only_digits(value: Optional[str]) -> str:
        return re.sub(r'\D+', '', value or '')

    @staticmethod
    def _normalize_nfse_key(value: Optional[str]) -> str:
        raw = (value or '').strip()
        if not raw:
            return ''
        normalized = re.sub(r'\s+', '', raw)
        if normalized.upper().startswith('NFS'):
            return normalized[:80]
        return normalized[:80]


    @staticmethod
    def _detect_nfse_status(root) -> str:
        """Tenta identificar se a NFS-e está cancelada a partir do XML.

        Como os layouts variam entre municípios e provedor nacional, a detecção usa
        heurísticas conservadoras. Se encontrar qualquer sinal forte de cancelamento,
        retorna CANCELADA; caso contrário, VALIDO.
        """
        status_text = DocumentXMLParser._find_text(
            root,
            [
                '//*[local-name()="Situacao"]',
                '//*[local-name()="Status"]',
                '//*[local-name()="status"]',
                '//*[local-name()="SituacaoNfse"]',
                '//*[local-name()="StatusNfse"]',
                '//*[local-name()="DescricaoSituacao"]',
                '//*[local-name()="DescricaoStatus"]',
            ],
        )
        status_norm = (status_text or '').strip().upper()
        if status_norm:
            if any(token in status_norm for token in ('CANCEL', 'CANC.', 'CANCELADA', 'CANCELADO', 'CANCELAMENTO')):
                return 'CANCELADA'
            if status_norm in {'2', 'C'}:
                return 'CANCELADA'

        cancel_markers = [
            '//*[contains(local-name(), "Cancelamento")]',
            '//*[contains(local-name(), "NfseCancel")]',
            '//*[contains(local-name(), "PedidoCancelamento")]',
            '//*[contains(local-name(), "ConfirmacaoCancelamento")]',
            '//*[@Situacao="Cancelada" or @situacao="cancelada" or @Status="Cancelada" or @status="cancelada"]',
        ]
        for expr in cancel_markers:
            try:
                if root.xpath(expr):
                    return 'CANCELADA'
            except Exception:
                continue

        try:
            xml_text = etree.tostring(root, encoding='unicode', with_tail=False)
        except Exception:
            xml_text = ''
        xml_upper = xml_text.upper()
        if any(token in xml_upper for token in (
            'NFSE CANCELADA',
            'NFS-E CANCELADA',
            'CANCELAMENTO',
            'SITUACAO>CANCELADA<',
            'STATUS>CANCELADA<',
        )):
            return 'CANCELADA'

        return 'VALIDO'

    @staticmethod
    def _build_nfse_key(
        numero: Optional[str],
        codigo_verificacao: Optional[str],
        emit_cnpj: Optional[str],
        dest_cnpj: Optional[str],
        data_emissao: Optional[datetime],
        valor_total: float,
        xml_content: bytes,
    ) -> str:
        base = '|'.join([
            numero or '',
            codigo_verificacao or '',
            DocumentXMLParser._only_digits(emit_cnpj),
            DocumentXMLParser._only_digits(dest_cnpj),
            data_emissao.strftime('%Y%m%d%H%M%S') if data_emissao else '',
            f'{valor_total:.2f}',
        ])
        if not base.strip('|'):
            base = hashlib.sha1(xml_content).hexdigest()
        return ('NFSE' + hashlib.sha1(base.encode('utf-8')).hexdigest().upper())[:44]
