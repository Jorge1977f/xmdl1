"""Sincronização direta com a API oficial da NFS-e Nacional (ADN).

Observações importantes:
- O endpoint oficial para contribuintes existe e usa mTLS.
- O requests não consegue usar um .pfx/.p12 diretamente em ``session.cert``.
  Por isso este serviço converte o certificado PKCS#12 para PEM temporário.
- A API devolve um envelope JSON com uma janela de documentos em ``LoteDFe``.
  Cada item do lote possui um ``NSU`` próprio e o ``ArquivoXml`` compactado.
- Este serviço materializa o JSON bruto, extrai os XMLs reais, filtra por tipo e
  período, gera manifestos e importa automaticamente o que passou no filtro.
"""
from __future__ import annotations

import base64
import csv
import json
import gzip
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import requests
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates

from app.db import (
    get_db_session,
    JobDownloadRepository,
    LogEventoRepository,
    CredencialRepository,
    EmpresaRepository,
)
from app.parsers import DocumentXMLParser
from app.services.xml_import_service import XMLImportService
from app.utils.logger import log
from config.settings import DOWNLOADS_DIR


class SincronizadorNFSEAPI:
    """Sincronizador de DF-e via ADN para contribuintes."""

    URL_PRODUCAO = "https://adn.nfse.gov.br"
    URL_HOMOLOGACAO = "https://adn.producaorestrita.nfse.gov.br"

    def __init__(
        self,
        empresa_id: int,
        cert_path: str,
        cert_password: str,
        ambiente: str = "producao",
        output_dir: Optional[Path] = None,
        job_id: Optional[int] = None,
        credencial_id: Optional[int] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ):
        self.empresa_id = empresa_id
        self.cert_path = str(cert_path)
        self.cert_password = cert_password or ""
        self.ambiente = (ambiente or "producao").lower()
        self.job_id = job_id
        self.credencial_id = credencial_id
        self.progress_callback = progress_callback
        self.url_base = self.URL_HOMOLOGACAO if self.ambiente.startswith("homo") else self.URL_PRODUCAO
        self.started_at = datetime.now()
        self.nsu_atual = 0

        self.respostas_salvas = 0
        self.documentos_inspecionados = 0
        self.documentos_extraidos = 0
        self.documentos_filtrados = 0
        self.documentos_importados = 0
        self.documentos_atualizados = 0
        self.documentos_invalidos = 0
        self.documentos_duplicados = 0
        self.consultas_api = 0
        self.max_lote_retorno = 0
        self.erros: list[str] = []
        self.avisos: list[str] = []
        self._pem_files: list[Path] = []
        self._manifest_rows: list[dict] = []
        self._item_nsu_processados: set[int] = set()
        self._summary_report: dict[str, object] = {}

        base_output = Path(output_dir or DOWNLOADS_DIR / "api_nfse")
        stamp = self.started_at.strftime("%Y%m%d_%H%M%S")
        self.output_dir = base_output / f"empresa_{empresa_id}" / stamp
        self.raw_dir = self.output_dir / "raw"
        self.decoded_dir = self.output_dir / "decoded"
        self.debug_dir = self.output_dir / "debug"
        self.xml_dir = self.output_dir / "xml"
        self.xml_todos_dir = self.xml_dir / "todos"
        self.xml_prestadas_dir = self.xml_dir / "prestadas"
        self.xml_tomadas_dir = self.xml_dir / "tomadas"
        self.xml_outros_dir = self.xml_dir / "outros"
        self.matched_dir = self.output_dir / "matched"
        self.matched_prestadas_dir = self.matched_dir / "prestadas"
        self.matched_tomadas_dir = self.matched_dir / "tomadas"
        self.fora_filtro_dir = self.output_dir / "fora_filtro"
        for folder in (
            self.output_dir,
            self.raw_dir,
            self.decoded_dir,
            self.debug_dir,
            self.xml_dir,
            self.xml_todos_dir,
            self.xml_prestadas_dir,
            self.xml_tomadas_dir,
            self.xml_outros_dir,
            self.matched_dir,
            self.matched_prestadas_dir,
            self.matched_tomadas_dir,
            self.fora_filtro_dir,
        ):
            folder.mkdir(parents=True, exist_ok=True)

        self._db_session = get_db_session()
        self._job_repo = JobDownloadRepository(self._db_session)
        self._log_repo = LogEventoRepository(self._db_session)
        self._credencial_repo = CredencialRepository(self._db_session)
        self._empresa_repo = EmpresaRepository(self._db_session)
        self._xml_import_service = XMLImportService(self._db_session)
        self._empresa = self._empresa_repo.get_by_id(self.empresa_id)
        self._company_cnpj = self._only_digits(getattr(self._empresa, "cnpj", "") or "")
        self._company_root = self._company_cnpj[:8] if len(self._company_cnpj) >= 8 else ""
        self.session = self._criar_sessao()

        self._log("INFO", f"Sincronizador API iniciado | ambiente={self.ambiente} | base={self.url_base}")
        self._log("INFO", f"Saída dos arquivos: {self.output_dir}")

    def close(self):
        try:
            self.session.close()
        except Exception:
            pass
        for pem in self._pem_files:
            try:
                if pem.exists():
                    pem.unlink()
            except Exception:
                pass
        try:
            self._db_session.close()
        except Exception:
            pass

    def _emit_progress(self, percent: int, message: str):
        if self.progress_callback:
            try:
                self.progress_callback(int(percent), str(message or ""))
            except Exception:
                pass

    def _persistir_proximo_nsu(self, nsu: int, lote: int | None = None, scope: str = "geral"):
        if not self.credencial_id:
            return
        try:
            nsu_limpo = max(0, int(nsu))
            payload = {"ultimo_nsu_api": nsu_limpo}
            if scope == "prestadas":
                payload["ultimo_nsu_api_prestadas"] = nsu_limpo
            elif scope == "tomadas":
                payload["ultimo_nsu_api_tomadas"] = nsu_limpo
            if lote is not None:
                payload["lote_nsu_api"] = max(1, int(lote))
            self._credencial_repo.update(self.credencial_id, **payload)
        except Exception as exc:
            log.warning(f"[API NFSe] Não foi possível persistir NSU na credencial {self.credencial_id}: {exc}")

    def _log(self, nivel: str, mensagem: str, detalhe: str | None = None):
        text = f"[API NFSe] {mensagem}"
        if nivel == "ERROR":
            log.error(text)
        elif nivel == "WARNING":
            log.warning(text)
        else:
            log.info(text)

        if self.job_id:
            try:
                self._log_repo.create(self.job_id, "API_NFSE", mensagem, nivel=nivel, detalhe=detalhe)
            except Exception as exc:
                log.warning(f"[API NFSe] Não foi possível gravar log no banco: {exc}")

    def _criar_sessao(self) -> requests.Session:
        cert_pem, key_pem = self._converter_pfx_para_pem()
        session = requests.Session()
        session.cert = (str(cert_pem), str(key_pem))
        session.verify = True
        session.headers.update(
            {
                "Accept": "application/json, application/xml, text/xml, */*",
                "User-Agent": "XMDL-NFSE-API/1.0",
                "Cache-Control": "no-cache",
            }
        )
        self._log("INFO", f"Sessão mTLS preparada com PEM temporário derivado de {Path(self.cert_path).name}")
        return session

    def _converter_pfx_para_pem(self) -> tuple[Path, Path]:
        cert_file = Path(self.cert_path)
        if not cert_file.exists():
            raise FileNotFoundError(f"Certificado não encontrado: {cert_file}")

        password = self.cert_password.encode("utf-8") if self.cert_password else None
        raw = cert_file.read_bytes()
        private_key, certificate, additional_certs = load_key_and_certificates(raw, password)
        if private_key is None or certificate is None:
            raise ValueError("Não foi possível extrair chave privada e certificado do arquivo PFX/P12")

        temp_root = Path(tempfile.mkdtemp(prefix="xmdl_nfse_api_"))
        cert_pem = temp_root / "client_cert.pem"
        key_pem = temp_root / "client_key.pem"

        cert_chunks = [certificate.public_bytes(Encoding.PEM)]
        for extra in additional_certs or []:
            cert_chunks.append(extra.public_bytes(Encoding.PEM))
        cert_pem.write_bytes(b"".join(cert_chunks))
        key_pem.write_bytes(
            private_key.private_bytes(
                encoding=Encoding.PEM,
                format=PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=NoEncryption(),
            )
        )
        self._pem_files.extend([cert_pem, key_pem])
        return cert_pem, key_pem

    def _persistir_metadata_resposta(self, nsu: int, response: requests.Response):
        headers = {k: v for k, v in response.headers.items()}
        payload = {
            "nsu": nsu,
            "url": response.request.url if response.request else None,
            "metodo": response.request.method if response.request else None,
            "status_code": response.status_code,
            "headers": headers,
            "timestamp": datetime.now().isoformat(),
        }
        meta_file = self.debug_dir / f"nsu_{nsu:08d}_meta.json"
        meta_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _persistir_corpo_bruto(self, nsu: int, response: requests.Response) -> Path:
        content_type = (response.headers.get("content-type") or "").lower()
        suffix = ".bin"
        if "json" in content_type:
            suffix = ".json"
        elif "xml" in content_type:
            suffix = ".xml"
        elif "text" in content_type:
            suffix = ".txt"

        raw_file = self.raw_dir / f"nsu_{nsu:08d}_raw{suffix}"
        raw_file.write_bytes(response.content or b"")
        return raw_file

    def _save_pretty_json(self, nsu: int, data: dict) -> Path:
        pretty_file = self.decoded_dir / f"nsu_{nsu:08d}.json"
        pretty_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return pretty_file

    def _decode_string_candidate(self, value: str) -> Optional[bytes]:
        if not value:
            return None
        text = value.strip()
        if not text:
            return None
        if text.startswith("<"):
            return text.encode("utf-8")
        try:
            raw = base64.b64decode(text, validate=False)
        except Exception:
            raw = text.encode("utf-8", errors="ignore")

        if raw.startswith(b"\x1f\x8b"):
            try:
                raw = gzip.decompress(raw)
            except Exception:
                pass
        return raw or None

    def _only_digits(self, value: Optional[str]) -> str:
        return "".join(ch for ch in (value or "") if ch.isdigit())

    def _same_company(self, doc_cnpj: str) -> bool:
        digits = self._only_digits(doc_cnpj)
        if not digits or not self._company_cnpj:
            return False
        if digits == self._company_cnpj:
            return True
        return bool(self._company_root and digits.startswith(self._company_root))

    def _infer_role(self, parsed: dict) -> str:
        emit_cnpj = self._only_digits((parsed.get("emitente") or {}).get("cnpj"))
        dest_cnpj = self._only_digits((parsed.get("destinatario") or {}).get("cnpj"))
        if self._same_company(emit_cnpj) and not self._same_company(dest_cnpj):
            return "prestada"
        if self._same_company(dest_cnpj) and not self._same_company(emit_cnpj):
            return "tomada"
        if self._same_company(emit_cnpj):
            return "prestada"
        if self._same_company(dest_cnpj):
            return "tomada"
        return "outra"

    def _is_within_period(self, data_emissao: datetime | None, data_inicial: datetime | None, data_final: datetime | None) -> bool:
        if data_emissao is None:
            return False
        if data_inicial and data_emissao < data_inicial:
            return False
        if data_final and data_emissao > data_final:
            return False
        return True

    def _safe_stem(self, value: str) -> str:
        text = (value or "").strip()
        cleaned = []
        for ch in text:
            if ch.isalnum() or ch in ("-", "_"):
                cleaned.append(ch)
        return "".join(cleaned)[:80] or "sem_chave"

    def _write_manifest(self):
        if not self._manifest_rows:
            return
        json_path = self.output_dir / "manifesto_api.json"
        csv_path = self.output_dir / "manifesto_api.csv"
        json_path.write_text(json.dumps(self._manifest_rows, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        fieldnames = [
            "nsu_consulta",
            "nsu_documento",
            "chave",
            "numero",
            "data_emissao",
            "valor_total",
            "emitente_cnpj",
            "emitente_nome",
            "destinatario_cnpj",
            "destinatario_nome",
            "papel_empresa",
            "tipo_documento",
            "periodo_ok",
            "tipo_ok",
            "matched",
            "arquivo_xml",
        ]
        with csv_path.open("w", newline="", encoding="utf-8-sig") as fp:
            writer = csv.DictWriter(fp, fieldnames=fieldnames)
            writer.writeheader()
            for row in self._manifest_rows:
                writer.writerow({key: row.get(key) for key in fieldnames})

    def _processar_lote_json(
        self,
        nsu_consulta: int,
        data: dict,
        tipo_nota: Optional[str],
        data_inicial: Optional[datetime],
        data_final: Optional[datetime],
        limite_documentos: int,
    ) -> dict:
        pretty_file = self._save_pretty_json(nsu_consulta, data)
        lote = data.get("LoteDFe") or []
        status_processamento = (data.get("StatusProcessamento") or "").strip().upper()
        self.max_lote_retorno = max(self.max_lote_retorno, len(lote))

        if not isinstance(lote, list):
            self.avisos.append(f"NSU consulta {nsu_consulta}: campo LoteDFe inesperado")
            self._log("WARNING", f"NSU consulta {nsu_consulta}: campo LoteDFe inesperado", detalhe=f"arquivo={pretty_file}")
            return {"pretty_path": pretty_file, "processados": 0, "matched": 0, "ultimo_nsu": None}

        if status_processamento and status_processamento != "DOCUMENTOS_LOCALIZADOS":
            self._log(
                "INFO",
                f"NSU consulta {nsu_consulta}: status {status_processamento}",
                detalhe=f"documentos_no_lote={len(lote)} | arquivo={pretty_file}",
            )

        novos_itens = []
        for item in lote:
            try:
                item_nsu = int(item.get("NSU") or 0)
            except Exception:
                item_nsu = 0
            if item_nsu <= max(0, int(nsu_consulta)):
                continue
            if item_nsu in self._item_nsu_processados:
                continue
            novos_itens.append((item_nsu, item))

        novos_itens.sort(key=lambda pair: pair[0])
        if limite_documentos > 0:
            novos_itens = novos_itens[:limite_documentos]

        if not novos_itens:
            self._log(
                "INFO",
                f"NSU consulta {nsu_consulta}: lote sem novos documentos aproveitáveis",
                detalhe=f"documentos_no_lote={len(lote)} | arquivo={pretty_file}",
            )
            return {"pretty_path": pretty_file, "processados": 0, "matched": 0, "ultimo_nsu": None}

        processados = 0
        matched = 0
        ultimo_nsu = None
        invalidos_lote = 0
        fora_filtro_lote = 0

        for item_nsu, item in novos_itens:
            xml_bytes = self._decode_string_candidate(item.get("ArquivoXml") or "")
            chave = (item.get("ChaveAcesso") or "").strip()
            safe_stem = f"nsu_{item_nsu:08d}_{self._safe_stem(chave or str(item_nsu))}"

            if not xml_bytes or b"<" not in xml_bytes[:200]:
                invalidos_lote += 1
                self.documentos_invalidos += 1
                self._item_nsu_processados.add(item_nsu)
                self.avisos.append(f"NSU documento {item_nsu}: ArquivoXml não pôde ser convertido em XML")
                continue

            xml_path = self.xml_todos_dir / f"{safe_stem}.xml"
            xml_path.write_bytes(xml_bytes)
            self.documentos_extraidos += 1
            self._item_nsu_processados.add(item_nsu)

            parsed = DocumentXMLParser.parse(xml_bytes)
            if not parsed:
                invalidos_lote += 1
                self.documentos_invalidos += 1
                shutil.copy2(xml_path, self.fora_filtro_dir / xml_path.name)
                continue

            papel_empresa = self._infer_role(parsed)
            if papel_empresa == "prestada":
                role_dir = self.xml_prestadas_dir
                tipo_documento = "NFS-e Prestada"
            elif papel_empresa == "tomada":
                role_dir = self.xml_tomadas_dir
                tipo_documento = "NFS-e Tomada"
            else:
                role_dir = self.xml_outros_dir
                tipo_documento = "NFS-e"
            shutil.copy2(xml_path, role_dir / xml_path.name)

            data_emissao = parsed.get("data_emissao")
            periodo_ok = self._is_within_period(data_emissao, data_inicial, data_final)
            tipo_ok = True if not tipo_nota else (papel_empresa == tipo_nota)
            matched_atual = bool(periodo_ok and tipo_ok)
            if matched_atual:
                destino = self.matched_prestadas_dir if papel_empresa == "prestada" else self.matched_tomadas_dir
                shutil.copy2(xml_path, destino / xml_path.name)
                matched += 1
                self.documentos_filtrados += 1
            else:
                fora_filtro_lote += 1
                shutil.copy2(xml_path, self.fora_filtro_dir / xml_path.name)

            self._manifest_rows.append(
                {
                    "nsu_consulta": nsu_consulta,
                    "nsu_documento": item_nsu,
                    "chave": parsed.get("chave") or chave,
                    "numero": parsed.get("numero") or "",
                    "data_emissao": data_emissao.isoformat() if isinstance(data_emissao, datetime) else "",
                    "valor_total": parsed.get("valor_total") or 0,
                    "emitente_cnpj": (parsed.get("emitente") or {}).get("cnpj") or "",
                    "emitente_nome": (parsed.get("emitente") or {}).get("nome") or "",
                    "destinatario_cnpj": (parsed.get("destinatario") or {}).get("cnpj") or "",
                    "destinatario_nome": (parsed.get("destinatario") or {}).get("nome") or "",
                    "papel_empresa": papel_empresa,
                    "tipo_documento": tipo_documento,
                    "periodo_ok": periodo_ok,
                    "tipo_ok": tipo_ok,
                    "matched": matched_atual,
                    "arquivo_xml": str(xml_path),
                }
            )

            processados += 1
            ultimo_nsu = item_nsu

        self._log(
            "INFO",
            f"NSU consulta {nsu_consulta}: lote tratado com {processados} novo(s) documento(s)",
            detalhe=(
                f"json={pretty_file} | lote_total={len(lote)} | novos={processados} | "
                f"matched={matched} | invalidos={invalidos_lote} | fora_filtro={fora_filtro_lote}"
            ),
        )
        return {
            "pretty_path": pretty_file,
            "processados": processados,
            "matched": matched,
            "ultimo_nsu": ultimo_nsu,
        }

    def _importar_xmls_filtrados(self) -> dict:
        diretorios = []
        if self.matched_prestadas_dir.exists() and any(self.matched_prestadas_dir.glob("*.xml")):
            diretorios.append(("prestadas", self.matched_prestadas_dir))
        if self.matched_tomadas_dir.exists() and any(self.matched_tomadas_dir.glob("*.xml")):
            diretorios.append(("tomadas", self.matched_tomadas_dir))

        if not diretorios:
            return {"imported": 0, "updated": 0, "invalid": 0, "duplicates": 0, "scanned": 0, "por_tipo": {}}

        totais = {"imported": 0, "updated": 0, "invalid": 0, "duplicates": 0, "scanned": 0, "por_tipo": {}}
        for label, target_dir in diretorios:
            summary = self._xml_import_service.import_company_directory(
                empresa_id=self.empresa_id,
                company_cnpj=self._company_cnpj,
                directory=target_dir,
                modified_after=self.started_at,
            )
            por_tipo = {
                "scanned": int(summary.scanned or 0),
                "imported": int(summary.imported or 0),
                "updated": int(summary.updated or 0),
                "invalid": int(summary.invalid or 0),
                "duplicates": int(summary.duplicates or 0),
            }
            totais["por_tipo"][label] = por_tipo
            totais["scanned"] += por_tipo["scanned"]
            totais["imported"] += por_tipo["imported"]
            totais["updated"] += por_tipo["updated"]
            totais["invalid"] += por_tipo["invalid"]
            totais["duplicates"] += por_tipo["duplicates"]

        self.documentos_importados += int(totais["imported"] or 0)
        self.documentos_atualizados += int(totais["updated"] or 0)
        self.documentos_invalidos += int(totais["invalid"] or 0)
        self.documentos_duplicados += int(totais["duplicates"] or 0)
        return totais

    def _build_summary_report(self, tipo_nota: Optional[str], data_inicial: Optional[datetime], data_final: Optional[datetime]) -> dict:
        rows = list(self._manifest_rows)
        totais = {
            "prestadas": sum(1 for r in rows if r.get("papel_empresa") == "prestada"),
            "tomadas": sum(1 for r in rows if r.get("papel_empresa") == "tomada"),
            "outras": sum(1 for r in rows if r.get("papel_empresa") not in {"prestada", "tomada"}),
            "filtradas": sum(1 for r in rows if r.get("matched")),
            "filtradas_prestadas": sum(1 for r in rows if r.get("matched") and r.get("papel_empresa") == "prestada"),
            "filtradas_tomadas": sum(1 for r in rows if r.get("matched") and r.get("papel_empresa") == "tomada"),
            "filtradas_outras": sum(1 for r in rows if r.get("matched") and r.get("papel_empresa") not in {"prestada", "tomada"}),
        }

        datas = []
        for row in rows:
            valor = row.get("data_emissao")
            if not valor:
                continue
            try:
                datas.append(datetime.fromisoformat(str(valor)))
            except Exception:
                continue

        periodo_localizado = "-"
        if datas:
            periodo_localizado = f"{min(datas).strftime('%d/%m/%Y')} a {max(datas).strftime('%d/%m/%Y')}"

        periodo_solicitado = "-"
        if data_inicial or data_final:
            ini = data_inicial.strftime('%d/%m/%Y') if isinstance(data_inicial, datetime) else '-'
            fim = data_final.strftime('%d/%m/%Y') if isinstance(data_final, datetime) else '-'
            periodo_solicitado = f"{ini} a {fim}"

        scope_label = {
            None: 'todos',
            'prestada': 'prestadas/saídas',
            'tomada': 'tomadas/entradas',
        }.get(tipo_nota, tipo_nota or 'todos')

        resumo = {
            "tipo_filtro": scope_label,
            "periodo_solicitado": periodo_solicitado,
            "periodo_localizado": periodo_localizado,
            "totais": totais,
            "nsu_consultado_de": min((int(r.get("nsu_documento") or 0) for r in rows), default=0),
            "nsu_consultado_ate": max((int(r.get("nsu_documento") or 0) for r in rows), default=0),
        }

        txt_path = self.output_dir / "resumo_periodo_api.txt"
        json_path = self.output_dir / "resumo_periodo_api.json"
        linhas = [
            f"Tipo filtrado: {scope_label}",
            f"Período solicitado: {periodo_solicitado}",
            f"Período localizado nos XMLs: {periodo_localizado}",
            f"NSU documentos: {resumo['nsu_consultado_de']} a {resumo['nsu_consultado_ate']}",
            f"Prestadas/saídas: {totais['prestadas']}",
            f"Tomadas/entradas: {totais['tomadas']}",
            f"Outras: {totais['outras']}",
            f"Filtradas no período/tipo: {totais['filtradas']}",
            f"Filtradas prestadas/saídas: {totais['filtradas_prestadas']}",
            f"Filtradas tomadas/entradas: {totais['filtradas_tomadas']}",
            f"Filtradas outras: {totais['filtradas_outras']}",
        ]
        txt_path.write_text("\n".join(linhas), encoding="utf-8")
        json_path.write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
        resumo["arquivo_txt"] = str(txt_path)
        resumo["arquivo_json"] = str(json_path)
        self._summary_report = resumo
        return resumo

    def sincronizar_dfe(
        self,
        nsu_inicial: int = 0,
        max_documentos: int = 200,
        max_vazios_consecutivos: int = 1,
        delay_entre_requisicoes: float = 0.4,
        tipo_nota: Optional[str] = None,
        data_inicial: Optional[str | datetime] = None,
        data_final: Optional[str | datetime] = None,
        cursor_scope: str = "geral",
    ) -> dict:
        self.nsu_atual = max(0, int(nsu_inicial or 0))
        max_documentos = max(1, int(max_documentos or 100))
        tipo_nota = (tipo_nota or "").strip().lower() or None
        if isinstance(data_inicial, str) and data_inicial:
            data_inicial_dt = datetime.fromisoformat(data_inicial)
        else:
            data_inicial_dt = data_inicial if isinstance(data_inicial, datetime) else None
        if isinstance(data_final, str) and data_final:
            data_final_dt = datetime.fromisoformat(data_final).replace(hour=23, minute=59, second=59, microsecond=999999)
        else:
            data_final_dt = data_final if isinstance(data_final, datetime) else None

        vazios = 0
        self._persistir_proximo_nsu(self.nsu_atual, lote=max_documentos, scope=cursor_scope)
        self._emit_progress(2, f"API NFSe: preparando certificado e conexão mTLS a partir do NSU {self.nsu_atual}...")
        self._atualizar_job(status="EXECUTANDO", inicio_em=datetime.utcnow(), total_baixado=0, total_erros=0)

        try:
            while self.documentos_inspecionados < max_documentos:
                nsu_consulta = self.nsu_atual
                restante = max_documentos - self.documentos_inspecionados
                progresso = min(95, 5 + int((self.documentos_inspecionados / max(1, max_documentos)) * 90))
                self._emit_progress(
                    progresso,
                    f"API NFSe: consultando NSU base {nsu_consulta} no ADN (inspecionados {self.documentos_inspecionados}/{max_documentos})...",
                )
                url = f"{self.url_base}/contribuintes/DFe/{nsu_consulta}"
                self._log("INFO", f"Consultando endpoint {url}")
                self.consultas_api += 1

                try:
                    response = self.session.get(url, timeout=(20, 90))
                except requests.exceptions.SSLError as exc:
                    msg = f"Erro SSL/mTLS ao consultar NSU {nsu_consulta}: {exc}"
                    self.erros.append(msg)
                    self._log("ERROR", msg)
                    break
                except requests.exceptions.RequestException as exc:
                    msg = f"Erro de rede ao consultar NSU {nsu_consulta}: {exc}"
                    self.erros.append(msg)
                    self._log("ERROR", msg)
                    break

                self._persistir_metadata_resposta(nsu_consulta, response)
                raw_path = self._persistir_corpo_bruto(nsu_consulta, response)
                self._log(
                    "INFO",
                    f"NSU base {nsu_consulta} respondeu HTTP {response.status_code}",
                    detalhe=f"content-type={response.headers.get('content-type')} | arquivo_bruto={raw_path}",
                )

                if response.status_code == 200:
                    self.respostas_salvas += 1
                    decoded_path = None
                    try:
                        data = response.json()
                        process_result = self._processar_lote_json(
                            nsu_consulta=nsu_consulta,
                            data=data,
                            tipo_nota=tipo_nota,
                            data_inicial=data_inicial_dt,
                            data_final=data_final_dt,
                            limite_documentos=restante,
                        )
                        decoded_path = process_result.get("pretty_path")
                    except Exception as exc:
                        self.avisos.append(f"NSU base {nsu_consulta}: falha ao tratar JSON ({exc})")
                        self._log("WARNING", f"NSU base {nsu_consulta}: falha ao tratar JSON", detalhe=str(exc))
                        process_result = {"processados": 0, "matched": 0, "ultimo_nsu": None}

                    processados = int(process_result.get("processados") or 0)
                    ultimo_nsu = process_result.get("ultimo_nsu")
                    if processados <= 0 or ultimo_nsu is None:
                        vazios += 1
                        self._log(
                            "INFO",
                            f"NSU base {nsu_consulta}: nenhum novo documento aproveitável. Sequência vazia {vazios}/{max_vazios_consecutivos}",
                            detalhe=f"bruto={raw_path} | decodificado={decoded_path}",
                        )
                        if vazios >= max_vazios_consecutivos:
                            break
                        self.nsu_atual = max(self.nsu_atual + 1, nsu_consulta + 1)
                        self._persistir_proximo_nsu(self.nsu_atual, lote=max_documentos, scope=cursor_scope)
                        time.sleep(max(0.0, float(delay_entre_requisicoes or 0.0)))
                        continue

                    vazios = 0
                    self.documentos_inspecionados += processados
                    self.nsu_atual = int(ultimo_nsu)
                    self._persistir_proximo_nsu(self.nsu_atual, lote=max_documentos, scope=cursor_scope)
                    self._atualizar_job(total_baixado=self.documentos_filtrados)
                    self._emit_progress(
                        min(95, 5 + int((self.documentos_inspecionados / max(1, max_documentos)) * 90)),
                        (
                            f"API NFSe: lote processado. Novos XMLs {processados}, filtrados {self.documentos_filtrados}, "
                            f"último NSU salvo {self.nsu_atual}."
                        ),
                    )
                    time.sleep(max(0.0, float(delay_entre_requisicoes or 0.0)))
                    continue

                if response.status_code == 404:
                    vazios += 1
                    self._log("INFO", f"NSU base {nsu_consulta} não localizado (404). Sequência vazia {vazios}/{max_vazios_consecutivos}")
                    self.nsu_atual = max(self.nsu_atual + 1, nsu_consulta + 1)
                    self._persistir_proximo_nsu(self.nsu_atual, lote=max_documentos, scope=cursor_scope)
                    if vazios >= max_vazios_consecutivos:
                        break
                    continue

                if response.status_code in (401, 403):
                    msg = (
                        f"A API rejeitou o acesso no NSU base {nsu_consulta} com HTTP {response.status_code}. "
                        "Isso normalmente indica problema de certificado, mTLS ou permissão do contribuinte."
                    )
                    self.erros.append(msg)
                    self._log("ERROR", msg, detalhe=response.text[:1000])
                    break

                if response.status_code == 429:
                    self._log("WARNING", f"Rate limit no NSU base {nsu_consulta}; aguardando 3 segundos para nova tentativa.")
                    time.sleep(3)
                    continue

                if response.status_code >= 500:
                    msg = f"Servidor da API retornou {response.status_code} no NSU base {nsu_consulta}"
                    self.erros.append(msg)
                    self._log("ERROR", msg, detalhe=response.text[:1000])
                    break

                msg = f"Resposta inesperada no NSU base {nsu_consulta}: HTTP {response.status_code}"
                self.erros.append(msg)
                self._log("ERROR", msg, detalhe=response.text[:1000])
                break

            self._write_manifest()
            resumo_periodo = self._build_summary_report(tipo_nota, data_inicial_dt, data_final_dt)
            import_summary = self._importar_xmls_filtrados()

            success = self.documentos_filtrados > 0 and not self.erros
            if success:
                final_message = (
                    f"Sincronização via API concluída com {self.documentos_filtrados} XML(s) no filtro, "
                    f"{self.documentos_importados} importado(s) e {self.documentos_atualizados} atualizado(s)."
                )
            elif self.documentos_extraidos > 0:
                final_message = (
                    f"Sincronização via API concluiu parcialmente: {self.documentos_extraidos} XML(s) extraído(s), "
                    f"{self.documentos_filtrados} no filtro e {len(self.erros)} erro(s)."
                )
            else:
                final_message = "A API respondeu, mas nenhum XML utilizável foi extraído nesta execução."

            status = "CONCLUIDO" if success else ("PARCIAL" if self.documentos_extraidos else "ERRO")
            self._atualizar_job(
                status=status,
                fim_em=datetime.utcnow(),
                total_baixado=self.documentos_filtrados,
                total_erros=len(self.erros),
                log_resumo=final_message,
            )
            self._emit_progress(100 if self.documentos_extraidos else 0, final_message)

            self._persistir_proximo_nsu(self.nsu_atual, lote=max_documentos, scope=cursor_scope)
            return {
                "sucesso": success,
                "parcial": bool(self.documentos_extraidos and self.erros),
                "mensagem": final_message,
                "documentos_salvos": self.documentos_extraidos,
                "documentos_extraidos": self.documentos_extraidos,
                "documentos_filtrados": self.documentos_filtrados,
                "documentos_inspecionados": self.documentos_inspecionados,
                "consultas_api": self.consultas_api,
                "respostas_salvas": self.respostas_salvas,
                "importados": self.documentos_importados,
                "atualizados": self.documentos_atualizados,
                "invalidos": self.documentos_invalidos,
                "duplicados": self.documentos_duplicados,
                "nsu_inicial": nsu_inicial,
                "nsu_final": self.nsu_atual,
                "pasta_saida": str(self.output_dir),
                "pasta_debug": str(self.debug_dir),
                "pasta_xml": str(self.xml_dir),
                "pasta_matched": str(self.matched_dir),
                "manifesto": str(self.output_dir / "manifesto_api.csv"),
                "cursor_scope": cursor_scope,
                "resumo_periodo": resumo_periodo,
                "ambiente": self.ambiente,
                "erros": list(self.erros),
                "avisos": list(self.avisos),
                "max_lote_retorno": self.max_lote_retorno,
                "resumo_importacao": import_summary,
            }
        finally:
            self.close()

    def _atualizar_job(self, **kwargs):
        if not self.job_id:
            return
        try:
            self._job_repo.update(self.job_id, **kwargs)
        except Exception as exc:
            log.warning(f"[API NFSe] Não foi possível atualizar job {self.job_id}: {exc}")
