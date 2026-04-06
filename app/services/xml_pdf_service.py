"""Geração de PDF para visualização de XML com layout fiscal mais próximo do DANFSe."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
import json
import re
import threading


from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, Image

from app.parsers import DocumentXMLParser
from app.utils.logger import log
from config.settings import CACHE_DIR, MUNICIPIOS_IBGE_FILE


class XMLPDFService:
    """Gera um PDF mais próximo do DANFSe Padrão Nacional para visualização do XML."""

    _RENDER_VERSION = "20260404_v5"
    _MUNICIPIO_CACHE_PATH = Path(CACHE_DIR) / "municipios_cache.json"
    _MUNICIPIOS_IBGE_PATH = Path(MUNICIPIOS_IBGE_FILE)
    _MUNICIPIO_CACHE_LOCK = threading.Lock()
    _MUNICIPIOS_IBGE_DATA: dict[str, str] | None = None
    _UF_BY_IBGE_PREFIX = {
        '11': 'RO', '12': 'AC', '13': 'AM', '14': 'RR', '15': 'PA', '16': 'AP', '17': 'TO',
        '21': 'MA', '22': 'PI', '23': 'CE', '24': 'RN', '25': 'PB', '26': 'PE', '27': 'AL', '28': 'SE', '29': 'BA',
        '31': 'MG', '32': 'ES', '33': 'RJ', '35': 'SP',
        '41': 'PR', '42': 'SC', '43': 'RS',
        '50': 'MS', '51': 'MT', '52': 'GO', '53': 'DF',
    }
    _MUNICIPIO_OVERRIDES = {
        '4115200': {'municipio': 'Maringá', 'uf': 'PR'},
        '4210506': {'municipio': 'Maravilha', 'uf': 'SC'},
    }

    @staticmethod
    def ensure_pdf(xml_path: str | Path) -> Path | None:
        path = Path(xml_path)
        if not path.exists():
            return None

        pdf_path = path.with_suffix('.pdf')
        meta_path = pdf_path.with_suffix('.pdf.meta.json')
        try:
            if pdf_path.exists() and pdf_path.stat().st_mtime >= path.stat().st_mtime:
                if meta_path.exists():
                    meta = json.loads(meta_path.read_text(encoding='utf-8'))
                    if meta.get('render_version') == XMLPDFService._RENDER_VERSION:
                        return pdf_path
                else:
                    return pdf_path
        except Exception:
            pass

        try:
            xml_bytes = path.read_bytes()
            data = DocumentXMLParser.parse(xml_bytes) or {}
            try:
                extra = XMLPDFService._extract_extra_fields_from_bytes(xml_bytes)
            except Exception as extract_exc:
                log.warning(f"Falha ao extrair campos extras do XML {path}: {extract_exc}")
                extra = {}
            XMLPDFService._render_pdf(pdf_path, data, extra)
            try:
                meta_path.write_text(json.dumps({'render_version': XMLPDFService._RENDER_VERSION}, ensure_ascii=False), encoding='utf-8')
            except Exception:
                pass
            return pdf_path if pdf_path.exists() else None
        except Exception as exc:
            log.exception(f"Falha ao gerar PDF do XML {path}: {exc}")
            return None

    @staticmethod
    def _extract_extra_fields(xml_path: Path) -> dict[str, Any]:
        return XMLPDFService._extract_extra_fields_from_bytes(xml_path.read_bytes())

    @staticmethod
    def _extract_extra_fields_from_bytes(xml_bytes: bytes) -> dict[str, Any]:
        root = ET.fromstring(xml_bytes)

        def normalize(tag: str) -> str:
            return tag.split('}', 1)[-1].lower()

        def find_text(local_names: list[str]) -> str:
            lowered = {name.lower() for name in local_names}
            for elem in root.iter():
                if normalize(elem.tag) in lowered and (elem.text or '').strip():
                    return (elem.text or '').strip()
            return ''

        def find_texts(local_names: list[str]) -> list[str]:
            lowered = {name.lower() for name in local_names}
            values: list[str] = []
            for elem in root.iter():
                if normalize(elem.tag) in lowered and (elem.text or '').strip():
                    value = (elem.text or '').strip()
                    if value not in values:
                        values.append(value)
            return values

        def child_text(block: ET.Element | None, child_names: list[str]) -> str:
            if block is None:
                return ''
            lowered = {name.lower() for name in child_names}
            for child in block.iter():
                if child is block:
                    continue
                if normalize(child.tag) in lowered and (child.text or '').strip():
                    return (child.text or '').strip()
            return ''

        def child_text_like(block: ET.Element | None, fragments: list[str]) -> str:
            if block is None:
                return ''
            lowered = [fragment.lower() for fragment in fragments]
            for child in block.iter():
                if child is block:
                    continue
                tag = normalize(child.tag)
                if any(fragment in tag for fragment in lowered) and (child.text or '').strip():
                    return (child.text or '').strip()
            return ''

        def find_best_block(block_names: list[str], detail_names: list[str] | None = None) -> ET.Element | None:
            lowered = [name.lower() for name in block_names]
            candidates: list[tuple[int, ET.Element]] = []
            for elem in root.iter():
                tag = normalize(elem.tag)
                exact_index = None
                partial_index = None
                if tag in lowered:
                    exact_index = lowered.index(tag)
                else:
                    for idx, name in enumerate(lowered):
                        if name in tag:
                            partial_index = idx
                            break
                if exact_index is None and partial_index is None:
                    continue
                idx = exact_index if exact_index is not None else partial_index
                score = 100 - (idx or 0)
                if exact_index is not None:
                    score += 40
                documento = child_text(elem, ['CNPJ', 'Cnpj', 'CPF', 'Cpf']) or child_text_like(elem, ['cnpj', 'cpf'])
                nome = child_text(elem, ['xNome', 'RazaoSocial', 'Nome']) or child_text_like(elem, ['razaosocial', 'nome'])
                endereco = child_text(elem, ['xLgr', 'Endereco', 'Logradouro']) or child_text_like(elem, ['logradouro', 'endereco'])
                cidade = child_text(elem, ['xMun', 'Municipio', 'Cidade', 'NomeMunicipio', 'xCidade']) or child_text_like(elem, ['municip', 'cidade', 'xmun'])
                cep = child_text(elem, ['CEP', 'Cep']) or child_text_like(elem, ['cep'])
                uf = child_text(elem, ['UF', 'Uf', 'xUF']) or child_text_like(elem, ['uf'])
                if documento:
                    score += 20
                if nome:
                    score += 20
                if endereco:
                    score += 45
                if cidade:
                    score += 45
                if cep:
                    score += 18
                if uf:
                    score += 8
                if detail_names:
                    for detail in detail_names:
                        if child_text(elem, [detail]) or child_text_like(elem, [detail]):
                            score += 5
                candidates.append((score, elem))
            if not candidates:
                return None
            candidates.sort(key=lambda item: item[0], reverse=True)
            return candidates[0][1]

        def compose_address(block: ET.Element | None) -> str:
            if block is None:
                return ''
            street = child_text(block, ['xLgr', 'Endereco', 'Logradouro']) or child_text_like(block, ['logradouro', 'endereco'])
            number = child_text(block, ['nro', 'Numero']) or child_text_like(block, ['numero'])
            complement = child_text(block, ['xCpl', 'Complemento']) or child_text_like(block, ['complement'])
            district = child_text(block, ['xBairro', 'Bairro']) or child_text_like(block, ['bairro'])
            parts = [street]
            if number:
                parts.append(number)
            if complement:
                parts.append(complement)
            if district:
                parts.append(district)
            return ', '.join([p for p in parts if p])

        def find_first_block(block_names: list[str]) -> ET.Element | None:
            """Encontra o primeiro bloco que corresponde a um dos nomes fornecidos."""
            lowered = [name.lower() for name in block_names]
            for elem in root.iter():
                tag = normalize(elem.tag)
                if tag in lowered:
                    return elem
                for name in lowered:
                    if name in tag:
                        return elem
            return None

        def compose_city(block: ET.Element | None) -> str:
            if block is None:
                return ''
            city = (
                child_text(block, ['xMun', 'Municipio', 'Cidade', 'CidadeTomador', 'NomeMunicipio', 'xCidade', 'xMunGer'])
                or child_text_like(block, ['municipio', 'cidade', 'xmun'])
            )
            uf = child_text(block, ['UF', 'Uf', 'xUF']) or child_text_like(block, ['uf'])
            if city and uf:
                return f'{city} - {uf}'
            return city or ''

        prestador_block = find_best_block(
            ['PrestadorServico', 'prest', 'Prestador', 'DadosPrestador', 'emit', 'IdentificacaoPrestador', 'EnderecoEmitente', 'DadosEnderecoPrestador'],
            ['CNPJ', 'CPF', 'RazaoSocial', 'Nome', 'xLgr', 'Endereco', 'Municipio', 'Cidade', 'CEP', 'xMun', 'xMunGer', 'NomeMunicipio'],
        )
        tomador_block = find_best_block(
            ['TomadorServico', 'toma', 'Tomador', 'DadosTomador', 'dest', 'Destinatario', 'IdentificacaoTomador', 'EnderecoTomador', 'DadosEnderecoPrestador'],
            ['CNPJ', 'CPF', 'RazaoSocial', 'Nome', 'xLgr', 'Endereco', 'Municipio', 'Cidade', 'CEP', 'xMun', 'xMunGer', 'NomeMunicipio'],
        )
        valores_block = find_first_block(['valores', 'Valores', 'valoresnfse', 'ValoresNfse'])
        servico_block = find_first_block(['serv', 'Servico', 'dadosservico', 'DadosServico'])

        valor_servico = child_text(valores_block, ['vServ', 'ValorServicos', 'ValorServico']) or find_text(['vServ', 'ValorServicos'])
        valor_liquido = child_text(valores_block, ['vLiq', 'ValorLiquidoNfse', 'ValorLiquido']) or find_text(['vLiq', 'ValorLiquidoNfse'])
        base_calculo = child_text(valores_block, ['vBC', 'BaseCalculo', 'ValorBaseCalculo']) or find_text(['vBC', 'BaseCalculo'])
        aliquota = child_text(valores_block, ['pAliqAplic', 'Aliquota', 'AliquotaAplicada']) or find_text(['pAliqAplic', 'Aliquota'])
        issqn = child_text(valores_block, ['vISSQN', 'ValorIss', 'ValorIssqn']) or find_text(['vISSQN', 'ValorIss'])

        info = {
            'cabecalho': {
                'municipio_emissor': compose_city(prestador_block) or find_text(['xLocEmi', 'MunicipioGerador', 'xMun']),
                'telefone_municipio': child_text(prestador_block, ['fone', 'Telefone']) or find_text(['fone', 'Telefone']),
                'email_municipio': child_text(prestador_block, ['email', 'Email']) or find_text(['email', 'Email']),
                'competencia': find_text(['dCompet', 'Competencia']) or find_text(['DataEmissao', 'dhEmi']),
                'numero_dps': find_text(['nDPS', 'NumeroDps']),
                'serie_dps': find_text(['serie', 'Serie']),
                'data_emissao_nfse': find_text(['dhEmi', 'DataHoraEmissao', 'DataEmissao']),
                'data_emissao_dps': find_text(['dhEmi', 'DataHoraEmissaoDps', 'dhGer']),
                'codigo_verificacao': find_text(['CodigoVerificacao', 'cVerif', 'CodigoAutenticidade']),
                'municipio_tomador': compose_city(tomador_block) or child_text(tomador_block, ['xMun', 'Municipio', 'Cidade', 'xMunGer', 'NomeMunicipio', 'xMun']) or '',
                'uf_tomador': child_text(tomador_block, ['UF', 'Uf', 'xUF', 'uf']) or child_text_like(tomador_block, ['uf']) or '',
            },
            'prestador': {
                'documento': child_text(prestador_block, ['CNPJ', 'Cnpj', 'CPF', 'Cpf']) or find_texts(['CNPJ', 'CPF'])[0] if find_texts(['CNPJ', 'CPF']) else '',
                'inscricao_municipal': child_text(prestador_block, ['IM', 'InscricaoMunicipal']) or find_text(['IM', 'InscricaoMunicipal']),
                'telefone': child_text(prestador_block, ['fone', 'Telefone']) or find_text(['fone', 'Telefone']),
                'nome': child_text(prestador_block, ['xNome', 'RazaoSocial', 'Nome']) or find_text(['xNome', 'RazaoSocial', 'Nome']),
                'email': child_text(prestador_block, ['email', 'Email']) or find_text(['email', 'Email']),
                'endereco': compose_address(prestador_block),
                'municipio': compose_city(prestador_block) or XMLPDFService._join_nonempty([find_text(['xLocEmi']), child_text(prestador_block, ['UF'])], ' - '),
                'cep': child_text(prestador_block, ['CEP', 'Cep']),
                'simples_nacional': find_text(['opSimpNac', 'SimplesNacional', 'OptanteSimplesNacional']),
                'regime_sn': find_text(['regApTribSN', 'RegimeApuracaoTributariaSN']),
                'regime_especial': find_text(['regEspTrib', 'RegimeEspecialTributacao']),
            },
            'tomador': {
                'documento': child_text(tomador_block, ['CNPJ', 'Cnpj', 'CPF', 'Cpf']) or (find_texts(['CNPJ', 'CPF'])[1] if len(find_texts(['CNPJ', 'CPF'])) > 1 else ''),
                'inscricao_municipal': child_text(tomador_block, ['IM', 'InscricaoMunicipal']),
                'telefone': child_text(tomador_block, ['fone', 'Telefone']),
                'nome': child_text(tomador_block, ['xNome', 'RazaoSocial', 'Nome']),
                'email': child_text(tomador_block, ['email', 'Email']),
                'endereco': compose_address(tomador_block),
                'municipio': compose_city(tomador_block) or XMLPDFService._join_nonempty([child_text(tomador_block, ['xMun', 'Municipio', 'Cidade', 'xMunGer', 'NomeMunicipio']), child_text(tomador_block, ['UF', 'Uf', 'xUF', 'uf'])], ' - '),
                'uf': child_text(tomador_block, ['UF', 'Uf', 'xUF', 'uf']) or child_text_like(tomador_block, ['uf']),
                'codigo_municipio': child_text(tomador_block, ['cMun', 'CodigoMunicipio']) or child_text_like(tomador_block, ['cmun']),
                'cep': child_text(tomador_block, ['CEP', 'Cep']),
            },
            'servico': {
                'codigo_tributacao_nacional': child_text(servico_block, ['cTribNac', 'CodigoTributacaoNacional']) or find_text(['cTribNac', 'CodigoTributacaoNacional']),
                'descricao_tributacao_nacional': child_text(servico_block, ['xTribNac', 'DescricaoTributacaoNacional']) or find_text(['xTribNac', 'DescricaoTributacaoNacional']),
                'codigo_tributacao_municipal': child_text(servico_block, ['cTribMun', 'CodigoTributacaoMunicipal']) or find_text(['cTribMun', 'CodigoTributacaoMunicipal']),
                'local_prestacao': child_text(servico_block, ['xLocPrestacao', 'LocalPrestacao', 'xLocIncid']) or find_text(['xLocPrestacao', 'LocalPrestacao', 'xLocIncid']),
                'codigo_local_prestacao': child_text(servico_block, ['cLocPrestacao', 'cLocIncid', 'CodigoMunicipioPrestacao']) or find_text(['cLocPrestacao', 'cLocIncid', 'CodigoMunicipioPrestacao']),
                'pais_prestacao': child_text(servico_block, ['xPais', 'PaisPrestacao']) or find_text(['xPais', 'PaisPrestacao']),
                'descricao_servico': child_text(servico_block, ['xDescServ', 'Discriminacao', 'DiscriminacaoServico']) or find_text(['xDescServ', 'Discriminacao', 'DiscriminacaoServico']),
            },
            'tributacao_municipal': {
                'tributacao_issqn': find_text(['tribISSQN', 'TributacaoIssqn']),
                'pais_resultado_prestacao': find_text(['xPaisResultado', 'PaisResultadoPrestacao']),
                'local_incidencia': find_text(['xLocIncid', 'MunicipioIncidenciaIssqn', 'xLocPrestacao']),
                'codigo_local_incidencia': find_text(['cLocIncid', 'cLocPrestacao', 'CodigoMunicipioIncidenciaIssqn']),
                'tipo_imunidade': find_text(['tpImunidade', 'TipoImunidade']),
                'suspensao_issqn': find_text(['suspExigISSQN', 'SuspensaoExigibilidadeIssqn']),
                'processo_suspensao': find_text(['nProcessoSuspensao', 'NumeroProcessoSuspensao']),
                'beneficio_municipal': find_text(['beneficioMunicipal', 'BeneficioMunicipal']),
                'valor_servico': valor_servico,
                'desconto_incondicionado': find_text(['vDescIncond', 'DescontoIncondicionado']),
                'deducoes': find_text(['vDeducao', 'TotalDeducoesReducoes']),
                'base_calculo': base_calculo,
                'aliquota_aplicada': aliquota,
                'retencao_issqn': find_text(['tpRetISSQN', 'RetencaoIssqn']),
                'issqn_apurado': issqn,
                'operacao_tributavel': find_text(['opTributavel', 'OperacaoTributavel']),
                'regime_especial': find_text(['regEspTrib', 'RegimeEspecialTributacao']),
                'calculo_bm': find_text(['calcBM', 'CalculoBM']),
            },
            'tributacao_federal': {
                'irrf': find_text(['vIRRF', 'ValorIRRF']),
                'contribuicao_previdenciaria': find_text(['vINSS', 'ValorINSS']),
                'pis': find_text(['vPIS', 'ValorPIS']),
                'cofins': find_text(['vCOFINS', 'ValorCOFINS']),
                'csll': find_text(['vCSLL', 'ValorCSLL']),
                'descricao_contribuicoes': find_text(['xObsRet', 'DescricaoContribuicoesRetidas']),
                'desconto_incondicionado': find_text(['vDescIncond', 'DescontoIncondicionado']),
                'issqn_retido': find_text(['vISSRet', 'ValorIssRetido']),
            },
            'valor_total': {
                'valor_servico': valor_servico,
                'desconto_condicionado': find_text(['vDescCond', 'DescontoCondicionado']),
                'total_retencoes_federais': find_text(['vTotRetFed', 'TotalRetencoesFederais']),
                'pis_cofins_proprio': find_text(['vPisCofins', 'PisCofinsDebitoApuracaoPropria']),
                'valor_liquido': valor_liquido or valor_servico,
            },
            'totais_tributos': {
                'federais': find_text(['vTotTribFed', 'ValorTotalTributosFederais']),
                'estaduais': find_text(['vTotTribEst', 'ValorTotalTributosEstaduais']),
                'municipais': find_text(['vTotTribMun', 'ValorTotalTributosMunicipais']),
            },
            'informacoes_complementares': find_text(['xInfComp', 'InformacoesComplementares', 'xObsComp', 'Observacao']),
        }
        return info

    @staticmethod
    def _render_pdf(pdf_path: Path, data: dict[str, Any], extra: dict[str, Any]) -> None:
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        margin_mm = 5
        doc = SimpleDocTemplate(
            str(pdf_path),
            pagesize=A4,
            leftMargin=margin_mm * mm,
            rightMargin=margin_mm * mm,
            topMargin=margin_mm * mm,
            bottomMargin=margin_mm * mm,
        )
        styles = XMLPDFService._styles()
        story: list[Any] = []

        tipo = (data.get('tipo') or '').upper()
        extra = dict(extra or {})
        extra['_page_inner_width'] = A4[0] - (2 * margin_mm * mm)
        if tipo == 'NFSE':
            XMLPDFService._build_nfse_story(story, styles, data, extra)
            doc.build(story, onFirstPage=XMLPDFService._draw_nfse_border, onLaterPages=XMLPDFService._draw_nfse_border)
        else:
            XMLPDFService._build_nfe_story(story, styles, data, extra)
            doc.build(story)

    @staticmethod
    def _draw_nfse_border(canvas, doc):
        canvas.saveState()
        canvas.setLineWidth(0.8)
        canvas.rect(2.5 * mm, 2.5 * mm, A4[0] - 5 * mm, A4[1] - 5 * mm)
        canvas.restoreState()

    @classmethod
    def _load_municipio_cache(cls) -> dict[str, dict[str, str]]:
        with cls._MUNICIPIO_CACHE_LOCK:
            try:
                if cls._MUNICIPIO_CACHE_PATH.exists():
                    return json.loads(cls._MUNICIPIO_CACHE_PATH.read_text(encoding='utf-8'))
            except Exception:
                pass
        return {}

    @classmethod
    def _save_municipio_cache(cls, cache: dict[str, dict[str, str]]) -> None:
        with cls._MUNICIPIO_CACHE_LOCK:
            try:
                cls._MUNICIPIO_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
                cls._MUNICIPIO_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding='utf-8')
            except Exception:
                pass

    @classmethod
    def _load_municipios_ibge_data(cls) -> dict[str, str]:
        cached = cls._MUNICIPIOS_IBGE_DATA
        if cached is not None:
            return cached
        data: dict[str, str] = {}
        try:
            if cls._MUNICIPIOS_IBGE_PATH.exists():
                loaded = json.loads(cls._MUNICIPIOS_IBGE_PATH.read_text(encoding='utf-8'))
                if isinstance(loaded, dict):
                    data = {cls._only_digits(k)[:7]: str(v).strip() for k, v in loaded.items() if cls._only_digits(k)[:7] and str(v).strip()}
        except Exception as exc:
            log.warning(f"Falha ao carregar lista interna de municípios IBGE: {exc}")
        cls._MUNICIPIOS_IBGE_DATA = data
        return data

    @staticmethod
    def _only_digits(value: Any) -> str:
        return re.sub(r'\D+', '', str(value or ''))

    @classmethod
    def _uf_from_ibge_code(cls, code: Any) -> str:
        digits = cls._only_digits(code)[:7]
        if len(digits) < 2:
            return ''
        return cls._UF_BY_IBGE_PREFIX.get(digits[:2], '')

    @classmethod
    def _resolve_city_by_ibge_code(cls, code: Any) -> dict[str, str]:
        digits = cls._only_digits(code)[:7]
        if len(digits) != 7:
            return {'municipio': '', 'uf': ''}

        cache = cls._load_municipio_cache()
        if digits in cache:
            return cache[digits]
        if digits in cls._MUNICIPIO_OVERRIDES:
            cache[digits] = cls._MUNICIPIO_OVERRIDES[digits]
            cls._save_municipio_cache(cache)
            return cache[digits]

        municipios = cls._load_municipios_ibge_data()
        municipio = municipios.get(digits, '')
        result = {'municipio': municipio, 'uf': cls._uf_from_ibge_code(digits)}
        if municipio:
            cache[digits] = result
            cls._save_municipio_cache(cache)
        return result

    @classmethod
    def _resolve_city_by_cep(cls, cep: Any) -> dict[str, str]:
        # Mantido apenas como fallback local. Não faz consulta externa para não deixar a geração do PDF lenta.
        digits = cls._only_digits(cep)[:8]
        if len(digits) != 8:
            return {'municipio': '', 'uf': ''}
        cache_key = f'cep:{digits}'
        cache = cls._load_municipio_cache()
        return cache.get(cache_key, {'municipio': '', 'uf': ''})

    @classmethod
    def _resolve_municipio_text(cls, municipio: Any = '', uf: Any = '', codigo_ibge: Any = '', cep: Any = '') -> str:
        municipio_text = str(municipio or '').strip()
        uf_text = str(uf or '').strip()

        # Quando vier o código IBGE, ele manda. Evita cair em bairro/complemento ou no município da prestação.
        resolved = cls._resolve_city_by_ibge_code(codigo_ibge)
        if resolved.get('municipio'):
            return cls._compose_city_from_parts(resolved.get('municipio'), resolved.get('uf') or uf_text)

        # Só aceita município em texto quando ele realmente parece nome de cidade.
        if municipio_text and not cls._only_digits(municipio_text):
            lowered = municipio_text.lower()
            invalid_tokens = ['bairro', 'zona', 'quadra', 'lote', 'casa', 'apto', 'apartamento']
            if not any(token in lowered for token in invalid_tokens):
                return cls._compose_city_from_parts(municipio_text, uf_text)

        resolved = cls._resolve_city_by_cep(cep)
        if resolved.get('municipio'):
            return cls._compose_city_from_parts(resolved.get('municipio'), resolved.get('uf') or uf_text)

        return cls._compose_city_from_parts('', uf_text)

    @staticmethod
    def _styles() -> dict[str, ParagraphStyle]:
        base = getSampleStyleSheet()
        styles = {
            'title': ParagraphStyle(
                'title',
                parent=base['Title'],
                fontName='Helvetica-Bold',
                fontSize=12,
                leading=14,
                alignment=TA_CENTER,
                textColor=colors.black,
                spaceAfter=2,
            ),
            'subtitle': ParagraphStyle(
                'subtitle',
                parent=base['Normal'],
                fontName='Helvetica',
                fontSize=9,
                leading=11,
                alignment=TA_CENTER,
                textColor=colors.black,
            ),
            'label': ParagraphStyle(
                'label',
                parent=base['Normal'],
                fontName='Helvetica-Bold',
                fontSize=7,
                leading=8,
                textColor=colors.black,
            ),
            'value': ParagraphStyle(
                'value',
                parent=base['Normal'],
                fontName='Helvetica',
                fontSize=8,
                leading=10,
                textColor=colors.black,
            ),
            'value_bold': ParagraphStyle(
                'value_bold',
                parent=base['Normal'],
                fontName='Helvetica-Bold',
                fontSize=8,
                leading=10,
                textColor=colors.black,
            ),
            'value_compact': ParagraphStyle(
                'value_compact',
                parent=base['Normal'],
                fontName='Helvetica',
                fontSize=7,
                leading=8,
                textColor=colors.black,
            ),
            'value_micro': ParagraphStyle(
                'value_micro',
                parent=base['Normal'],
                fontName='Helvetica',
                fontSize=6.8,
                leading=7.4,
                textColor=colors.black,
            ),
            'small_center': ParagraphStyle(
                'small_center',
                parent=base['Normal'],
                fontName='Helvetica',
                fontSize=6,
                leading=7,
                textColor=colors.black,
                alignment=TA_CENTER,
            ),
            'small_qr': ParagraphStyle(
                'small_qr',
                parent=base['Normal'],
                fontName='Helvetica',
                fontSize=5.5,
                leading=6.4,
                textColor=colors.black,
                alignment=TA_JUSTIFY,
            ),
            'section_center': ParagraphStyle(
                'section_center',
                parent=base['Normal'],
                fontName='Helvetica-Bold',
                fontSize=8,
                leading=9,
                textColor=colors.black,
                alignment=TA_CENTER,
                spaceBefore=1,
                spaceAfter=1,
            ),
            'section': ParagraphStyle(
                'section',
                parent=base['Normal'],
                fontName='Helvetica-Bold',
                fontSize=8,
                leading=10,
                textColor=colors.black,
                alignment=TA_LEFT,
                spaceBefore=2,
                spaceAfter=2,
            ),
        }
        return styles

    @staticmethod
    def _truncate_words(text: Any, max_chars: int = 80, max_lines: int = 1) -> str:
        raw = XMLPDFService._safe_text(text)
        if not raw or raw == '-':
            return '-'
        compact = ' '.join(raw.split())
        
        # Se cabe em uma linha, retornar
        if len(compact) <= max_chars and max_lines >= 1:
            return compact
        
        # Para múltiplas linhas, dividir respeitando max_lines
        if max_lines > 1:
            lines = []
            current_line = ''
            words = compact.split()
            
            for word in words:
                # Se adicionar a palavra excede o limite de caracteres
                if len(current_line) + len(word) + 1 > max_chars:
                    # Se já atingiu o limite de linhas, parar
                    if len(lines) >= max_lines - 1:
                        # Adicionar a linha atual e parar
                        if current_line:
                            lines.append(current_line)
                        break
                    # Senão, começar nova linha
                    if current_line:
                        lines.append(current_line)
                    current_line = word
                else:
                    # Adicionar palavra à linha atual
                    current_line += (' ' if current_line else '') + word
            
            # Adicionar última linha se houver espaço
            if current_line and len(lines) < max_lines:
                lines.append(current_line)
            
            return '\n'.join(lines[:max_lines])
        
        # Para uma linha, truncar com elípsis
        cut = compact[:max_chars].rsplit(' ', 1)[0].strip()
        return (cut or compact[:max_chars]).rstrip(' ,;:-') + '...'

    @staticmethod
    def _compose_city_from_parts(*parts: Any) -> str:
        values = [XMLPDFService._safe_text(part) for part in parts if XMLPDFService._safe_text(part) and XMLPDFService._safe_text(part) != '-']
        if not values:
            return ''
        if len(values) >= 2 and values[1] and len(values[1]) <= 3:
            return f"{values[0]} - {values[1]}"
        return ' - '.join(values)

    @staticmethod
    def _build_nfse_story(story: list[Any], styles: dict[str, ParagraphStyle], data: dict[str, Any], extra: dict[str, Any]) -> None:
        emit = data.get('emitente') or {}
        dest = data.get('destinatario') or {}
        header = extra.get('cabecalho') or {}
        prestador = extra.get('prestador') or {}
        tomador = extra.get('tomador') or {}
        servico = extra.get('servico') or {}
        trib_mun = extra.get('tributacao_municipal') or {}
        trib_fed = extra.get('tributacao_federal') or {}
        valor_total = extra.get('valor_total') or {}
        totais_tributos = extra.get('totais_tributos') or {}

        numero = data.get('numero') or ''
        chave = data.get('chave') or ''
        chave_exibicao = XMLPDFService._display_nfse_key(chave)
        full_width = float(extra.get('_page_inner_width') or (200 * mm))
        qrcode_width = 34 * mm
        meta_width = full_width - qrcode_width
        tomador_municipio = XMLPDFService._resolve_municipio_text(
            tomador.get('municipio'),
            tomador.get('uf') or header.get('uf_tomador'),
            tomador.get('codigo_municipio'),
            tomador.get('cep'),
        ) or XMLPDFService._compose_city_from_parts(
            getattr(dest, 'get', lambda *_: '')('municipio') if isinstance(dest, dict) else '',
            getattr(dest, 'get', lambda *_: '')('uf') if isinstance(dest, dict) else '',
        )
        local_prestacao = XMLPDFService._resolve_municipio_text(
            servico.get('local_prestacao'),
            '',
            servico.get('codigo_local_prestacao') or trib_mun.get('codigo_local_incidencia'),
            prestador.get('cep'),
        )
        local_incidencia = XMLPDFService._resolve_municipio_text(
            trib_mun.get('local_incidencia'),
            '',
            trib_mun.get('codigo_local_incidencia') or servico.get('codigo_local_prestacao'),
            prestador.get('cep'),
        )

        def fld(label, value, style='value'):
            shown = XMLPDFService._safe_text(value) or '-'
            return Paragraph(f"<b>{label}</b><br/>{shown}", styles[style])

        def section_title(title: str):
            t = Table([[Paragraph(title.upper(), styles['section'])]], colWidths=[full_width])
            t.setStyle(TableStyle([
                ('LINEABOVE', (0, 0), (-1, -1), 0.7, colors.black),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                ('TOPPADDING', (0, 0), (-1, -1), 1),
                ('LEFTPADDING', (0, 0), (-1, -1), 1),
                ('RIGHTPADDING', (0, 0), (-1, -1), 1),
            ]))
            story.append(t)

        def section_table(rows, widths, spans=None):
            t = Table(rows, colWidths=widths)
            style = [
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 1),
                ('RIGHTPADDING', (0, 0), (-1, -1), 1),
                ('TOPPADDING', (0, 0), (-1, -1), 0.5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0.5),
            ]
            for sp in spans or []:
                style.append(('SPAN', sp[0], sp[1]))
            t.setStyle(TableStyle(style))
            story.append(t)
            story.append(Spacer(1, 0.7 * mm))

        # Cabeçalho principal
        municipio_emissor = XMLPDFService._safe_text(header.get('municipio_emissor') or prestador.get('municipio'))
        right_text = [f"<b>MUNICÍPIO DE {municipio_emissor.upper()}</b>" if municipio_emissor else "<b>MUNICÍPIO</b>"]
        if header.get('telefone_municipio'):
            right_text.append(XMLPDFService._safe_text(header.get('telefone_municipio')))
        if header.get('email_municipio'):
            right_text.append(XMLPDFService._safe_text(header.get('email_municipio')))

        header_table = Table(
            [[
                Paragraph("<para align='left'><font size='20'><b>NFS-e</b></font><br/><font size='7'>Nota Fiscal de<br/>Serviço eletrônica</font></para>", styles['value']),
                Paragraph("<font size='14'><b>DANFSe v1.0</b></font><br/><font size='10'><b>Documento Auxiliar da NFS-e</b></font>", styles['title']),
                Paragraph("<br/>".join(right_text), styles['small_center']),
            ]],
            colWidths=[58 * mm, 74 * mm, full_width - (132 * mm)],
        )
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'CENTER'),
            ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
            ('LINEBELOW', (0, 0), (-1, -1), 0.7, colors.black),
            ('LEFTPADDING', (0, 0), (-1, -1), 1),
            ('RIGHTPADDING', (0, 0), (-1, -1), 1),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 2 * mm))

        qr_code = qr.QrCodeWidget((XMLPDFService._safe_text(chave_exibicao) or 'SEMCHAVE')[:120])
        qr_drawing = Drawing(24 * mm, 24 * mm)
        qr_drawing.add(qr_code)
        qr_info = Paragraph(
            "A autenticidade desta NFS-e pode ser verificada pela leitura deste código QR ou pela consulta da chave de acesso no portal nacional da NFS-e.",
            styles['small_qr'],
        )
        meta_grid = Table(
            [
                [Paragraph(f"<b>Chave de Acesso da NFS-e</b><br/>{XMLPDFService._safe_text(chave_exibicao) or '-'}", styles['value'])],
                [
                    fld('Número da NFS-e', numero),
                    fld('Competência da NFS-e', XMLPDFService._format_date(header.get('competencia'))),
                    fld('Data e Hora da emissão da NFS-e', XMLPDFService._format_datetime(header.get('data_emissao_nfse') or data.get('data_emissao'))),
                ],
                [
                    fld('Número da DPS', header.get('numero_dps')),
                    fld('Série da DPS', header.get('serie_dps')),
                    fld('Data e Hora da emissão da DPS', XMLPDFService._format_datetime(header.get('data_emissao_dps'))),
                ],
            ],
            colWidths=[meta_width],
        )
        # rebuild second and third rows with inner table for proper widths
        meta_grid = Table(
            [
                [Paragraph(f"<b>Chave de Acesso da NFS-e</b><br/>{XMLPDFService._safe_text(chave_exibicao) or '-'}", styles['value'])],
                [Table([[
                    fld('Número da NFS-e', numero),
                    fld('Competência da NFS-e', XMLPDFService._format_date(header.get('competencia'))),
                    fld('Data e Hora da emissão da NFS-e', XMLPDFService._format_datetime(header.get('data_emissao_nfse') or data.get('data_emissao'))),
                ]], colWidths=[meta_width * 0.30, meta_width * 0.34, meta_width * 0.36])],
                [Table([[
                    fld('Número da DPS', header.get('numero_dps')),
                    fld('Série da DPS', header.get('serie_dps')),
                    fld('Data e Hora da emissão da DPS', XMLPDFService._format_datetime(header.get('data_emissao_dps'))),
                ]], colWidths=[meta_width * 0.30, meta_width * 0.34, meta_width * 0.36])],
            ],
            colWidths=[meta_width],
        )
        meta_grid.setStyle(TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ]))

        top_table = Table(
            [[meta_grid, Table([[qr_drawing], [qr_info]], colWidths=[qrcode_width])]],
            colWidths=[meta_width, qrcode_width],
        )
        top_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('LINEBELOW', (0, 0), (-1, -1), 0.7, colors.black),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(top_table)
        story.append(Spacer(1, 1.5 * mm))

        section_title('EMITENTE DA NFS-e')
        section_table(
            [
                [
                    fld('Prestador do Serviço', ''),
                    fld('CNPJ / CPF / NIF', prestador.get('documento') or emit.get('cnpj')),
                    fld('Inscrição Municipal', prestador.get('inscricao_municipal')),
                    fld('Telefone', prestador.get('telefone')),
                ],
                [
                    fld('Nome / Nome Empresarial', prestador.get('nome') or emit.get('nome')),
                    '',
                    fld('E-mail', prestador.get('email')),
                    '',
                ],
                [
                    fld('Endereço', prestador.get('endereco')),
                    '',
                    fld('Município', prestador.get('municipio') or header.get('municipio_emissor')),
                    fld('CEP', prestador.get('cep')),
                ],
                [
                    fld('Simples Nacional na Data de Competência', XMLPDFService._map_simples_nacional(prestador.get('simples_nacional'))),
                    '',
                    fld('Regime de Apuração Tributária pelo SN', XMLPDFService._map_regime_sn(prestador.get('regime_sn'))),
                    '',
                ],
            ],
            [50 * mm, 50 * mm, 50 * mm, full_width - (150 * mm)],
            spans=[((0, 1), (1, 1)), ((2, 1), (3, 1)), ((0, 2), (1, 2)), ((0, 3), (1, 3)), ((2, 3), (3, 3))],
        )

        section_title('TOMADOR DO SERVIÇO')
        section_table(
            [
                [
                    fld('CNPJ / CPF / NIF', tomador.get('documento') or dest.get('cnpj')),
                    fld('Inscrição Municipal', tomador.get('inscricao_municipal')),
                    fld('Telefone', tomador.get('telefone')),
                    fld('', ''),
                ],
                [
                    fld('Nome / Nome Empresarial', tomador.get('nome') or dest.get('nome')),
                    '',
                    fld('E-mail', tomador.get('email')),
                    '',
                ],
                [
                    fld('Endereço', tomador.get('endereco')),
                    '',
                    fld('Município', tomador_municipio),
                    fld('CEP', tomador.get('cep')),
                ],
            ],
            [50 * mm, 50 * mm, 50 * mm, full_width - (150 * mm)],
            spans=[((2, 0), (3, 0)), ((0, 1), (1, 1)), ((2, 1), (3, 1)), ((0, 2), (1, 2))],
        )

        interm = Table(
            [
                [Paragraph('INTERMEDIÁRIO DO SERVIÇO', styles['section_center'])],
                [Paragraph('NÃO IDENTIFICADO NA NFS-e', styles['subtitle'])],
            ],
            colWidths=[full_width],
        )
        interm.setStyle(TableStyle([
            ('LINEABOVE', (0, 0), (-1, -1), 0.7, colors.black),
            ('LINEBELOW', (0, -1), (-1, -1), 0.7, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        story.append(interm)
        story.append(Spacer(1, 0.7 * mm))

        codigo_nac = XMLPDFService._truncate_words(XMLPDFService._join_nonempty([
            XMLPDFService._safe_text(servico.get('codigo_tributacao_nacional')),
            XMLPDFService._safe_text(servico.get('descricao_tributacao_nacional')),
        ], ' - '), 44, max_lines=2)
        section_title('SERVIÇO PRESTADO')
        section_table(
            [
                [
                    fld('Código de Tributação Nacional', codigo_nac, style='value_micro'),
                    fld('Código de Tributação Municipal', servico.get('codigo_tributacao_municipal')),
                    fld('Local da Prestação', local_prestacao or servico.get('local_prestacao') or trib_mun.get('local_incidencia')),
                    fld('País da Prestação', servico.get('pais_prestacao')),
                ],
                [fld('Descrição do Serviço', servico.get('descricao_servico'), style='value_compact'), '', '', ''],
            ],
            [50 * mm, 50 * mm, 50 * mm, full_width - (150 * mm)],
            spans=[((0, 1), (3, 1))],
        )

        section_title('TRIBUTAÇÃO MUNICIPAL')
        section_table(
            [
                [
                    fld('Tributação do ISSQN', XMLPDFService._map_tributacao_issqn(trib_mun.get('tributacao_issqn'))),
                    fld('País Resultado da Prestação do Serviço', trib_mun.get('pais_resultado_prestacao')),
                    fld('Município de Incidência do ISSQN', local_incidencia or trib_mun.get('local_incidencia')),
                    fld('Regime Especial de Tributação', XMLPDFService._map_regime_especial(trib_mun.get('regime_especial'))),
                ],
                [
                    fld('Tipo de Imunidade', trib_mun.get('tipo_imunidade')),
                    fld('Suspensão da Exigibilidade do ISSQN', trib_mun.get('suspensao_issqn')),
                    fld('Número Processo Suspensão', trib_mun.get('processo_suspensao')),
                    fld('Benefício Municipal', trib_mun.get('beneficio_municipal')),
                ],
                [
                    fld('Valor do Serviço', XMLPDFService._format_currency(trib_mun.get('valor_servico') or data.get('valor_total'))),
                    fld('Desconto Incondicionado', XMLPDFService._format_currency(trib_mun.get('desconto_incondicionado'))),
                    fld('Total Deduções/Reduções', XMLPDFService._format_currency(trib_mun.get('deducoes'))),
                    fld('Cálculo do BM', trib_mun.get('calculo_bm')),
                ],
                [
                    fld('BC ISSQN', XMLPDFService._format_currency(trib_mun.get('base_calculo'))),
                    fld('Alíquota Aplicada', XMLPDFService._format_percent(trib_mun.get('aliquota_aplicada'))),
                    fld('Retenção do ISSQN', XMLPDFService._map_retencao_issqn(trib_mun.get('retencao_issqn'))),
                    fld('ISSQN Apurado', XMLPDFService._format_currency(trib_mun.get('issqn_apurado'))),
                ],
            ],
            [50 * mm, 50 * mm, 50 * mm, full_width - (150 * mm)],
        )

        section_title('TRIBUTAÇÃO FEDERAL')
        section_table(
            [
                [
                    fld('IRRF', XMLPDFService._format_currency(trib_fed.get('irrf'))),
                    fld('Contribuição Previdenciária - Retida', XMLPDFService._format_currency(trib_fed.get('contribuicao_previdenciaria'))),
                    fld('Contribuições Sociais - Retidas', XMLPDFService._format_currency(trib_fed.get('csll'))),
                    fld('Descrição Contrib. Sociais - Retidas', trib_fed.get('descricao_contribuicoes')),
                ],
                [
                    fld('PIS - Débito Apuração Própria', XMLPDFService._format_currency(trib_fed.get('pis'))),
                    fld('COFINS - Débito Apuração Própria', XMLPDFService._format_currency(trib_fed.get('cofins'))),
                    fld('', ''),
                    fld('', ''),
                ],
            ],
            [50 * mm, 50 * mm, 50 * mm, full_width - (150 * mm)],
        )

        section_title('VALOR TOTAL DA NFS-e')
        section_table(
            [
                [
                    fld('Valor do Serviço', XMLPDFService._format_currency(valor_total.get('valor_servico') or data.get('valor_total'))),
                    fld('Desconto Condicionado', XMLPDFService._format_currency(valor_total.get('desconto_condicionado'))),
                    fld('Desconto Incondicionado', XMLPDFService._format_currency(trib_mun.get('desconto_incondicionado'))),
                    fld('ISSQN Retido', XMLPDFService._format_currency(trib_fed.get('issqn_retido'))),
                ],
                [
                    fld('Total das Retenções Federais', XMLPDFService._format_currency(valor_total.get('total_retencoes_federais'))),
                    fld('PIS/COFINS - Débito Apur. Própria', XMLPDFService._format_currency(valor_total.get('pis_cofins_proprio'))),
                    fld('', ''),
                    fld('Valor Líquido da NFS-e', XMLPDFService._format_currency(valor_total.get('valor_liquido') or data.get('valor_total')), style='value_bold'),
                ],
            ],
            [50 * mm, 50 * mm, 50 * mm, full_width - (150 * mm)],
        )

        section_title('TOTAIS APROXIMADOS DOS TRIBUTOS')
        trib_width = full_width / 3.0
        section_table(
            [[
                fld('Federais', XMLPDFService._format_currency(totais_tributos.get('federais'))),
                fld('Estaduais', XMLPDFService._format_currency(totais_tributos.get('estaduais'))),
                fld('Municipais', XMLPDFService._format_currency(totais_tributos.get('municipais'))),
            ]],
            [trib_width, trib_width, full_width - (2 * trib_width)],
        )

        section_title('INFORMAÇÕES COMPLEMENTARES')
        info_text = XMLPDFService._safe_text(extra.get('informacoes_complementares')) or '-'
        info_table = Table([[Paragraph(info_text, styles['value_compact'])]], colWidths=[full_width])
        info_table.setStyle(TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 1),
            ('RIGHTPADDING', (0, 0), (-1, -1), 1),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ('LINEBELOW', (0, 0), (-1, -1), 0.7, colors.black),
        ]))
        story.append(info_table)

    @staticmethod
    def _build_nfe_story(story: list[Any], styles: dict[str, ParagraphStyle], data: dict[str, Any], extra: dict[str, Any]) -> None:
        emit = data.get('emitente') or {}
        dest = data.get('destinatario') or {}

        story.append(Paragraph('DANFE simplificado', styles['title']))
        story.append(Paragraph('Documento auxiliar gerado a partir do XML', styles['subtitle']))
        story.append(Spacer(1, 2 * mm))

        chave = XMLPDFService._safe_text(data.get('chave'))
        story.append(Paragraph(f"<b>Chave de Acesso:</b> {chave}", styles['value']))
        story.append(Spacer(1, 2 * mm))

        def fld(label, value):
            return Paragraph(f"<b>{label}</b><br/>{XMLPDFService._safe_text(value) or '-'}", styles['value'])

        t = Table([
            [fld('Número', data.get('numero')), fld('Série', data.get('serie')), fld('Modelo', data.get('modelo')), fld('Data de Emissão', XMLPDFService._format_datetime(data.get('data_emissao'))), fld('Valor Total', XMLPDFService._format_currency(data.get('valor_total')))],
            [fld('Emitente', emit.get('nome')), fld('Documento Emitente', emit.get('cnpj')), fld('Destinatário', dest.get('nome')), fld('Documento Destinatário', dest.get('cnpj')), fld('CFOP', data.get('cfop'))]
        ], colWidths=[38*mm, 38*mm, 38*mm, 38*mm, 38*mm])
        story.append(t)

    @staticmethod
    def _format_date(value: Any) -> str:
        if not value:
            return '-'
        if hasattr(value, 'strftime'):
            return value.strftime('%d/%m/%Y')
        text = str(value).strip()
        if 'T' in text:
            text = text.split('T', 1)[0]
        if len(text) >= 10 and text[4] == '-' and text[7] == '-':
            y, m, d = text[:10].split('-')
            return f'{d}/{m}/{y}'
        return text

    @staticmethod
    def _format_datetime(value: Any) -> str:
        if not value:
            return '-'
        if hasattr(value, 'strftime'):
            return value.strftime('%d/%m/%Y %H:%M:%S')
        text = str(value).strip().replace('T', ' ')
        if len(text) >= 19 and text[4] == '-' and text[7] == '-':
            return f'{text[8:10]}/{text[5:7]}/{text[0:4]} {text[11:19]}'
        return text

    @staticmethod
    def _format_currency(value: Any) -> str:
        if value in (None, '', '-', '0', '0.00', '0,00'):
            return '-'
        try:
            raw = str(value).strip().replace('R$', '').replace(' ', '')
            if ',' in raw and '.' in raw:
                if raw.rfind(',') > raw.rfind('.'):
                    raw = raw.replace('.', '').replace(',', '.')
                else:
                    raw = raw.replace(',', '')
            elif ',' in raw:
                raw = raw.replace('.', '').replace(',', '.')
            number = float(raw)
            formatted = f'{number:,.2f}'
            formatted = formatted.replace(',', 'X').replace('.', ',').replace('X', '.')
            return f'R$ {formatted}'
        except Exception:
            text = str(value).strip()
            return text if text else '-'

    @staticmethod
    def _format_percent(value: Any) -> str:
        text = str(value or '').strip()
        if not text or text in {'0', '0.00', '0,00'}:
            return '-'
        if text.endswith('%'):
            return text
        if ',' not in text and '.' in text:
            try:
                return f'{float(text):.2f}%'.replace('.', ',')
            except Exception:
                return text
        return f'{text}%'

    @staticmethod
    def _map_simples_nacional(value: Any) -> str:
        mapping = {
            '1': 'Optante pelo Simples Nacional',
            '2': 'Não optante pelo Simples Nacional',
            '3': 'Optante - Microempreendedor Individual (MEI)',
        }
        text = str(value or '').strip()
        return mapping.get(text, text)

    @staticmethod
    def _map_regime_sn(value: Any) -> str:
        mapping = {
            '1': 'Regime caixa',
            '2': 'Regime competência',
        }
        text = str(value or '').strip()
        return mapping.get(text, text)

    @staticmethod
    def _map_regime_especial(value: Any) -> str:
        mapping = {
            '0': '-',
            '1': 'Microempresa municipal',
            '2': 'Estimativa',
            '3': 'Sociedade de profissionais',
            '4': 'Cooperativa',
            '5': 'MEI',
            '6': 'ME/EPP',
        }
        text = str(value or '').strip()
        return mapping.get(text, text)

    @staticmethod
    def _map_tributacao_issqn(value: Any) -> str:
        mapping = {
            '1': 'Operação tributável',
            '2': 'Imunidade',
            '3': 'Não incidência',
            '4': 'Exportação',
            '5': 'Exigibilidade suspensa por decisão judicial',
            '6': 'Exigibilidade suspensa por processo administrativo',
        }
        text = str(value or '').strip()
        return mapping.get(text, text or '-')

    @staticmethod
    def _map_retencao_issqn(value: Any) -> str:
        mapping = {
            '1': 'Não Retido',
            '2': 'Retido pelo tomador',
            '3': 'Retido por intermediário',
        }
        text = str(value or '').strip()
        return mapping.get(text, text or '-')

    @staticmethod
    def _safe_text(value: Any) -> str:
        if value is None:
            return ''
        text = str(value)
        return (
            text.replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
        )

    @staticmethod
    def _display_nfse_key(value: Any) -> str:
        text = str(value or '').strip()
        if not text:
            return '-'
        upper = text.upper()
        if upper.startswith('NFSE'):
            return text[4:] or text
        if upper.startswith('NFS'):
            return text[3:] or text
        return text

    @staticmethod
    def _join_nonempty(values: list[Any], sep: str = ' '):
        items = [str(v).strip() for v in values if v not in (None, '', '-') and str(v).strip()]
        return sep.join(items) if items else '-'

