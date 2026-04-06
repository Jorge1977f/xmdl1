"""Importação de XMLs baixados para o banco de dados."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional
import re

from sqlalchemy.orm import Session

from app.db import DocumentoRepository
from app.parsers import DocumentXMLParser
from app.utils.hashes import HashManager
from app.utils.logger import log


@dataclass
class ImportSummary:
    scanned: int = 0
    imported: int = 0
    updated: int = 0
    invalid: int = 0
    duplicates: int = 0


class XMLImportService:
    """Importa XMLs da pasta de download para a tabela de documentos."""

    def __init__(self, session: Session):
        self.session = session
        self.doc_repo = DocumentoRepository(session)

    def import_from_directory(
        self,
        empresa_id: int,
        tipo_documento: str,
        directory: str | Path,
        modified_after: datetime | None = None,
    ) -> ImportSummary:
        return self._import_directory(
            empresa_id=empresa_id,
            default_tipo_documento=tipo_documento,
            directory=directory,
            modified_after=modified_after,
            company_cnpj=None,
        )

    def import_company_directory(
        self,
        empresa_id: int,
        company_cnpj: str,
        directory: str | Path,
        modified_after: datetime | None = None,
    ) -> ImportSummary:
        """Importa uma pasta da empresa inferindo o tipo do documento por arquivo."""
        return self._import_directory(
            empresa_id=empresa_id,
            default_tipo_documento=None,
            directory=directory,
            modified_after=modified_after,
            company_cnpj=company_cnpj,
        )

    def _import_directory(
        self,
        empresa_id: int,
        default_tipo_documento: Optional[str],
        directory: str | Path,
        modified_after: datetime | None = None,
        company_cnpj: Optional[str] = None,
    ) -> ImportSummary:
        summary = ImportSummary()
        base_dir = Path(directory)
        if not base_dir.exists():
            log.warning(f"Pasta de importação não encontrada: {base_dir}")
            return summary

        files = list(self._iter_xml_files(base_dir, modified_after))
        summary.scanned = len(files)
        for xml_path in files:
            try:
                content = xml_path.read_bytes()
            except Exception as exc:
                summary.invalid += 1
                log.exception(f"Falha ao ler XML {xml_path}: {exc}")
                continue

            parsed = DocumentXMLParser.parse(content)
            if not parsed or not parsed.get("chave"):
                summary.invalid += 1
                log.warning(f"XML ignorado por falta de chave/dados válidos: {xml_path}")
                continue

            tipo_documento = default_tipo_documento or self._infer_tipo_documento(parsed, xml_path, company_cnpj)
            payload = {
                "numero": parsed.get("numero"),
                "serie": parsed.get("serie"),
                "modelo": parsed.get("modelo"),
                "data_emissao": parsed.get("data_emissao"),
                "emitente_cnpj": (parsed.get("emitente") or {}).get("cnpj"),
                "emitente_nome": (parsed.get("emitente") or {}).get("nome"),
                "destinatario_cnpj": (parsed.get("destinatario") or {}).get("cnpj"),
                "destinatario_nome": (parsed.get("destinatario") or {}).get("nome"),
                "valor_total": parsed.get("valor_total") or 0.0,
                "situacao": parsed.get("status") or "VALIDO",
                "origem_captura": "PORTAL",
                "schema": parsed.get("tipo") or "NFE",
                "hash_xml": HashManager.calculate_content_hash(content),
                "arquivo_xml": str(xml_path),
                "status": "XML_PROCESSADO",
            }

            existente = self.doc_repo.get_by_chave(empresa_id, parsed["chave"])
            if existente:
                if self._needs_update(existente, payload, tipo_documento):
                    self.doc_repo.update(existente.id, tipo_documento=tipo_documento, **payload)
                    summary.updated += 1
                else:
                    summary.duplicates += 1
            else:
                self.doc_repo.create(
                    empresa_id=empresa_id,
                    tipo_documento=tipo_documento,
                    chave=parsed["chave"],
                    **payload,
                )
                summary.imported += 1

        return summary

    def _infer_tipo_documento(self, parsed: dict, xml_path: Path, company_cnpj: Optional[str]) -> str:
        path_lower = ' / '.join(part.lower() for part in xml_path.parts)
        path_rules = [
            ('nfse_prestada', 'NFS-e Prestada'),
            ('nfse_prestadas', 'NFS-e Prestada'),
            ('prestada', 'NFS-e Prestada'),
            ('emitidas', 'NFS-e Prestada'),
            ('nfse_tomada', 'NFS-e Tomada'),
            ('nfse_tomadas', 'NFS-e Tomada'),
            ('tomada', 'NFS-e Tomada'),
            ('recebidas', 'NFS-e Tomada'),
            ('nfe_de_entrada', 'NF-e de Entrada'),
            ('nfe_entrada', 'NF-e de Entrada'),
            ('entrada', 'NF-e de Entrada'),
            ('nfe_de_saida', 'NF-e de Saída'),
            ('nfe_saida', 'NF-e de Saída'),
            ('saida', 'NF-e de Saída'),
            ('saída', 'NF-e de Saída'),
        ]
        for token, label in path_rules:
            if token in path_lower:
                return label

        schema = (parsed.get('tipo') or '').upper()
        emit_cnpj = self._digits((parsed.get('emitente') or {}).get('cnpj'))
        dest_cnpj = self._digits((parsed.get('destinatario') or {}).get('cnpj'))
        company = self._digits(company_cnpj)

        if schema == 'NFSE':
            if company and emit_cnpj and emit_cnpj == company:
                return 'NFS-e Prestada'
            if company and dest_cnpj and dest_cnpj == company:
                return 'NFS-e Tomada'
            return 'NFS-e'

        if company and emit_cnpj and emit_cnpj == company:
            return 'NF-e de Saída'
        if company and dest_cnpj and dest_cnpj == company:
            return 'NF-e de Entrada'
        return 'NF-e'

    def _digits(self, value: Optional[str]) -> str:
        return re.sub(r'\D+', '', value or '')

    def _needs_update(self, existing, payload: dict, tipo_documento: Optional[str] = None) -> bool:
        comparable_fields = [
            "numero",
            "serie",
            "modelo",
            "data_emissao",
            "emitente_cnpj",
            "emitente_nome",
            "destinatario_cnpj",
            "destinatario_nome",
            "valor_total",
            "situacao",
            "origem_captura",
            "schema",
            "hash_xml",
            "arquivo_xml",
            "status",
        ]
        if tipo_documento and getattr(existing, 'tipo_documento', None) != tipo_documento:
            return True
        for field in comparable_fields:
            current = getattr(existing, field, None)
            new_value = payload.get(field)
            if current != new_value:
                return True
        return False

    def _iter_xml_files(self, base_dir: Path, modified_after: datetime | None) -> Iterable[Path]:
        margin = timedelta(seconds=5)
        threshold = modified_after - margin if modified_after else None
        for path in base_dir.rglob("*.xml"):
            if not path.is_file():
                continue
            if threshold is not None:
                modified = datetime.utcfromtimestamp(path.stat().st_mtime)
                if modified < threshold:
                    continue
            yield path
