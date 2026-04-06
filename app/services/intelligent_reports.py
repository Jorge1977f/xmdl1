"""Módulo de relatórios inteligentes com análises financeiras e operacionais."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from collections import defaultdict
from decimal import Decimal

from app.utils.logger import log


@dataclass
class RelatorioFinanceiro:
    """Relatório financeiro de notas fiscais."""
    periodo_inicio: datetime
    periodo_fim: datetime
    total_notas: int = 0
    total_valor: Decimal = Decimal('0.00')
    valor_medio: Decimal = Decimal('0.00')
    valor_minimo: Decimal = Decimal('0.00')
    valor_maximo: Decimal = Decimal('0.00')
    notas_canceladas: int = 0
    notas_validas: int = 0
    percentual_canceladas: float = 0.0
    valor_cancelado: Decimal = Decimal('0.00')
    valor_valido: Decimal = Decimal('0.00')


@dataclass
class RelatorioCientes:
    """Relatório de análise de clientes."""
    top_clientes: List[Dict[str, Any]] = field(default_factory=list)
    total_clientes_unicos: int = 0
    cliente_maior_valor: Optional[Dict[str, Any]] = None
    cliente_mais_notas: Optional[Dict[str, Any]] = None


@dataclass
class RelatorioServicos:
    """Relatório de análise de serviços."""
    top_servicos: List[Dict[str, Any]] = field(default_factory=list)
    total_servicos_unicos: int = 0
    servico_mais_faturado: Optional[Dict[str, Any]] = None
    servico_mais_frequente: Optional[Dict[str, Any]] = None


@dataclass
class RelatorioImpostos:
    """Relatório de análise de impostos."""
    total_issqn: Decimal = Decimal('0.00')
    total_irrf: Decimal = Decimal('0.00')
    total_pis: Decimal = Decimal('0.00')
    total_cofins: Decimal = Decimal('0.00')
    total_csll: Decimal = Decimal('0.00')
    total_retencoes: Decimal = Decimal('0.00')
    percentual_issqn: float = 0.0
    percentual_retencoes: float = 0.0


@dataclass
class RelatorioTendencias:
    """Relatório de tendências e comparações."""
    periodos: List[Dict[str, Any]] = field(default_factory=list)
    crescimento_mes_anterior: float = 0.0
    media_diaria: Decimal = Decimal('0.00')
    pico_faturamento: Optional[Dict[str, Any]] = None
    vale_faturamento: Optional[Dict[str, Any]] = None


@dataclass
class RelatorioAtrasos:
    """Relatório de atrasos e cancelamentos."""
    total_canceladas: int = 0
    total_validas: int = 0
    taxa_cancelamento: float = 0.0
    canceladas_por_periodo: List[Dict[str, Any]] = field(default_factory=list)


class RelatoriosInteligentes:
    """Gera relatórios inteligentes a partir de dados de notas fiscais."""

    def __init__(self, dados_notas: List[Dict[str, Any]]):
        """Inicializa o gerador de relatórios."""
        self.dados_notas = dados_notas

    def gerar_relatorio_financeiro(self) -> RelatorioFinanceiro:
        """Gera relatório financeiro."""
        if not self.dados_notas:
            return RelatorioFinanceiro(
                periodo_inicio=datetime.now(),
                periodo_fim=datetime.now(),
            )

        valores = []
        valores_cancelados = []
        valores_validos = []
        canceladas = 0
        validas = 0

        for nota in self.dados_notas:
            valor = self._parse_valor(nota.get('valor_total'))
            status = nota.get('status', 'VALIDO').upper()

            if valor:
                valores.append(valor)
                if status == 'CANCELADA':
                    valores_cancelados.append(valor)
                    canceladas += 1
                else:
                    valores_validos.append(valor)
                    validas += 1

        total_valor = sum(valores) if valores else Decimal('0.00')
        total_notas = len(self.dados_notas)
        valor_medio = total_valor / total_notas if total_notas > 0 else Decimal('0.00')

        return RelatorioFinanceiro(
            periodo_inicio=self._get_data_minima(),
            periodo_fim=self._get_data_maxima(),
            total_notas=total_notas,
            total_valor=total_valor,
            valor_medio=valor_medio,
            valor_minimo=min(valores) if valores else Decimal('0.00'),
            valor_maximo=max(valores) if valores else Decimal('0.00'),
            notas_canceladas=canceladas,
            notas_validas=validas,
            percentual_canceladas=(canceladas / total_notas * 100) if total_notas > 0 else 0.0,
            valor_cancelado=sum(valores_cancelados) if valores_cancelados else Decimal('0.00'),
            valor_valido=sum(valores_validos) if valores_validos else Decimal('0.00'),
        )

    def gerar_relatorio_clientes(self, top_n: int = 10) -> RelatorioCientes:
        """Gera relatório de clientes."""
        clientes_dados = defaultdict(lambda: {'valor': Decimal('0.00'), 'notas': 0})

        for nota in self.dados_notas:
            cliente = (
                nota.get('tomador_razao_social')
                or nota.get('destinatario_nome')
                or nota.get('emitente_nome')
                or 'Desconhecido'
            )
            valor = self._parse_valor(nota.get('valor_total'))

            if valor:
                clientes_dados[cliente]['valor'] += valor
                clientes_dados[cliente]['notas'] += 1

        top_clientes_valor = sorted(
            clientes_dados.items(),
            key=lambda x: x[1]['valor'],
            reverse=True
        )[:top_n]

        top_clientes_lista = [
            {
                'cliente': nome,
                'valor_total': float(dados['valor']),
                'quantidade_notas': dados['notas'],
                'valor_medio': float(dados['valor'] / dados['notas']) if dados['notas'] > 0 else 0.0,
            }
            for nome, dados in top_clientes_valor
        ]

        return RelatorioCientes(
            top_clientes=top_clientes_lista,
            total_clientes_unicos=len(clientes_dados),
            cliente_maior_valor=top_clientes_lista[0] if top_clientes_lista else None,
        )

    def gerar_relatorio_servicos(self, top_n: int = 10) -> RelatorioServicos:
        """Gera relatório de serviços (apenas notas válidas)."""
        servicos_dados = defaultdict(lambda: {'valor': Decimal('0.00'), 'notas': 0})

        for nota in self.dados_notas:
            # Excluir notas canceladas do relatório de serviços
            status = str(nota.get('status', 'VALIDO') or 'VALIDO').upper()
            if 'CANCEL' in status:
                continue
            
            servico = (
                nota.get('descricao_servico')
                or nota.get('servico_descricao')
                or nota.get('tipo_documento')
                or 'Serviço Genérico'
            )
            valor = self._parse_valor(nota.get('valor_total'))

            if valor:
                servicos_dados[servico]['valor'] += valor
                servicos_dados[servico]['notas'] += 1

        top_servicos_valor = sorted(
            servicos_dados.items(),
            key=lambda x: x[1]['valor'],
            reverse=True
        )[:top_n]

        top_servicos_lista = [
            {
                'servico': nome,
                'valor_total': float(dados['valor']),
                'quantidade_notas': dados['notas'],
            }
            for nome, dados in top_servicos_valor
        ]

        return RelatorioServicos(
            top_servicos=top_servicos_lista,
            total_servicos_unicos=len(servicos_dados),
            servico_mais_faturado=top_servicos_lista[0] if top_servicos_lista else None,
        )

    def gerar_relatorio_impostos(self) -> RelatorioImpostos:
        """Gera relatório de impostos."""
        total_issqn = Decimal('0.00')
        total_irrf = Decimal('0.00')
        total_pis = Decimal('0.00')
        total_cofins = Decimal('0.00')
        total_csll = Decimal('0.00')
        total_valor = Decimal('0.00')

        for nota in self.dados_notas:
            total_issqn += self._parse_valor(nota.get('issqn_valor'))
            total_irrf += self._parse_valor(nota.get('irrf_valor'))
            total_pis += self._parse_valor(nota.get('pis_valor'))
            total_cofins += self._parse_valor(nota.get('cofins_valor'))
            total_csll += self._parse_valor(nota.get('csll_valor'))
            total_valor += self._parse_valor(nota.get('valor_total'))

        total_retencoes = total_issqn + total_irrf + total_pis + total_cofins + total_csll

        return RelatorioImpostos(
            total_issqn=total_issqn,
            total_irrf=total_irrf,
            total_pis=total_pis,
            total_cofins=total_cofins,
            total_csll=total_csll,
            total_retencoes=total_retencoes,
            percentual_issqn=(total_issqn / total_valor * 100) if total_valor > 0 else 0.0,
            percentual_retencoes=(total_retencoes / total_valor * 100) if total_valor > 0 else 0.0,
        )

    def gerar_relatorio_tendencias(self) -> RelatorioTendencias:
        """Gera relatório de tendências."""
        periodos_dados = defaultdict(Decimal)

        for nota in self.dados_notas:
            data = self._parse_data(nota.get('data_emissao'))
            if data:
                valor = self._parse_valor(nota.get('valor_total'))
                if valor:
                    chave = data.strftime('%Y-%m-%d')
                    periodos_dados[chave] += valor

        periodos_ordenados = sorted(periodos_dados.items())
        periodos_lista = [
            {'data': data, 'valor': float(valor)}
            for data, valor in periodos_ordenados
        ]

        total_valor = sum(periodos_dados.values())
        media_diaria = total_valor / len(periodos_dados) if periodos_dados else Decimal('0.00')

        pico = max(periodos_lista, key=lambda x: x['valor']) if periodos_lista else None
        vale = min(periodos_lista, key=lambda x: x['valor']) if periodos_lista else None

        return RelatorioTendencias(
            periodos=periodos_lista,
            media_diaria=media_diaria,
            pico_faturamento=pico,
            vale_faturamento=vale,
        )

    def gerar_relatorio_atrasos(self) -> RelatorioAtrasos:
        """Gera relatório de cancelamentos."""
        canceladas = 0
        validas = 0

        for nota in self.dados_notas:
            status = nota.get('status', 'VALIDO').upper()
            if status == 'CANCELADA':
                canceladas += 1
            else:
                validas += 1

        total = canceladas + validas
        taxa_cancelamento = (canceladas / total * 100) if total > 0 else 0.0

        return RelatorioAtrasos(
            total_canceladas=canceladas,
            total_validas=validas,
            taxa_cancelamento=taxa_cancelamento,
        )

    def _parse_valor(self, valor: Any) -> Decimal:
        """Converte valor para Decimal."""
        if valor is None:
            return Decimal('0.00')
        try:
            if isinstance(valor, Decimal):
                return valor
            if isinstance(valor, (int, float)):
                return Decimal(str(valor))
            valor_str = str(valor).replace('R$', '').replace('.', '').replace(',', '.').strip()
            return Decimal(valor_str) if valor_str else Decimal('0.00')
        except Exception:
            return Decimal('0.00')

    def _parse_data(self, data: Any) -> Optional[datetime]:
        """Converte data para datetime."""
        if data is None:
            return None
        try:
            if isinstance(data, datetime):
                return data
            if isinstance(data, str):
                for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S']:
                    try:
                        return datetime.strptime(data, fmt)
                    except ValueError:
                        continue
        except Exception:
            pass
        return None

    def _get_data_minima(self) -> datetime:
        """Retorna a data mínima dos dados."""
        datas = []
        for nota in self.dados_notas:
            data = self._parse_data(nota.get('data_emissao'))
            if data:
                datas.append(data)
        return min(datas) if datas else datetime.now()

    def _get_data_maxima(self) -> datetime:
        """Retorna a data máxima dos dados."""
        datas = []
        for nota in self.dados_notas:
            data = self._parse_data(nota.get('data_emissao'))
            if data:
                datas.append(data)
        return max(datas) if datas else datetime.now()
