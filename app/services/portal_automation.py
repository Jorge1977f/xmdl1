"""Automação do Portal Contribuinte NFS-e com fluxo robusto de filtro e download."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote
import json
import re
import threading
import zipfile

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from app.db import (
    CredencialRepository,
    EmpresaRepository,
    JobDownloadRepository,
    LogEventoRepository,
    get_db_session,
)
from app.services.xml_import_service import XMLImportService, ImportSummary
from app.services.download_checkpoint import DownloadCheckpoint
from app.utils.logger import log
from config.settings import PLAYWRIGHT_NAVIGATION_TIMEOUT, DOWNLOADS_DIR, DEFAULT_NFSE_CONTRIBUINTE_URL


class JobCancelledError(Exception):
    """Sinaliza cancelamento solicitado pelo usuário."""


@dataclass
class JobExecutionSummary:
    success: bool
    message: str
    job_id: int
    empresa_nome: str
    download_dir: str
    opened_portal: bool = False
    login_attempted: bool = False
    login_selector: str = ""
    files_scanned: int = 0
    files_imported: int = 0
    files_updated: int = 0
    files_invalid: int = 0
    duplicates: int = 0
    files_pdf_official: int = 0
    errors: list[str] = field(default_factory=list)
    debug_dir: str = ""
    debug_log_file: str = ""


class PortalAutomationService:
    """Executa um job de download abrindo o portal e importando os XMLs."""

    _cancel_events: dict[int, threading.Event] = {}

    USER_SELECTORS = [
        'input[type="email"]',
        'input[name*="login" i]',
        'input[name*="usuario" i]',
        'input[name*="user" i]',
        'input[id*="login" i]',
        'input[id*="usuario" i]',
        'input[id*="user" i]',
        'input[type="text"]',
    ]
    PASS_SELECTORS = [
        'input[type="password"]',
        'input[name*="senha" i]',
        'input[id*="senha" i]',
        'input[name*="password" i]',
        'input[id*="password" i]',
    ]
    SUBMIT_SELECTORS = [
        'button[type="submit"]',
        'input[type="submit"]',
        'button:has-text("Entrar")',
        'button:has-text("Acessar")',
        'button:has-text("Login")',
        'button:has-text("Continuar")',
    ]
    CERTIFICATE_SELECTORS = [
        'img[alt*="Certificado" i]',
        'img[src*="cert" i]',
        'text="Certificado Digital"',
        'a:has-text("Certificado")',
        'button:has-text("Certificado Digital")',
    ]
    NFSE_ROW_MENU_SELECTORS = [
        'button[aria-haspopup="menu"]',
        'button[aria-haspopup="true"]',
        'button.dropdown-toggle',
        '.dropdown-toggle',
        'button:has(i.fa-ellipsis-v)',
        'a:has(i.fa-ellipsis-v)',
        'span:has(i.fa-ellipsis-v)',
        'div:has(i.fa-ellipsis-v)',
        'button:has(i.fa-ellipsis-vertical)',
        'a:has(i.fa-ellipsis-vertical)',
        'span:has(i.fa-ellipsis-vertical)',
        'div:has(i.fa-ellipsis-vertical)',
        'i.fa-ellipsis-v',
        'i.fa-ellipsis-vertical',
        'i[class*="ellipsis"]',
        'svg[class*="ellipsis"]',
        'span[title*="ações" i]',
        'div[title*="ações" i]',
        '[data-bs-toggle="dropdown"]',
        '[data-toggle="dropdown"]',
        'button.btn-link',
        'a.btn-link',
        'button:has-text("⋮")',
        'a:has-text("⋮")',
        'span:has-text("⋮")',
        'button:has(svg)',
        'a:has(svg)',
        'span:has(svg)',
        '[title*="Ações" i]',
        'button[title*="ações" i]',
        'a[title*="ações" i]',
        '[aria-label*="ações" i]',
        '[aria-label*="menu" i]',
        '[aria-label*="mais" i]',
    ]
    NFSE_DOWNLOAD_MENU_SELECTORS = [
        'a:has-text("Download XML")',
        'button:has-text("Download XML")',
        'a:has-text("Baixar XML")',
        'button:has-text("Baixar XML")',
        'a:has-text("XML")',
        'button:has-text("XML")',
        'a[href*="download" i]:has-text("XML")',
        'button[title*="Download" i]',
        'a[title*="Download" i]',
        'text=/download\\s*xml/i',
        'text=/baixar\\s*xml/i',
    ]
    NFSE_PDF_MENU_SELECTORS = [
        'a:has-text("DANFSe")',
        'button:has-text("DANFSe")',
        'a:has-text("DANFS-e")',
        'button:has-text("DANFS-e")',
        'a:has-text("PDF")',
        'button:has-text("PDF")',
        'a:has-text("Visualizar")',
        'button:has-text("Visualizar")',
        'a:has-text("Imprimir")',
        'button:has-text("Imprimir")',
        'a[title*="pdf" i]',
        'button[title*="pdf" i]',
        'text=/danf\\s*-?s?e/i',
        'text=/pdf/i',
        'text=/visualizar/i',
        'text=/imprimir/i',
    ]
    NEXT_PAGE_SELECTORS = [
        'a[aria-label*="próxima" i]',
        'button[aria-label*="próxima" i]',
        '[title*="próxima" i]',
        '[aria-label*="proxima" i]',
        '[title*="proxima" i]',
        'a:has-text("Próxima")',
        'button:has-text("Próxima")',
        'a:has-text(">")',
        'button:has-text(">")',
        'span:has-text(">")',
        'div:has-text(">")',
        'a:has-text("›")',
        'button:has-text("›")',
        'span:has-text("›")',
        'div:has-text("›")',
        'a:has-text("»")',
        'button:has-text("»")',
        'span:has-text("»")',
        'div:has-text("»")',
        'a[rel="next"]',
        'li.next a',
        '.pagination-next',
    ]

    PAGINATION_CONTAINERS = [
        'ul.pagination',
        'nav[aria-label*="pag" i]',
        '.pagination',
        '.pager',
        'div:has(> a:has-text("1"))',
    ]

    def __init__(self, progress_callback=None):
        self.session = get_db_session()
        self.job_repo = JobDownloadRepository(self.session)
        self.empresa_repo = EmpresaRepository(self.session)
        self.cred_repo = CredencialRepository(self.session)
        self.log_repo = LogEventoRepository(self.session)
        self.xml_import = XMLImportService(self.session)
        self._job_debug_contexts: dict[int, dict[str, Any]] = {}
        self._job_pdf_download_counts: dict[int, int] = {}
        self._job_import_summaries: dict[int, ImportSummary] = {}
        self._job_checkpoints: dict[int, DownloadCheckpoint] = {}
        self.progress_callback = progress_callback


    @classmethod
    def request_cancel(cls, job_id: int):
        event = cls._cancel_events.setdefault(job_id, threading.Event())
        event.set()

    @classmethod
    def clear_cancel_request(cls, job_id: int):
        cls._cancel_events.pop(job_id, None)

    @classmethod
    def is_cancel_requested(cls, job_id: int) -> bool:
        event = cls._cancel_events.get(job_id)
        return bool(event and event.is_set())

    def _raise_if_cancel_requested(self, job_id: int, stage: str = ''):
        if self.is_cancel_requested(job_id):
            stage_text = f" durante {stage}" if stage else ''
            self._log_job_event(job_id, 'PORTAL', f'Cancelamento solicitado pelo usuário{stage_text}.', nivel='WARNING')
            raise JobCancelledError('Download cancelado pelo usuário.')

    def _report_progress(self, percent: int, message: str):
        try:
            if self.progress_callback:
                self.progress_callback(max(0, min(100, int(percent))), message)
        except Exception as exc:
            log.warning(f"Falha ao enviar progresso do job: {exc}")

    def execute_job(self, job_id: int) -> JobExecutionSummary:
        job = self.job_repo.get_by_id(job_id)
        if not job:
            raise ValueError(f"Job {job_id} não encontrado")

        empresa = self.empresa_repo.get_by_id(job.empresa_id)
        if not empresa:
            raise ValueError(f"Empresa do job {job_id} não encontrada")

        portal = self.cred_repo.get_ativo_by_empresa(empresa.id, "PORTAL")
        cert = self.cred_repo.get_ativo_by_empresa(empresa.id, "CERTIFICADO")
        download_dir = self._resolve_download_dir(empresa.cnpj, job.tipo_documento, portal.downloads_dir if portal else None)

        summary = JobExecutionSummary(
            success=False,
            message="",
            job_id=job.id,
            empresa_nome=empresa.razao_social,
            download_dir=str(download_dir),
        )

        download_mode = self._extract_download_mode(job)
        download_pdf_official = download_mode == "XML_AND_PDF"

        if not portal:
            message = "Configure o acesso ao portal na tela de Configurações antes de executar."
            self._register_error(job.id, "PORTAL", message)
            self.job_repo.update(job.id, status="ERRO_CONFIGURACAO", log_resumo=message, total_erros=1)
            summary.message = message
            summary.errors.append(message)
            return summary

        portal_url = portal.portal_url or DEFAULT_NFSE_CONTRIBUINTE_URL

        if not cert or not cert.cert_path:
            message = "Configure o certificado digital na tela de Configurações antes de executar."
            self._register_error(job.id, "PORTAL", message)
            self.job_repo.update(job.id, status="ERRO_CONFIGURACAO", log_resumo=message, total_erros=1)
            summary.message = message
            summary.errors.append(message)
            return summary

        cert_path = Path(cert.cert_path)
        if not cert_path.exists():
            message = f"O certificado salvo não foi encontrado: {cert_path}. Reimporte o certificado na pasta interna do programa."
            self._register_error(job.id, "PORTAL", message)
            self.job_repo.update(job.id, status="ERRO_CONFIGURACAO", log_resumo=message, total_erros=1)
            summary.message = message
            summary.errors.append(message)
            return summary

        wait_seconds = int(portal.tempo_espera_login or 120)
        debug_context = self._prepare_job_debug_context(job.id, download_dir)
        summary.debug_dir = str(debug_context['dir'])
        summary.debug_log_file = str(debug_context['log_file'])
        self._job_import_summaries[job.id] = ImportSummary()
        # ✨ NOVO: Inicializar checkpoint para preservar downloads
        self._job_checkpoints[job.id] = DownloadCheckpoint(download_dir)
        self.clear_cancel_request(job.id)

        self.job_repo.update(job.id, status="PROCESSANDO", inicio_em=datetime.utcnow(), log_resumo="Iniciando automação do portal.")
        self._report_progress(5, "Preparando acesso ao portal e validando certificado...")
        self._log_job_event(
            job.id,
            "PORTAL",
            f"Abrindo portal {portal_url}",
            detalhe=(
                f"Pasta de download: {download_dir}\n"
                f"Pasta debug: {summary.debug_dir}\n"
                f"Arquivo debug: {summary.debug_log_file}\n"
                f"Tipo documento: {job.tipo_documento}\n"
                f"Modo download: {download_mode}\n"
                f"Período: {job.data_inicial.strftime('%d/%m/%Y')} a {job.data_final.strftime('%d/%m/%Y')}"
            ),
        )

        start_mark = datetime.utcnow()
        self._report_progress(15, "Abrindo portal da NFS-e...")
        try:
            result = self._run_browser_session(
                portal_url=portal_url,
                login=portal.login or "",
                senha=portal.senha or "",
                download_dir=download_dir,
                wait_seconds=wait_seconds,
                headless=bool(portal.navegador_headless),
                modo_login=(portal.modo_login or "MANUAL_ASSISTIDO"),
                certificado_configurado=bool(cert and cert.cert_path),
                download_pdf_official=download_pdf_official,
                job=job,
            )
            summary.opened_portal = True
            self._report_progress(35, "Portal carregado. Aplicando período e iniciando consulta...")
            summary.login_attempted = result["login_attempted"]
            summary.login_selector = result.get("login_selector", "")
            if result.get("message"):
                self._log_job_event(job.id, "PORTAL", result["message"])
        except JobCancelledError as exc:
            message = str(exc)
            self.job_repo.update(job.id, status="CANCELADO", fim_em=datetime.utcnow(), log_resumo=message)
            summary.message = message
            summary.errors.append(message)
            return summary
        except PlaywrightTimeoutError as exc:
            message = f"Tempo excedido ao abrir o portal: {exc}"
            self._register_error(job.id, "PORTAL", message)
            self.job_repo.update(job.id, status="ERRO_LOGIN", fim_em=datetime.utcnow(), total_erros=1, log_resumo=message)
            summary.message = message
            summary.errors.append(message)
            return summary
        except PlaywrightError as exc:
            message = f"Falha no Playwright: {exc}. Rode 'python -m playwright install chromium'."
            self._register_error(job.id, "PORTAL", message)
            self.job_repo.update(job.id, status="ERRO_LOGIN", fim_em=datetime.utcnow(), total_erros=1, log_resumo=message)
            summary.message = message
            summary.errors.append(message)
            return summary
        except Exception as exc:
            message = f"Erro inesperado na automação: {exc}"
            self._register_error(job.id, "PORTAL", message)
            self.job_repo.update(job.id, status="ERRO_LOGIN", fim_em=datetime.utcnow(), total_erros=1, log_resumo=message)
            summary.message = message
            summary.errors.append(message)
            return summary

        self._report_progress(96, "Consolidando XMLs importados durante os períodos...")
        imported = self._job_import_summaries.get(job.id, ImportSummary())
        summary.files_scanned = imported.scanned
        summary.files_imported = imported.imported
        summary.files_updated = imported.updated
        summary.files_invalid = imported.invalid
        summary.duplicates = imported.duplicates

        total_baixado = imported.imported + imported.updated
        total_erros = imported.invalid
        summary.files_pdf_official = self._job_pdf_download_counts.get(job.id, 0)
        if total_baixado > 0:
            message = f"Portal aberto e {total_baixado} XML(s) importado(s) para {empresa.razao_social}."
            if download_pdf_official:
                message += f" PDFs oficiais salvos: {summary.files_pdf_official}."
            status = "CONCLUIDO"
            success = True
        else:
            message = (
                "Portal aberto, mas nenhum XML novo foi localizado na pasta monitorada. "
                "Confira os logs do job; o portal do contribuinte mudou o menu de ações e o fluxo foi reforçado."
            )
            if download_pdf_official and summary.files_pdf_official:
                message += f" PDFs oficiais salvos: {summary.files_pdf_official}."
            status = "SEM_XML"
            success = False

        self.job_repo.update(
            job.id,
            status=status,
            fim_em=datetime.utcnow(),
            total_encontrado=imported.scanned,
            total_baixado=total_baixado,
            total_erros=total_erros,
            log_resumo=message,
        )
        self._log_job_event(job.id, "IMPORTADOR_XML", message)

        self._report_progress(100, "Processo concluído.")
        summary.success = success
        summary.message = message
        self._job_pdf_download_counts.pop(job.id, None)
        self._job_import_summaries.pop(job.id, None)
        self.clear_cancel_request(job.id)
        return summary

    def _run_browser_session(
        self,
        portal_url: str,
        login: str,
        senha: str,
        download_dir: Path,
        wait_seconds: int,
        headless: bool,
        modo_login: str,
        certificado_configurado: bool,
        download_pdf_official: bool,
        job,
    ) -> dict[str, Any]:
        download_dir.mkdir(parents=True, exist_ok=True)
        certificate_assisted_mode = modo_login != "LOGIN_SENHA" and certificado_configurado
        temporary_visible_browser = headless and certificate_assisted_mode
        effective_headless = headless and not temporary_visible_browser
        launch_args = ['--start-maximized'] if not effective_headless else None

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=effective_headless,
                downloads_path=str(download_dir),
                args=launch_args,
            )
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            try:
                self._raise_if_cancel_requested(job.id, 'abertura do portal')
                page.goto(portal_url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_NAVIGATION_TIMEOUT)
                if not effective_headless:
                    self._set_browser_window_state(browser, 'maximized', job.id)
                self._log_job_event(
                    job.id,
                    "PORTAL",
                    "Página inicial do portal carregada.",
                    detalhe=f"URL atual: {page.url}",
                )
                self._capture_page_artifacts(page, job.id, "01_portal_aberto")
                result = {
                    "login_attempted": False,
                    "login_selector": "",
                    "message": "Portal aberto com sucesso.",
                }

                if temporary_visible_browser:
                    self._log_job_event(
                        job.id,
                        "PORTAL",
                        "Navegador oculto solicitado com certificado digital.",
                        detalhe=(
                            "O navegador foi aberto visível temporariamente para permitir a seleção do certificado. "
                            "Após o login, a janela será minimizada para continuar a automação."
                        ),
                    )

                if modo_login == "LOGIN_SENHA" and login and senha:
                    login_selector = self._fill_first_visible(page, self.USER_SELECTORS, login)
                    password_selector = self._fill_first_visible(page, self.PASS_SELECTORS, senha)
                    if login_selector and password_selector:
                        result["login_attempted"] = True
                        result["login_selector"] = login_selector
                        submit_selector = self._click_first_visible(page, self.SUBMIT_SELECTORS)
                        self._log_job_event(
                            job.id,
                            "PORTAL",
                            "Campos de login encontrados para tentativa automática.",
                            detalhe=(
                                f"Campo usuário: {login_selector}\n"
                                f"Campo senha: {password_selector}\n"
                                f"Botão submit: {submit_selector or 'não localizado'}"
                            ),
                        )
                        result["message"] = (
                            "Tentativa automática de login executada"
                            f"{' com clique em botão de envio' if submit_selector else ' sem botão detectado; finalize manualmente'}"
                            "."
                        )
                    else:
                        self._log_job_event(
                            job.id,
                            "PORTAL",
                            "Campos de login não detectados automaticamente.",
                            detalhe=(
                                f"Campo usuário localizado: {'sim' if login_selector else 'não'}\n"
                                f"Campo senha localizado: {'sim' if password_selector else 'não'}"
                            ),
                        )
                        result["message"] = "Campos de login não detectados automaticamente; finalize o acesso manualmente no navegador aberto."
                else:
                    if certificado_configurado:
                        clicked = self._click_first_visible(page, self.CERTIFICATE_SELECTORS)
                        self._log_job_event(
                            job.id,
                            "PORTAL",
                            "Fluxo de certificado digital iniciado.",
                            detalhe=f"Botão de certificado acionado: {clicked or 'não localizado'}",
                        )
                        result["message"] = (
                            "Portal aberto em modo certificado assistido. "
                            + ("Clique/seleção do certificado disparado automaticamente. " if clicked else "")
                            + (
                                "Selecione o certificado; depois o sistema continuará automaticamente e minimizará o navegador."
                                if temporary_visible_browser
                                else "Selecione o certificado na janela do navegador e aguarde o restante da automação."
                            )
                        )
                    else:
                        self._log_job_event(job.id, "PORTAL", "Fluxo em modo manual assistido; aguardando ação do usuário.")
                        result["message"] = "Portal aberto em modo manual assistido. Faça login e aguarde o restante da automação."

                downloaded = 0
                if self._is_nfse_contribuinte_portal(portal_url):
                    downloaded, browser, context, page = self._execute_nfse_portal_flow(
                        playwright,
                        page,
                        browser,
                        context,
                        job,
                        wait_seconds,
                        download_dir,
                        download_pdf_official,
                        relaunch_headless=temporary_visible_browser,
                    )
                    result["message"] = (
                        f"Fluxo do Portal Contribuinte NFS-e executado. Downloads concluídos: {downloaded}."
                        if downloaded
                        else "Acesso ao Portal Contribuinte concluído, mas nenhum XML foi baixado no período informado."
                    )
                else:
                    page.wait_for_timeout(max(wait_seconds, 5) * 1000)

                self._capture_page_artifacts(page, job.id, "99_fim_sessao")
                return result
            except Exception as exc:
                self._capture_page_artifacts(page, job.id, "98_erro_sessao")
                self._log_job_event(
                    job.id,
                    "PORTAL",
                    f"Erro dentro da sessão do navegador: {exc}",
                    nivel="ERROR",
                    detalhe=f"URL no erro: {getattr(page, 'url', '')}",
                )
                raise
            finally:
                try:
                    context.close()
                except Exception:
                    pass
                try:
                    browser.close()
                except Exception:
                    pass

    def _prepare_job_debug_context(self, job_id: int, download_dir: Path) -> dict[str, Any]:
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        debug_dir = download_dir / '_debug' / f'job_{job_id}_{timestamp}'
        debug_dir.mkdir(parents=True, exist_ok=True)
        log_file = debug_dir / 'portal_debug.log'
        if not log_file.exists():
            log_file.write_text(
                f"=== DEBUG PORTAL JOB {job_id} ===\nCriado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n",
                encoding='utf-8',
            )
        context = {'dir': debug_dir, 'log_file': log_file}
        self._job_debug_contexts[job_id] = context
        return context

    def _get_job_debug_context(self, job_id: int) -> dict[str, Any] | None:
        return self._job_debug_contexts.get(job_id)

    def _write_job_debug_line(self, job_id: int, line: str):
        ctx = self._get_job_debug_context(job_id)
        if not ctx:
            return
        try:
            with open(ctx['log_file'], 'a', encoding='utf-8') as fp:
                fp.write(line.rstrip() + '\n')
        except Exception as exc:
            log.warning(f'Não foi possível escrever no log detalhado do job {job_id}: {exc}')

    def _log_job_event(self, job_id: int, origem: str, mensagem: str, nivel: str = 'INFO', detalhe: str | None = None):
        self.log_repo.create(job_id, origem, mensagem, nivel=nivel, detalhe=detalhe)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        line = f'[{timestamp}] [{nivel}] [{origem}] {mensagem}'
        if detalhe:
            line += f'\n{detalhe}'
        self._write_job_debug_line(job_id, line + '\n')
        try:
            log.log(nivel.upper(), f'[JOB {job_id}] [{origem}] {mensagem}')
        except Exception:
            log.info(f'[JOB {job_id}] [{origem}] {mensagem}')

    def _capture_page_artifacts(self, page, job_id: int, name: str):
        ctx = self._get_job_debug_context(job_id)
        if not ctx or page is None:
            return
        safe_name = re.sub(r'[^a-zA-Z0-9_\-]+', '_', name).strip('_') or 'pagina'
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        png_path = ctx['dir'] / f'{stamp}_{safe_name}.png'
        html_path = ctx['dir'] / f'{stamp}_{safe_name}.html'
        meta_path = ctx['dir'] / f'{stamp}_{safe_name}.json'
        try:
            page.screenshot(path=str(png_path), full_page=True)
        except Exception as exc:
            self._write_job_debug_line(job_id, f'[WARN] Falha ao salvar screenshot {png_path.name}: {exc}')
        try:
            html_path.write_text(page.content(), encoding='utf-8')
        except Exception as exc:
            self._write_job_debug_line(job_id, f'[WARN] Falha ao salvar HTML {html_path.name}: {exc}')
        try:
            meta = {
                'capturado_em': datetime.now().isoformat(),
                'url': getattr(page, 'url', ''),
                'title': page.title(),
            }
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as exc:
            self._write_job_debug_line(job_id, f'[WARN] Falha ao salvar metadados {meta_path.name}: {exc}')
        self._write_job_debug_line(job_id, f'[DEBUG] Snapshot salvo: {png_path.name}, {html_path.name}, {meta_path.name}')

    def _safe_row_text(self, row) -> str:
        try:
            text = row.inner_text(timeout=1000) or ''
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:500]
        except Exception:
            return ''

    def _describe_locator(self, locator) -> str:
        if locator is None:
            return 'locator=None'
        for getter in (
            lambda: locator.inner_text(timeout=500),
            lambda: locator.get_attribute('title'),
            lambda: locator.get_attribute('aria-label'),
            lambda: locator.get_attribute('href'),
            lambda: locator.get_attribute('class'),
        ):
            try:
                value = getter()
                if value:
                    return re.sub(r'\s+', ' ', str(value)).strip()[:300]
            except Exception:
                continue
        return 'sem descrição visível'

    def _execute_nfse_portal_flow(self, playwright, page, browser, context, job, wait_seconds: int, download_dir: Path, download_pdf_official: bool, relaunch_headless: bool = False):
        deadline = max(wait_seconds, 15) * 1000
        self._log_job_event(job.id, "PORTAL", "Aguardando conclusão do login/acesso ao portal.", detalhe=f"Tempo máximo de espera: {deadline // 1000}s")
        self._wait_for_nfse_login(page, deadline)
        self._log_job_event(job.id, "PORTAL", "Login/acesso concluído ou tempo de espera encerrado.", detalhe=f"URL após login: {page.url}")
        self._capture_page_artifacts(page, job.id, "02_pos_login")

        if relaunch_headless:
            switched = self._switch_nfse_session_to_headless(playwright, browser, context, page, download_dir, job)
            if switched is not None:
                browser, context, page = switched
            else:
                minimized = self._set_browser_window_state(browser, 'minimized', job.id)
                if minimized:
                    self._log_job_event(job.id, "PORTAL", "Navegador minimizado após a seleção do certificado.")
                else:
                    self._log_job_event(
                        job.id,
                        "PORTAL",
                        "Não foi possível ocultar o navegador automaticamente após o login.",
                        nivel="WARNING",
                    )

        downloaded = 0
        current_date = job.data_inicial
        while current_date <= job.data_final:
            self._raise_if_cancel_requested(job.id, 'processamento do período')
            period_start_mark = datetime.utcnow()
            period_end = min(current_date + timedelta(days=29), job.data_final)
            self._log_job_event(
                job.id,
                "PORTAL",
                f"Processando período: {current_date.strftime('%d/%m/%Y')} a {period_end.strftime('%d/%m/%Y')}",
            )

            target_url = self._build_nfse_target_url(page.url, job.tipo_documento, current_date, period_end)
            self._log_job_event(job.id, "PORTAL", f"Navegando para consulta filtrada: {target_url}")
            page.goto(target_url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_NAVIGATION_TIMEOUT)
            page.wait_for_timeout(3500)
            self._log_job_event(job.id, "PORTAL", "Página filtrada carregada.", detalhe=f"URL carregada: {page.url}")
            self._capture_page_artifacts(page, job.id, f"03_periodo_{current_date.strftime('%Y%m%d')}_{period_end.strftime('%Y%m%d')}")

            downloaded += self._download_nfse_results(page, job, download_dir, download_pdf_official)
            imported = self.xml_import.import_from_directory(
                empresa_id=job.empresa_id,
                tipo_documento=job.tipo_documento,
                directory=download_dir,
                modified_after=period_start_mark,
            )
            checkpoint = self._job_checkpoints.get(job.id)
            if checkpoint and imported.imported > 0:
                for xml_file in download_dir.glob('*.xml'):
                    checkpoint.mark_imported(xml_file.name)
            
            total = self._job_import_summaries.setdefault(job.id, ImportSummary())
            total.scanned += imported.scanned
            total.imported += imported.imported
            total.updated += imported.updated
            total.invalid += imported.invalid
            total.duplicates += imported.duplicates
            self._log_job_event(
                job.id,
                'IMPORTADOR_XML',
                f"Período {current_date.strftime('%d/%m/%Y')} a {period_end.strftime('%d/%m/%Y')} importado.",
                detalhe=(
                    f"Varridos: {imported.scanned} | Importados: {imported.imported} | "
                    f"Atualizados: {imported.updated} | Duplicados: {imported.duplicates} | Inválidos: {imported.invalid}"
                ),
            )
            self._report_progress(95, f"Importando XMLs do período {current_date.strftime('%d/%m')}...")
            current_date = (period_end + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

        return downloaded, browser, context, page

    def _switch_nfse_session_to_headless(self, playwright, browser, context, page, download_dir: Path, job):
        ctx = self._get_job_debug_context(job.id) or {}
        state_path = (ctx.get('dir') or download_dir) / 'storage_state_after_login.json'
        try:
            context.storage_state(path=str(state_path))
            current_url = page.url
            self._log_job_event(
                job.id,
                "PORTAL",
                "Login concluído; trocando o navegador visível por uma sessão oculta para continuar os downloads.",
                detalhe=f"URL preservada: {current_url}",
            )
        except Exception as exc:
            self._log_job_event(job.id, "PORTAL", f"Falha ao salvar a sessão após o login: {exc}", nivel="WARNING")
            return None

        try:
            new_browser = playwright.chromium.launch(
                headless=True,
                downloads_path=str(download_dir),
            )
            new_context = new_browser.new_context(accept_downloads=True, storage_state=str(state_path))
            new_page = new_context.new_page()
            new_page.goto(current_url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_NAVIGATION_TIMEOUT)
            new_page.wait_for_timeout(1500)
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass
            self._log_job_event(job.id, "PORTAL", "Sessão oculta iniciada com sucesso após a escolha do certificado.")
            self._capture_page_artifacts(new_page, job.id, "02b_reaberto_headless")
            return new_browser, new_context, new_page
        except Exception as exc:
            self._log_job_event(
                job.id,
                "PORTAL",
                f"Falha ao reabrir a sessão oculta após a escolha do certificado: {exc}",
                nivel="WARNING",
                detalhe="O sistema vai tentar continuar com a janela visível/minimizada.",
            )
            return None

    def _set_browser_window_state(self, browser, state: str, job_id: int | None = None) -> bool:
        try:
            session = browser.new_browser_cdp_session()
            payload = session.send('Browser.getWindowForTarget')
            window_id = payload.get('windowId')
            if not window_id:
                return False
            session.send('Browser.setWindowBounds', {
                'windowId': window_id,
                'bounds': {'windowState': state},
            })
            return True
        except Exception as exc:
            if job_id is not None:
                self._log_job_event(job_id, 'PORTAL', f'Falha ao alterar o estado da janela do navegador: {exc}', nivel='WARNING')
            return False

    def _wait_for_nfse_login(self, page, timeout_ms: int):
        try:
            page.wait_for_url(lambda url: 'EmissorNacional' in url and 'Login' not in url, timeout=timeout_ms)
        except Exception:
            page.wait_for_timeout(timeout_ms // 2)
        try:
            page.wait_for_selector('text="PORTAL CONTRIBUINTE"', timeout=8000)
        except Exception:
            pass

    def _build_nfse_target_url(self, current_url: str, tipo_documento: str, data_inicial, data_final) -> str:
        if '/EmissorNacional/' in current_url:
            base = current_url.split('/EmissorNacional/')[0].rstrip('/')
        else:
            base = current_url.split('/EmissorNacional')[0].rstrip('/')
        lower = (tipo_documento or '').lower()
        path = 'Notas/Emitidas' if ('saída' in lower or 'prestada' in lower or 'prestado' in lower) else 'Notas/Recebidas'
        di = data_inicial.strftime('%d/%m/%Y')
        df = data_final.strftime('%d/%m/%Y')
        return f"{base}/EmissorNacional/{path}?executar=1&busca=&datainicio={quote(di)}&datafim={quote(df)}"

    def _download_nfse_results(self, page, job, download_dir: Path, download_pdf_official: bool) -> int:
        page.wait_for_timeout(3000)
        try:
            if page.locator('text="Nenhum registro encontrado"').count() > 0:
                self._log_job_event(job.id, "PORTAL", "Nenhum registro retornado para o período informado no Portal Contribuinte NFS-e.")
                self._capture_page_artifacts(page, job.id, "04_sem_registros")
                return 0
        except Exception:
            pass

        downloaded = 0
        current_page = self._current_page_number(page) or 1
        visited_signatures: set[str] = set()

        while True:
            signature_before = self._page_signature(page)
            if signature_before in visited_signatures:
                self._log_job_event(
                    job.id,
                    "PORTAL",
                    "Paginação interrompida para evitar loop em página repetida.",
                    nivel="WARNING",
                    detalhe=f"Assinatura repetida: {signature_before}",
                )
                break
            visited_signatures.add(signature_before)

            self._log_job_event(job.id, "PORTAL", f"Analisando página {current_page} de resultados.")
            page_downloaded = self._download_from_current_page(page, job, download_dir, download_pdf_official, current_page=current_page)
            downloaded += page_downloaded

            if not self._go_to_next_page(page, job, current_page, signature_before):
                break

            page.wait_for_timeout(2500)
            current_page = self._current_page_number(page) or (current_page + 1)

        self._log_job_event(job.id, "PORTAL", f"Total de XMLs baixados neste período: {downloaded}")
        return downloaded

    def _download_from_current_page(self, page, job, download_dir: Path, download_pdf_official: bool, current_page: int = 1) -> int:
        downloaded = 0
        rows = page.locator('table tbody tr')
        row_count = rows.count()
        if row_count == 0:
            self._log_job_event(job.id, "PORTAL", "Nenhuma linha encontrada na tabela de notas.")
            return 0

        self._log_job_event(job.id, "PORTAL", f"Encontradas {row_count} nota(s) nesta página.")
        total_pages = self._estimate_total_pages(page, current_page)
        page_label = f"Página {current_page} de {total_pages}" if total_pages and total_pages >= current_page else f"Página {current_page}"
        self._report_progress(max(40, min(85, 40 + current_page * 5)), f"{page_label}: {row_count} nota(s) encontrada(s). Iniciando downloads...")
        self._capture_page_artifacts(page, job.id, "05_tabela_resultados")
        for idx in range(row_count):
            self._raise_if_cancel_requested(job.id, 'download das linhas da página')
            row = rows.nth(idx)
            try:
                downloaded += self._download_from_row(page, row, idx, row_count, job, download_dir, download_pdf_official, current_page=current_page)
            except Exception as exc:
                self._log_job_event(job.id, "PORTAL", f"Erro ao processar linha {idx + 1}: {exc}", nivel="ERROR")
        return downloaded

    def _download_from_row(self, page, row, idx: int, row_count: int, job, download_dir: Path, download_pdf_official: bool, current_page: int = 1) -> int:
        row_text = self._safe_row_text(row)
        self._log_job_event(
            job.id,
            "PORTAL",
            f"Processando linha {idx + 1}/{row_count}.",
            detalhe=f"Conteúdo da linha: {row_text or 'não foi possível ler o texto da linha'}",
        )
        page_ranges = {1: (45, 70), 2: (70, 80), 3: (80, 87), 4: (87, 92), 5: (92, 96)}
        start_pct, end_pct = page_ranges.get(current_page, (96, 98))
        progress_pct = start_pct + int(((idx + 1) / max(row_count, 1)) * (end_pct - start_pct))
        total_pages = self._estimate_total_pages(page, current_page)
        page_label = f"página {current_page} de {total_pages}" if total_pages and total_pages >= current_page else f"página {current_page}"
        self._report_progress(progress_pct, f"Baixando XMLs: {page_label}, item {idx + 1} de {row_count}...")

        situacao_filtro = self._extract_situacao_filtro(job)
        row_situacao = self._classify_row_situacao(row_text)
        if not self._row_matches_situacao_filter(row_text, situacao_filtro):
            self._log_job_event(
                job.id,
                'PORTAL',
                f"Linha {idx + 1} ignorada pelo filtro de situação.",
                detalhe=f"Filtro: {situacao_filtro} | Situação detectada: {row_situacao} | Linha: {row_text}",
            )
            return 0

        link = self._find_direct_download_link(row)
        if link is not None:
            self._log_job_event(
                job.id,
                "PORTAL",
                f"Link direto de download encontrado na linha {idx + 1}.",
                detalhe=f"Elemento: {self._describe_locator(link)}",
            )
            xml_count = self._trigger_download(page, link, download_dir, job, f"XML {idx + 1}/{row_count} baixado via link direto.", preferred_stem=self._preferred_file_stem(row_text, idx + 1))
            if download_pdf_official:
                self._log_job_event(job.id, "PORTAL", f"Linha {idx + 1}: modo XML + DANFSe ativo, mas o PDF oficial depende do menu da linha.", nivel="WARNING")
            return xml_count

        menu_button = self._find_row_menu_button(row)
        if menu_button is None:
            self._log_job_event(
                job.id,
                "PORTAL",
                f"Menu de ações não encontrado para a linha {idx + 1}.",
                detalhe=f"Linha: {row_text}",
            )
            self._capture_page_artifacts(page, job.id, f"06_linha_{idx + 1}_sem_menu")
            return 0

        self._log_job_event(
            job.id,
            "PORTAL",
            f"Menu de ações localizado para a linha {idx + 1}.",
            detalhe=f"Elemento do menu: {self._describe_locator(menu_button)}",
        )
        menu_button.scroll_into_view_if_needed(timeout=2000)
        menu_button.click(timeout=4000, force=True)
        page.wait_for_timeout(800)

        item = self._find_download_item(page, row)
        if item is None:
            self._log_job_event(
                job.id,
                "PORTAL",
                f"Opção de download/XML não encontrada para a linha {idx + 1}.",
                detalhe=f"Linha: {row_text}",
            )
            self._capture_page_artifacts(page, job.id, f"07_linha_{idx + 1}_sem_item_xml")
            self._close_open_menu(page)
            return 0

        self._log_job_event(
            job.id,
            "PORTAL",
            f"Opção de download localizada para a linha {idx + 1}.",
            detalhe=f"Elemento de download: {self._describe_locator(item)}",
        )
        preferred_stem = self._preferred_file_stem(row_text, idx + 1)
        count = self._trigger_download(page, item, download_dir, job, f"XML {idx + 1}/{row_count} baixado pelo menu da linha.", preferred_stem=preferred_stem)
        page.wait_for_timeout(500)

        if download_pdf_official:
            pdf_saved = self._try_download_official_pdf_from_row(page, row, idx, row_count, job, download_dir, preferred_stem)
            if pdf_saved:
                self._job_pdf_download_counts[job.id] = self._job_pdf_download_counts.get(job.id, 0) + 1

        return count

    def _extract_job_payload(self, job) -> dict[str, Any]:
        raw = (getattr(job, 'log_resumo', None) or '').strip()
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _extract_download_mode(self, job) -> str:
        payload = self._extract_job_payload(job)
        mode = (payload.get('download_mode') or '').strip().upper()
        return mode or 'XML_ONLY'

    def _extract_situacao_filtro(self, job) -> str:
        payload = self._extract_job_payload(job)
        value = (payload.get('situacao_filtro') or '').strip().lower()
        if 'cancel' in value:
            return 'CANCELADAS'
        if 'ativa' in value or 'válid' in value or 'valid' in value:
            return 'ATIVAS'
        return 'TODAS'

    def _classify_row_situacao(self, row_text: str) -> str:
        normalized = re.sub(r'\s+', ' ', (row_text or '').strip()).lower()
        cancel_tokens = [
            'cancelada', 'cancelado', 'cancelamento', 'nfse cancelada', 'nfs-e cancelada',
            'evento de cancelamento', 'situação cancelada', 'situacao cancelada',
        ]
        if any(token in normalized for token in cancel_tokens):
            return 'CANCELADA'
        return 'ATIVA'

    def _row_matches_situacao_filter(self, row_text: str, situacao_filtro: str) -> bool:
        situacao = self._classify_row_situacao(row_text)
        if situacao_filtro == 'CANCELADAS':
            return situacao == 'CANCELADA'
        if situacao_filtro == 'ATIVAS':
            return situacao != 'CANCELADA'
        return True

    def _find_direct_download_link(self, row):
        selectors = [
            'a[href*="download" i]',
            'a[href*="xml" i]',
            'button[title*="download" i]',
            'a[title*="download" i]',
            'text=/download\\s*xml/i',
        ]
        for selector in selectors:
            try:
                loc = row.locator(selector).first
                if loc.count() and loc.is_visible(timeout=500):
                    return loc
            except Exception:
                continue
        return None

    def _find_row_menu_button(self, row):
        for selector in self.NFSE_ROW_MENU_SELECTORS:
            try:
                locs = row.locator(selector)
                count = locs.count()
                if count > 0:
                    for i in range(count - 1, -1, -1):
                        candidate = locs.nth(i)
                        if candidate.is_visible(timeout=500):
                            return candidate
            except Exception:
                continue

        fallback_selectors = [
            'td:last-child button',
            'td:last-child a',
            'td:last-child span',
            'td:last-child div',
            'td:last-child i',
            'td:last-child svg',
            'td:last-child *',
            'button',
            'a',
            'span',
            'div',
            'i',
        ]
        for selector in fallback_selectors:
            try:
                locs = row.locator(selector)
                count = locs.count()
                if count > 0:
                    for i in range(count - 1, -1, -1):
                        candidate = locs.nth(i)
                        if candidate.is_visible(timeout=500):
                            return candidate
            except Exception:
                continue
        return None

    def _find_download_item(self, page, row):
        for selector in self.NFSE_DOWNLOAD_MENU_SELECTORS:
            try:
                loc = page.locator(selector).last
                if loc.count() and loc.is_visible(timeout=800):
                    return loc
            except Exception:
                continue

        menu_scopes = [
            page.locator('[role="menu"]'),
            page.locator('.dropdown-menu'),
            page.locator('.menu'),
        ]
        for scope in menu_scopes:
            try:
                if scope.count() > 0:
                    for selector in ['a', 'button', '[role="menuitem"]']:
                        candidates = scope.last.locator(selector)
                        for i in range(candidates.count()):
                            candidate = candidates.nth(i)
                            text = (candidate.inner_text(timeout=500) or '').strip().lower()
                            if 'xml' in text or 'download' in text or 'baixar' in text:
                                return candidate
            except Exception:
                continue

        try:
            anchors = row.locator('a, button')
            for i in range(anchors.count()):
                candidate = anchors.nth(i)
                text = (candidate.inner_text(timeout=500) or '').strip().lower()
                if 'xml' in text or 'download' in text or 'baixar' in text:
                    return candidate
        except Exception:
            pass
        return None

    def _trigger_download(self, page, clickable, download_dir: Path, job, success_message: str, preferred_stem: str | None = None) -> int:
        try:
            self._raise_if_cancel_requested(job.id, 'download do XML')
            self._log_job_event(job.id, "PORTAL", "Acionando clique de download.", detalhe=f"Elemento: {self._describe_locator(clickable)}")
            with page.expect_download(timeout=15000) as dl_info:
                clickable.click(force=True)
            download = dl_info.value
            filename = download.suggested_filename or f'nfse_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xml'
            target_path = self._unique_download_target(download_dir, filename, preferred_stem=preferred_stem)
            download.save_as(str(target_path))
            extracted = self._extract_if_zip(target_path, download_dir, job)
            if extracted:
                self._log_job_event(job.id, "PORTAL", f"Arquivo compactado extraído: {target_path.name} -> {extracted} XML(s).")
            self._log_job_event(job.id, "PORTAL", success_message, detalhe=f"Arquivo salvo: {target_path}")
            return max(extracted, 1)
        except Exception as exc:
            self._capture_page_artifacts(page, job.id, "08_falha_download")
            self._log_job_event(job.id, "PORTAL", f"Falha ao concluir download: {exc}", nivel="ERROR")
            return 0

    def _try_download_official_pdf_from_row(self, page, row, idx: int, row_count: int, job, download_dir: Path, preferred_stem: str | None) -> bool:
        try:
            menu_button = self._find_row_menu_button(row)
            if menu_button is None:
                self._log_job_event(job.id, "PORTAL", f"Linha {idx + 1}: menu não encontrado para baixar DANFSe oficial.", nivel="WARNING")
                return False
            try:
                menu_button.scroll_into_view_if_needed(timeout=2000)
            except Exception:
                pass
            menu_button.click(timeout=4000, force=True)
            page.wait_for_timeout(800)

            item = self._find_pdf_item(page, row)
            if item is None:
                self._log_job_event(job.id, "PORTAL", f"Linha {idx + 1}: opção de DANFSe/PDF oficial não encontrada; ficará disponível apenas o PDF gerado do XML.", nivel="WARNING")
                self._close_open_menu(page)
                return False

            saved_path = self._trigger_official_pdf_download(page, item, download_dir, job, preferred_stem or f'linha_{idx + 1}')
            page.wait_for_timeout(500)
            if saved_path:
                self._log_job_event(job.id, "PORTAL", f"DANFSe oficial {idx + 1}/{row_count} salvo.", detalhe=f"Arquivo salvo: {saved_path}")
                return True

            self._log_job_event(job.id, "PORTAL", f"Linha {idx + 1}: não foi possível salvar o DANFSe oficial; o sistema usará o PDF gerado do XML na visualização.", nivel="WARNING")
            return False
        finally:
            self._close_open_menu(page)

    def _find_pdf_item(self, page, row):
        for selector in self.NFSE_PDF_MENU_SELECTORS:
            try:
                loc = page.locator(selector).last
                if loc.count() and loc.is_visible(timeout=800):
                    text = (loc.inner_text(timeout=300) or '').strip().lower()
                    if 'xml' not in text or 'pdf' in text or 'danf' in text or 'visual' in text or 'imprim' in text:
                        return loc
            except Exception:
                continue

        menu_scopes = [
            page.locator('[role="menu"]'),
            page.locator('.dropdown-menu'),
            page.locator('.menu'),
        ]
        for scope in menu_scopes:
            try:
                if scope.count() > 0:
                    for selector in ['a', 'button', '[role="menuitem"]']:
                        candidates = scope.last.locator(selector)
                        for i in range(candidates.count()):
                            candidate = candidates.nth(i)
                            text = (candidate.inner_text(timeout=500) or '').strip().lower()
                            if any(token in text for token in ('danf', 'pdf', 'visual', 'imprim')) and 'xml' not in text:
                                return candidate
            except Exception:
                continue

        try:
            anchors = row.locator('a, button')
            for i in range(anchors.count()):
                candidate = anchors.nth(i)
                text = (candidate.inner_text(timeout=500) or '').strip().lower()
                if any(token in text for token in ('danf', 'pdf', 'visual', 'imprim')) and 'xml' not in text:
                    return candidate
        except Exception:
            pass
        return None

    def _trigger_official_pdf_download(self, page, clickable, download_dir: Path, job, preferred_stem: str) -> Path | None:
        pdf_name = f"{preferred_stem}_oficial.pdf"
        try:
            with page.expect_download(timeout=12000) as dl_info:
                clickable.click(force=True)
            download = dl_info.value
            filename = download.suggested_filename or pdf_name
            if not filename.lower().endswith('.pdf'):
                filename = pdf_name
            target_path = self._unique_download_target(download_dir, filename, preferred_stem=f"{preferred_stem}_oficial")
            download.save_as(str(target_path))
            return target_path
        except Exception as download_exc:
            self._log_job_event(job.id, "PORTAL", f"Download direto do DANFSe não confirmado: {download_exc}", nivel="WARNING")

        try:
            with page.expect_popup(timeout=8000) as popup_info:
                clickable.click(force=True)
            popup = popup_info.value
            popup.wait_for_load_state('domcontentloaded', timeout=10000)
            popup.wait_for_timeout(1200)
            target_path = self._unique_download_target(download_dir, pdf_name, preferred_stem=f"{preferred_stem}_oficial")
            html = popup.content()
            if html and len(html) > 100:
                html_target = target_path.with_suffix('.html')
                html_target.write_text(html, encoding='utf-8')
                try:
                    popup.close()
                except Exception:
                    pass
                self._log_job_event(job.id, "PORTAL", "O portal abriu a visualização do DANFSe em janela HTML; o HTML foi salvo para referência, mas não como PDF oficial.", nivel="WARNING", detalhe=f"Arquivo salvo: {html_target}")
                return None
        except Exception as popup_exc:
            self._log_job_event(job.id, "PORTAL", f"Popup do DANFSe não confirmado: {popup_exc}", nivel="WARNING")
        return None

    def _preferred_file_stem(self, row_text: str, row_number: int) -> str:
        key_match = re.search(r'(\d{44})', row_text or '')
        if key_match:
            return key_match.group(1)
        number_match = re.search(r'\b(\d{3,})\b', row_text or '')
        if number_match:
            return f'nfse_{number_match.group(1)}'
        return f'nfse_linha_{row_number}'


    def _extract_if_zip(self, path: Path, download_dir: Path, job) -> int:
        if path.suffix.lower() != '.zip':
            return 0
        extracted = 0
        try:
            with zipfile.ZipFile(path, 'r') as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    name = Path(info.filename).name
                    if not name.lower().endswith('.xml'):
                        continue
                    target = self._unique_download_target(download_dir, name)
                    with zf.open(info) as src, open(target, 'wb') as dst:
                        dst.write(src.read())
                    extracted += 1
        except Exception as exc:
            self._log_job_event(job.id, "PORTAL", f"Falha ao extrair ZIP {path.name}: {exc}", nivel="ERROR")
        return extracted

    def _go_to_next_page(self, page, job, current_page: int, signature_before: str) -> bool:
        self._raise_if_cancel_requested(job.id, 'troca de página')
        active_page = self._current_page_number(page) or current_page

        container = self._find_pagination_container(page)
        if container is not None:
            next_number = active_page + 1
            candidate = self._find_numeric_page_candidate(container, next_number, page)
            if candidate is not None:
                if self._click_pagination_candidate(page, candidate, job, f"número {next_number}", signature_before, active_page):
                    return True

            title_candidate = self._find_page_by_attributes(container, next_number, page)
            if title_candidate is not None:
                if self._click_pagination_candidate(page, title_candidate, job, f"atributo página {next_number}", signature_before, active_page):
                    return True

        for selector in self.NEXT_PAGE_SELECTORS:
            try:
                locator = page.locator(selector).last
                if locator.count() and locator.is_visible(timeout=700) and self._is_clickable(locator):
                    if self._click_pagination_candidate(page, locator, job, f"seletor {selector}", signature_before, active_page):
                        return True
            except Exception:
                continue

        generic_arrow = self._find_generic_next_arrow(page)
        if generic_arrow is not None:
            if self._click_pagination_candidate(page, generic_arrow, job, "seta de próxima página", signature_before, active_page):
                return True

        if self._click_next_page_via_dom(page, job, active_page, signature_before):
            return True

        self._log_job_event(job.id, "PORTAL", "Nenhuma próxima página foi encontrada; paginação encerrada.")
        return False

    def _estimate_total_pages(self, page, current_page: int | None = None) -> int | None:
        container = self._find_pagination_container(page)
        texts: list[str] = []
        try:
            if container is not None:
                texts.append(container.inner_text(timeout=500) or '')
        except Exception:
            pass

        try:
            for selector in [
                '[aria-label*="pag" i]', '.pagination', 'ul.pagination', '.pager',
                r'text=/p[áa]gina\s+\d+\s+(de|/)\s*\d+/i'
            ]:
                loc = page.locator(selector).first
                if loc.count():
                    texts.append(loc.inner_text(timeout=300) or '')
        except Exception:
            pass

        for text_value in texts:
            match = re.search(r'p[áa]gina\s*(\d+)\s*(?:de|/)\s*(\d+)', text_value, re.IGNORECASE)
            if match:
                total = int(match.group(2))
                if total > 0:
                    return total

        numbers: set[int] = set()
        scopes = [container] if container is not None else []
        scopes.append(page)
        for scope in scopes:
            for selector in ['a', 'button', 'span', 'li', 'div', '[role="link"]', '[role="button"]']:
                try:
                    locs = scope.locator(selector)
                    count = min(locs.count(), 200)
                    for idx in range(count):
                        candidate = locs.nth(idx)
                        if scope is not page:
                            try:
                                if not candidate.is_visible(timeout=200):
                                    continue
                            except Exception:
                                continue
                        values = [
                            candidate.inner_text(timeout=200) or '',
                            candidate.get_attribute('title') or '',
                            candidate.get_attribute('aria-label') or '',
                        ]
                        for raw in values:
                            for num_txt in re.findall(r'\b(\d{1,4})\b', raw or ''):
                                try:
                                    num = int(num_txt)
                                except Exception:
                                    continue
                                if 1 <= num <= 9999:
                                    if scope is page or self._looks_like_pagination(candidate, page):
                                        numbers.add(num)
                except Exception:
                    continue
            if numbers:
                break

        if numbers:
            estimated = max(numbers)
            if current_page and estimated < current_page:
                return current_page
            return estimated
        return None

    def _find_pagination_container(self, page):
        for selector in self.PAGINATION_CONTAINERS:
            try:
                locs = page.locator(selector)
                count = locs.count()
                for idx in range(count):
                    candidate = locs.nth(idx)
                    if candidate.is_visible(timeout=500):
                        return candidate
            except Exception:
                continue
        return None

    def _current_page_number(self, page) -> int | None:
        selectors = [
            '[aria-current="page"]',
            'li.active',
            'a.active',
            'button.active',
            'span.active',
            'span.current',
            '.pagination .active',
        ]
        for selector in selectors:
            try:
                locs = page.locator(selector)
                count = locs.count()
                for idx in range(count):
                    candidate = locs.nth(idx)
                    if not candidate.is_visible(timeout=300):
                        continue
                    text_value = (candidate.inner_text(timeout=300) or '').strip()
                    match = re.search(r'(\d+)', text_value)
                    if match:
                        return int(match.group(1))
            except Exception:
                continue
        return None

    def _page_signature(self, page) -> str:
        try:
            rows = page.locator('table tbody tr')
            parts = [str(self._current_page_number(page) or '')]
            for idx in range(min(rows.count(), 3)):
                parts.append(self._safe_row_text(rows.nth(idx))[:120])
            return ' | '.join(part for part in parts if part)
        except Exception:
            return f"pagina:{self._current_page_number(page) or '?'}"

    def _find_numeric_page_candidate(self, container, page_number: int, page):
        target_text = str(page_number)
        for selector in ['a', 'button', '[role="link"]', '[role="button"]']:
            try:
                candidates = container.locator(selector)
                count = candidates.count()
                for idx in range(count):
                    candidate = candidates.nth(idx)
                    if not candidate.is_visible(timeout=300) or not self._is_clickable(candidate):
                        continue
                    text_value = (candidate.inner_text(timeout=300) or '').strip()
                    if text_value == target_text and self._looks_like_pagination(candidate, page):
                        return candidate
            except Exception:
                continue
        return None

    def _find_page_by_attributes(self, container, page_number: int, page):
        expected_values = {
            f'pagina {page_number}',
            f'página {page_number}',
            f'page {page_number}',
            str(page_number),
        }
        selectors = ['a', 'button', 'span', 'div', 'li', '[role="link"]', '[role="button"]']
        for selector in selectors:
            try:
                candidates = container.locator(selector)
                count = candidates.count()
                for idx in range(count):
                    candidate = candidates.nth(idx)
                    if not candidate.is_visible(timeout=300):
                        continue
                    values = [
                        candidate.get_attribute('title') or '',
                        candidate.get_attribute('aria-label') or '',
                        candidate.get_attribute('data-original-title') or '',
                        candidate.get_attribute('data-title') or '',
                        candidate.inner_text(timeout=300) or '',
                    ]
                    normalized = {' '.join(v.strip().lower().split()) for v in values if v}
                    if normalized & expected_values and self._looks_like_pagination(candidate, page):
                        return candidate
            except Exception:
                continue
        return None

    def _find_generic_next_arrow(self, page):
        arrow_texts = {'>', '›', '»', '>>'}
        attr_tokens = ('próxima', 'proxima', 'next', 'seguinte', 'avançar', 'avancar')
        for selector in ['a', 'button', 'span', 'div', 'li', '[role="link"]', '[role="button"]']:
            try:
                locs = page.locator(selector)
                count = locs.count()
                for idx in range(count - 1, -1, -1):
                    candidate = locs.nth(idx)
                    if not candidate.is_visible(timeout=300) or not self._is_clickable(candidate):
                        continue
                    text_value = (candidate.inner_text(timeout=300) or '').strip()
                    attrs = ' '.join(
                        filter(None, [
                            candidate.get_attribute('title') or '',
                            candidate.get_attribute('aria-label') or '',
                            candidate.get_attribute('data-original-title') or '',
                            candidate.get_attribute('class') or '',
                        ])
                    ).lower()
                    if (text_value in arrow_texts or any(token in attrs for token in attr_tokens)) and self._looks_like_pagination(candidate, page):
                        return candidate
            except Exception:
                continue
        return None

    def _click_next_page_via_dom(self, page, job, page_before: int, signature_before: str) -> bool:
        before_url = page.url
        script = r'''({ pageBefore }) => {
    const selectors = ['ul.pagination', 'nav[aria-label*="pag" i]', '.pagination', '.pager'];
    const containers = [];
    for (const sel of selectors) {
        for (const el of document.querySelectorAll(sel)) containers.push(el);
    }
    const isVisible = (el) => {
        if (!el) return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight;
    };
    const norm = (v) => (v || '').replace(/\s+/g, ' ').trim().toLowerCase();
    const clickable = (el, container) => {
        let cur = el;
        while (cur && cur !== container.parentElement) {
            const tag = (cur.tagName || '').toLowerCase();
            const role = norm(cur.getAttribute('role'));
            const cls = norm(cur.getAttribute('class'));
            if (['a', 'button'].includes(tag) || ['button', 'link'].includes(role) || cur.hasAttribute('onclick') || cur.hasAttribute('href') || cur.tabIndex >= 0 || cls.includes('page-link') || cls.includes('paginate')) {
                return cur;
            }
            cur = cur.parentElement;
        }
        return el;
    };
    const attrText = (el) => [el.innerText, el.textContent, el.title, el.getAttribute('aria-label'), el.getAttribute('data-original-title'), el.getAttribute('class')]
        .map(norm).filter(Boolean).join(' | ');
    const sortByX = (items) => items.sort((a, b) => a.getBoundingClientRect().left - b.getBoundingClientRect().left);
    const findActive = (container) => {
        for (const el of container.querySelectorAll('*')) {
            if (!isVisible(el)) continue;
            const cls = norm(el.getAttribute('class'));
            const attrs = attrText(el);
            if (cls.includes('active') || attrs.includes(`pagina ${pageBefore}`) || attrs.includes(`página ${pageBefore}`) || attrs === String(pageBefore)) {
                return el;
            }
        }
        return null;
    };

    for (const container of containers) {
        if (!isVisible(container)) continue;
        const rect = container.getBoundingClientRect();
        if (rect.top < window.innerHeight * 0.45) continue;

        const candidates = [];
        for (const el of container.querySelectorAll('*')) {
            if (!isVisible(el)) continue;
            const text = attrText(el);
            if (!text) continue;
            if ([`pagina ${pageBefore + 1}`, `página ${pageBefore + 1}`, String(pageBefore + 1)].some(v => text.includes(v))) {
                candidates.push(clickable(el, container));
            }
        }
        if (candidates.length) {
            const target = sortByX(candidates)[0];
            target.click();
            return { clicked: true, description: `dom atributo/numero ${pageBefore + 1}` };
        }

        const arrows = [];
        for (const el of container.querySelectorAll('*')) {
            if (!isVisible(el)) continue;
            const text = attrText(el);
            if (!text) continue;
            if (text.includes('próxima') || text.includes('proxima') || text.includes('next') || text === '>' || text === '›' || text === '»' || text.endsWith('| >') || text.endsWith('| ›') || text.endsWith('| »')) {
                arrows.push(clickable(el, container));
            }
        }
        if (arrows.length) {
            const target = sortByX(arrows).slice(-1)[0];
            target.click();
            return { clicked: true, description: 'dom seta próxima' };
        }

        const active = findActive(container);
        if (active) {
            const activeRect = active.getBoundingClientRect();
            const rightSide = [];
            for (const el of container.querySelectorAll('*')) {
                if (!isVisible(el)) continue;
                const r = el.getBoundingClientRect();
                if (r.left <= activeRect.right + 2) continue;
                const text = attrText(el);
                if (!text) continue;
                rightSide.push(clickable(el, container));
            }
            if (rightSide.length) {
                const target = sortByX(rightSide)[0];
                target.click();
                return { clicked: true, description: 'dom item à direita da página ativa' };
            }
        }
    }
    return { clicked: false, description: 'nenhum candidato DOM encontrado' };
}
'''
        try:
            result = page.evaluate(script, {'pageBefore': page_before})
        except Exception as exc:
            self._log_job_event(job.id, 'PORTAL', f'Falha no fallback DOM da paginação: {exc}', nivel='WARNING')
            return False

        if not result or not result.get('clicked'):
            detalhe = (result or {}).get('description', 'sem detalhe') if isinstance(result, dict) else 'sem detalhe'
            self._log_job_event(job.id, 'PORTAL', f'Fallback DOM da paginação não encontrou candidato ({detalhe}).', nivel='WARNING')
            return False

        changed = self._wait_for_page_change(page, signature_before, page_before, before_url)
        if changed:
            self._log_job_event(job.id, 'PORTAL', f"Avançando paginação por {result.get('description', 'fallback DOM')}", detalhe=f'Página anterior: {page_before}')
            return True

        self._log_job_event(job.id, 'PORTAL', f"Fallback DOM clicou, mas a próxima página não foi confirmada ({result.get('description', 'fallback DOM')}).", nivel='WARNING')
        return False

    def _looks_like_pagination(self, locator, page) -> bool:
        try:
            box = locator.bounding_box()
            if not box:
                return True
            viewport = page.viewport_size or {'height': 900}
            return box.get('y', 0) >= (viewport.get('height', 900) * 0.55)
        except Exception:
            return True

    def _is_clickable(self, locator) -> bool:
        try:
            classes = (locator.get_attribute('class') or '').lower()
            aria_disabled = (locator.get_attribute('aria-disabled') or '').lower()
            disabled_attr = locator.get_attribute('disabled')
            return 'disabled' not in classes and aria_disabled != 'true' and disabled_attr is None
        except Exception:
            return True

    def _click_pagination_candidate(self, page, locator, job, description: str, signature_before: str, page_before: int) -> bool:
        try:
            locator.scroll_into_view_if_needed(timeout=1500)
        except Exception:
            pass

        before_url = page.url
        try:
            locator.click(timeout=5000, force=True)
        except Exception as exc:
            self._log_job_event(job.id, 'PORTAL', f'Falha ao clicar na paginação ({description}): {exc}', nivel='WARNING')
            return False

        changed = self._wait_for_page_change(page, signature_before, page_before, before_url)
        if changed:
            self._log_job_event(job.id, 'PORTAL', f'Avançando paginação por {description}.', detalhe=f'Página anterior: {page_before}')
            return True

        self._log_job_event(job.id, 'PORTAL', f'Clique de paginação executado, mas a próxima página não foi confirmada ({description}).', nivel='WARNING')
        return False

    def _wait_for_page_change(self, page, signature_before: str, page_before: int, before_url: str) -> bool:
        for _ in range(12):
            page.wait_for_timeout(500)
            current_page = self._current_page_number(page) or page_before
            current_signature = self._page_signature(page)
            if page.url != before_url:
                return True
            if current_page != page_before:
                return True
            if current_signature != signature_before:
                return True
        return False

    def _close_open_menu(self, page):
        try:
            page.keyboard.press('Escape')
        except Exception:
            pass

    def _fill_first_visible(self, page, selectors: list[str], value: str) -> str:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if locator.is_visible(timeout=1200):
                    locator.fill(value)
                    return selector
            except Exception:
                continue
        return ""

    def _click_first_visible(self, page, selectors: list[str]) -> str:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if locator.is_visible(timeout=1200):
                    locator.click(timeout=2000)
                    return selector
            except Exception:
                continue
        return ""

    def _unique_download_target(self, download_dir: Path, filename: str, preferred_stem: str | None = None) -> Path:
        original = Path(filename)
        suffix = original.suffix if original.suffix else '.xml'
        stem = preferred_stem or (original.stem if original.stem else 'arquivo')
        target = download_dir / f'{stem}{suffix}'
        if not target.exists():
            return target
        i = 2
        while True:
            candidate = download_dir / f'{stem}_{i}{suffix}'
            if not candidate.exists():
                return candidate
            i += 1

    def _tipo_documento_slug(self, tipo_documento: str) -> str:
        slug = re.sub(r'[^a-zA-Z0-9]+', '_', (tipo_documento or '').strip().lower()).strip('_')
        return slug or 'documentos'

    def _resolve_download_dir(self, cnpj: str, tipo_documento: str, configured_dir: str | None) -> Path:
        cnpj_clean = re.sub(r'\D+', '', cnpj or '') or 'empresa'
        tipo_slug = self._tipo_documento_slug(tipo_documento)

        base = Path(configured_dir) if configured_dir else Path(DOWNLOADS_DIR)
        parts_lower = {part.lower() for part in base.parts}
        if cnpj_clean.lower() not in parts_lower:
            base = base / cnpj_clean
        if tipo_slug.lower() not in {part.lower() for part in base.parts}:
            base = base / tipo_slug
        return base

    def _is_nfse_contribuinte_portal(self, portal_url: str) -> bool:
        lowered = (portal_url or '').lower()
        return 'nfse.gov.br' in lowered and 'emissornacional' in lowered

    def _register_error(self, job_id: int, origem: str, mensagem: str):
        log.error(mensagem)
        self._log_job_event(job_id, origem, mensagem, nivel='ERROR')
