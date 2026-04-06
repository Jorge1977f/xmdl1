"""
Parser de NF-e (Nota Fiscal Eletrônica)
"""
from typing import Optional, Dict, Any
from lxml import etree
from datetime import datetime
from app.utils.logger import log


class NFeParser:
    """Parser para arquivos XML de NF-e"""

    NAMESPACES = {
        'nfe': 'http://www.portalfiscal.inf.br/nfe',
    }

    @staticmethod
    def parse(xml_content: bytes) -> Optional[Dict[str, Any]]:
        """
        Faz parse de XML de NF-e.
        """
        try:
            root = etree.fromstring(xml_content)
            nfe_data = {
                'tipo': 'NFE',
                'chave': NFeParser._extract_chave(root),
                'numero': NFeParser._extract_numero(root),
                'serie': NFeParser._extract_serie(root),
                'modelo': NFeParser._extract_modelo(root),
                'data_emissao': NFeParser._extract_data_emissao(root),
                'emitente': NFeParser._extract_emitente(root),
                'destinatario': NFeParser._extract_destinatario(root),
                'valor_total': NFeParser._extract_valor_total(root),
                'natureza': NFeParser._extract_natureza(root),
                'cfop': NFeParser._extract_cfop(root),
                'status': 'VALIDO',
            }
            log.info(f"NF-e parseada com sucesso: {nfe_data['chave']}")
            return nfe_data
        except Exception as e:
            log.error(f"Erro ao fazer parse de NF-e: {str(e)}")
            return None

    @staticmethod
    def _extract_chave(root) -> Optional[str]:
        try:
            infnfe = root.find('.//nfe:infNFe', NFeParser.NAMESPACES)
            if infnfe is not None:
                return infnfe.get('Id', '').replace('NFe', '')
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_numero(root) -> Optional[str]:
        try:
            ide = root.find('.//nfe:ide', NFeParser.NAMESPACES)
            if ide is not None:
                nNF = ide.find('nfe:nNF', NFeParser.NAMESPACES)
                if nNF is not None:
                    return nNF.text
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_serie(root) -> Optional[str]:
        try:
            ide = root.find('.//nfe:ide', NFeParser.NAMESPACES)
            if ide is not None:
                serie = ide.find('nfe:serie', NFeParser.NAMESPACES)
                if serie is not None:
                    return serie.text
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_modelo(root) -> Optional[str]:
        try:
            ide = root.find('.//nfe:ide', NFeParser.NAMESPACES)
            if ide is not None:
                mod = ide.find('nfe:mod', NFeParser.NAMESPACES)
                if mod is not None:
                    return mod.text
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_data_emissao(root) -> Optional[datetime]:
        try:
            ide = root.find('.//nfe:ide', NFeParser.NAMESPACES)
            if ide is not None:
                dhEmi = ide.find('nfe:dhEmi', NFeParser.NAMESPACES)
                if dhEmi is not None and dhEmi.text:
                    value = dhEmi.text.replace('Z', '+00:00')
                    return datetime.fromisoformat(value).replace(tzinfo=None)
                dEmi = ide.find('nfe:dEmi', NFeParser.NAMESPACES)
                if dEmi is not None and dEmi.text:
                    return datetime.strptime(dEmi.text, '%Y-%m-%d')
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_emitente(root) -> Dict[str, str]:
        emitente = {'cnpj': '', 'nome': ''}
        try:
            emit = root.find('.//nfe:emit', NFeParser.NAMESPACES)
            if emit is not None:
                cnpj_elem = emit.find('nfe:CNPJ', NFeParser.NAMESPACES)
                if cnpj_elem is not None:
                    emitente['cnpj'] = cnpj_elem.text
                xNome = emit.find('nfe:xNome', NFeParser.NAMESPACES)
                if xNome is not None:
                    emitente['nome'] = xNome.text
        except Exception:
            pass
        return emitente

    @staticmethod
    def _extract_destinatario(root) -> Dict[str, str]:
        destinatario = {'cnpj': '', 'nome': ''}
        try:
            dest = root.find('.//nfe:dest', NFeParser.NAMESPACES)
            if dest is not None:
                cnpj_elem = dest.find('nfe:CNPJ', NFeParser.NAMESPACES)
                if cnpj_elem is not None:
                    destinatario['cnpj'] = cnpj_elem.text
                xNome = dest.find('nfe:xNome', NFeParser.NAMESPACES)
                if xNome is not None:
                    destinatario['nome'] = xNome.text
        except Exception:
            pass
        return destinatario

    @staticmethod
    def _extract_valor_total(root) -> float:
        try:
            total = root.find('.//nfe:total', NFeParser.NAMESPACES)
            if total is not None:
                ICMSTot = total.find('nfe:ICMSTot', NFeParser.NAMESPACES)
                if ICMSTot is not None:
                    vNF = ICMSTot.find('nfe:vNF', NFeParser.NAMESPACES)
                    if vNF is not None and vNF.text:
                        return float(vNF.text)
        except Exception:
            pass
        return 0.0

    @staticmethod
    def _extract_natureza(root) -> Optional[str]:
        try:
            ide = root.find('.//nfe:ide', NFeParser.NAMESPACES)
            if ide is not None:
                natOp = ide.find('nfe:natOp', NFeParser.NAMESPACES)
                if natOp is not None:
                    return natOp.text
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_cfop(root) -> Optional[str]:
        try:
            det = root.find('.//nfe:det', NFeParser.NAMESPACES)
            if det is not None:
                prod = det.find('nfe:prod', NFeParser.NAMESPACES)
                if prod is not None:
                    cfop = prod.find('nfe:CFOP', NFeParser.NAMESPACES)
                    if cfop is not None:
                        return cfop.text
        except Exception:
            pass
        return None
