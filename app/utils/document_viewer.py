"""Utilitários para localizar e abrir XML/PDF/DANFE de documentos."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from app.services.xml_pdf_service import XMLPDFService
from app.utils.logger import log
from config.settings import DOWNLOADS_DIR, XML_DIR


def candidate_directories(empresa, cred_repo) -> list[Path]:
    """Retorna diretórios candidatos para localizar XMLs e PDFs de uma empresa."""
    if not empresa:
        return []

    cnpj = (empresa.cnpj or '').strip()
    candidates: list[Path] = []

    cred_portal = cred_repo.get_ativo_by_empresa(empresa.id, 'PORTAL') if cred_repo else None
    base_download = Path(cred_portal.downloads_dir) if cred_portal and cred_portal.downloads_dir else Path(DOWNLOADS_DIR)

    for candidate in [
        Path(XML_DIR) / cnpj,
        Path(DOWNLOADS_DIR) / cnpj,
        base_download,
        base_download / cnpj,
    ]:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        if resolved not in candidates:
            candidates.append(resolved)

    return [path for path in candidates if path.exists()]


def find_official_pdf(doc, xml_path: Path, empresa, cred_repo) -> Path | None:
    """Localiza o PDF oficial correspondente ao XML sem confundir documentos por número parcial."""
    candidates: list[Path] = []
    stem = xml_path.stem
    chave = (doc.chave or '').strip()

    def add(candidate: Path | None):
        if not candidate:
            return
        if candidate not in candidates:
            candidates.append(candidate)

    for candidate in [
        xml_path.with_name(f"{stem}_oficial.pdf"),
        xml_path.with_name(f"{stem}_danfe_oficial.pdf"),
        xml_path.with_name(f"{stem}_danfse_oficial.pdf"),
        xml_path.with_suffix('.pdf'),
    ]:
        add(candidate)

    searchable_tokens = [token for token in [chave, stem] if token and len(token) >= 16]
    if searchable_tokens:
        for directory in [xml_path.parent, *candidate_directories(empresa, cred_repo)]:
            if not directory or not directory.exists():
                continue
            for token in searchable_tokens:
                for pattern in [f"*{token}*_oficial.pdf", f"*{token}_danfe*.pdf", f"*{token}_danfse*.pdf", f"*{token}.pdf"]:
                    try:
                        for match in directory.rglob(pattern):
                            if match.is_file():
                                add(match)
                    except Exception:
                        continue

    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                return candidate
        except Exception:
            continue
    return None


def open_document_file(doc, empresa, cred_repo) -> tuple[bool, str]:
    """Abre o PDF oficial, PDF gerado ou XML do documento."""
    xml_path = (doc.arquivo_xml or '').strip()
    if not xml_path:
        message = f"Registro {getattr(doc, 'id', '?')} não possui arquivo XML vinculado."
        log.warning(message)
        return False, message

    path = Path(xml_path)
    if not path.exists():
        message = f"Arquivo não encontrado: {xml_path}"
        log.warning(message)
        return False, message

    official_pdf = find_official_pdf(doc, path, empresa, cred_repo)
    if official_pdf and official_pdf.exists():
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(official_pdf.resolve())))
        log.info(f"PDF oficial aberto: {official_pdf}")
        return True, str(official_pdf)

    pdf_path = XMLPDFService.ensure_pdf(path)
    if pdf_path and pdf_path.exists():
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(pdf_path.resolve())))
        log.info(f"PDF gerado aberto: {pdf_path}")
        return True, str(pdf_path)

    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
    log.info(f"XML aberto: {xml_path}")
    return True, str(path)
