"""
Parser para comprovante de inscrição e situação cadastral do CNPJ (PDF).
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Dict, Optional

from pypdf import PdfReader


class CnpjPdfParser:
    """Extrai dados do comprovante de CNPJ em PDF."""

    LABELS = {
        "cnpj": "NUMERO DE INSCRICAO",
        "matriz_filial": "MATRIZ",
        "data_abertura": "DATA DE ABERTURA",
        "razao_social": "NOME EMPRESARIAL",
        "nome_fantasia": "TITULO DO ESTABELECIMENTO (NOME DE FANTASIA)",
        "porte": "PORTE",
        "atividade_principal": "CODIGO E DESCRICAO DA ATIVIDADE ECONOMICA PRINCIPAL",
        "atividades_secundarias": "CODIGO E DESCRICAO DAS ATIVIDADES ECONOMICAS SECUNDARIAS",
        "natureza_juridica": "CODIGO E DESCRICAO DA NATUREZA JURIDICA",
        "logradouro": "LOGRADOURO",
        "numero": "NUMERO",
        "complemento": "COMPLEMENTO",
        "cep": "CEP",
        "bairro": "BAIRRO/DISTRITO",
        "municipio": "MUNICIPIO",
        "uf": "UF",
        "email": "ENDERECO ELETRONICO",
        "telefone": "TELEFONE",
        "efr": "ENTE FEDERATIVO RESPONSAVEL (EFR)",
        "situacao_cadastral": "SITUACAO CADASTRAL",
        "data_situacao_cadastral": "DATA DA SITUACAO CADASTRAL",
        "motivo_situacao_cadastral": "MOTIVO DE SITUACAO CADASTRAL",
        "situacao_especial": "SITUACAO ESPECIAL",
        "data_situacao_especial": "DATA DA SITUACAO ESPECIAL",
    }

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return text

    @classmethod
    def _extract_text(cls, pdf_path: str | Path) -> str:
        reader = PdfReader(str(pdf_path))
        chunks = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text:
                chunks.append(page_text)
        return "\n".join(chunks)

    @classmethod
    def _split_lines(cls, text: str) -> list[str]:
        normalized = cls._normalize_text(text)
        lines = []
        for line in normalized.splitlines():
            clean = re.sub(r"\s+", " ", line).strip()
            if clean:
                lines.append(clean)
        return lines

    @staticmethod
    def _extract_value(lines: list[str], label: str) -> Optional[str]:
        for index, line in enumerate(lines):
            if line == label and index + 1 < len(lines):
                return lines[index + 1].strip()
        return None

    @staticmethod
    def _digits_only(value: Optional[str]) -> str:
        if not value:
            return ""
        return re.sub(r"\D", "", value)

    @classmethod
    def parse(cls, pdf_path: str | Path) -> Dict[str, str]:
        text = cls._extract_text(pdf_path)
        lines = cls._split_lines(text)

        data: Dict[str, str] = {}
        for key, label in cls.LABELS.items():
            value = cls._extract_value(lines, label) or ""
            data[key] = value

        data["cnpj_mascara"] = data.get("cnpj", "")
        data["cnpj"] = cls._digits_only(data.get("cnpj"))
        data["uf"] = (data.get("uf") or "").upper().strip()
        data["municipio"] = (data.get("municipio") or "").strip().title()
        data["razao_social"] = (data.get("razao_social") or "").strip()
        data["nome_fantasia"] = (data.get("nome_fantasia") or "").strip()
        data["porte"] = (data.get("porte") or "").strip()
        data["email"] = (data.get("email") or "").strip().lower()
        data["logradouro"] = (data.get("logradouro") or "").strip().title()
        data["bairro"] = (data.get("bairro") or "").strip().title()
        data["complemento"] = (data.get("complemento") or "").strip().upper()
        data["telefone"] = (data.get("telefone") or "").strip()
        data["atividade_principal"] = (data.get("atividade_principal") or "").strip()
        data["atividades_secundarias"] = (data.get("atividades_secundarias") or "").strip()
        data["natureza_juridica"] = (data.get("natureza_juridica") or "").strip()
        data["situacao_cadastral"] = (data.get("situacao_cadastral") or "").strip().upper()
        data["situacao_especial"] = (data.get("situacao_especial") or "").strip().upper()
        data["matriz_filial"] = (data.get("matriz_filial") or "").strip().upper() or "MATRIZ"

        return data
