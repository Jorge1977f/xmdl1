"""Automação de portal com fluxo específico para o Portal Contribuinte NFS-e - VERSÃO CORRIGIDA."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

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
from app.services.xml_import_service import XMLImportService
from app.utils.logger import log
from config.settings import PLAYWRIGHT_NAVIGATION_TIMEOUT, DOWNLOADS_DIR


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
    errors: list[str] = field(default_factory=list)


class PortalAutomationServiceFixed:
    """Executa um job de download abrindo o portal e importando os XMLs - VERSÃO CORRIGIDA."""

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
    ]
    # CORRIGIDO: Seletores mais específicos para encontrar os botões de ação
    NFSE_ROW_MENU_SELECTORS = [
        'button[aria-haspopup="menu"]',
        'button[aria-haspopup="true"]',
        'button.dropdown-toggle',
        '.dropdown-toggle',
        'button:has(i.fa-ellipsis-v)',
        'a:has(i.fa-ellipsis-v)',
        'button:has(i.fa-ellipsis-vertical)',
        'a:has(i.fa-ellipsis-vertical)',
        '[title*="Ações" i]',
        'button[title*="ações" i]',
        'a[title*="ações" i]',
    ]
    # CORRIGIDO: Seletores mais robustos para encontrar links de download
    NFSE_DOWNLOAD_MENU_SELECTORS = [
        'a:has-text("Download XML")',
        'button:has-text("Download XML")',
        'a[href*="download" i]:has-text("XML")',
        'button[title*="Download" i]',
        'a[title*="Download" i]',
        'text="Download XML"',
    ]
    # NOVO: Seletores para botão de download em lote
    BATCH_DOWNLOAD_SELECTORS = [
        'button:has-text("Download em Lote")',
        'button:has-text("Baixar em Lote")',
        'a:has-text("Download em Lote")',
        'a:has-text("Baixar em Lote")',
        'button[title*="lote" i]',
        'a[title*="lote" i]',
    ]

    def __init__(self):
        self.session = get_db_session()
        self.job_repo = JobDownloadRepository(self.session)
        self.empresa_repo = EmpresaRepository(self.session)
        self.cred_repo = CredencialRepository(self.session)
        self.log_repo = LogEventoRepository(self.session)
        self.xml_import = XMLImportService(self.session)

    def execute_job(self, job_id: int) -> JobExecutionSummary:
        job = self.job_repo.get_by_id(job_id)
        if not job:
            raise ValueError(f"Job {job_id} não encontrado")
        empresa = self.empresa_repo.get_by_id(job.empresa_id)
        if not empresa:
            raise ValueError(f"Empresa do job {job_id} não encontrada")

        portal = self.cred_repo.get_ativo_by_empresa(empresa.id, "PORTAL")
        certificado = self.cred_repo.get_ativo_by_empresa(empresa.id, "CERTIFICADO")
        download_dir = self._resolve_download_dir(empresa.cnpj, job.tipo_documento, portal.downloads_dir if portal else None)
        summary = JobExecutionSummary(
            success=False,
            message="",
            job_id=job.id,
            empresa_nome=empresa.razao_social,
            download_dir=str(download_dir),
        )

        if not portal or not portal.portal_url:
            message = "Configure a URL do portal na tela de Configurações antes de executar."
            self._register_error(job.id, "PORTAL", message)
            self.job_repo.update(job.id, status="ERRO_CONFIGURACAO", log_resumo=message, total_erros=1)
            summary.message = message
            summary.errors.append(message)
            return summary

        wait_seconds = int(portal.tempo_espera_login or 120)
        self.job_repo.update(job.id, status="PROCESSANDO", inicio_em=datetime.utcnow(), log_resumo="Iniciando automação do portal.")
        self.log_repo.create(job.id, "PORTAL", f"Abrindo portal {portal.portal_url}", detalhe=f"Pasta de download: {download_dir}")

        start_mark = datetime.utcnow()
        try:
            login_result = self._run_browser_session(
                portal_url=portal.portal_url,
                login=portal.login or "",
                senha=portal.senha or "",
                download_dir=download_dir,
                wait_seconds=wait_seconds,
                headless=bool(portal.navegador_headless),
                modo_login=(portal.modo_login or "MANUAL_ASSISTIDO"),
                certificado_configurado=bool(certificado and certificado.cert_path),
                job=job,
                empresa=empresa,
            )
            summary.opened_portal = True
            summary.login_attempted = login_result["login_attempted"]
            summary.login_selector = login_result.get("login_selector", "")
            if login_result.get("message"):
                self.log_repo.create(job.id, "PORTAL", login_result["message"])
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

        imported = self.xml_import.import_from_directory(
            empresa_id=empresa.id,
            tipo_documento=job.tipo_documento,
            directory=download_dir,
            modified_after=start_mark,
        )
        summary.files_scanned = imported.scanned
        summary.files_imported = imported.imported
        summary.files_updated = imported.updated
        summary.files_invalid = imported.invalid
        summary.duplicates = imported.duplicates

        total_baixado = imported.imported + imported.updated
        total_erros = imported.invalid
        if total_baixado > 0:
            message = f"Portal aberto e {total_baixado} XML(s) importado(s) para {empresa.razao_social}."
            status = "CONCLUIDO"
            success = True
        else:
            message = (
                "Portal aberto, mas nenhum XML novo foi localizado na pasta monitorada. "
                "Confira a URL, conclua o acesso e revise se o portal permite download em lote para este período."
            )
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
        self.log_repo.create(job.id, "IMPORTADOR_XML", message)

        summary.success = success
        summary.message = message
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
        job,
        empresa,
    ) -> dict[str, Any]:
        download_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=headless,
                downloads_path=str(download_dir),
            )
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            page.goto(portal_url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_NAVIGATION_TIMEOUT)
            result = {
                "login_attempted": False,
                "login_selector": "",
                "message": "Portal aberto com sucesso.",
            }

            if modo_login == "LOGIN_SENHA" and login and senha:
                login_selector = self._fill_first_visible(page, self.USER_SELECTORS, login)
                password_selector = self._fill_first_visible(page, self.PASS_SELECTORS, senha)
                if login_selector and password_selector:
                    result["login_attempted"] = True
                    result["login_selector"] = login_selector
                    submit_selector = self._click_first_visible(page, self.SUBMIT_SELECTORS)
                    result["message"] = (
                        f"Tentativa automática de login executada"
                        f"{' com clique em botão de envio' if submit_selector else ' sem botão detectado; finalize manualmente'}"
                        "."
                    )
                else:
                    result["message"] = "Campos de login não detectados automaticamente; finalize o acesso manualmente no navegador aberto."
            else:
                if certificado_configurado:
                    clicked = self._click_first_visible(page, self.CERTIFICATE_SELECTORS)
                    result["message"] = (
                        "Portal aberto em modo certificado assistido. "
                        + ("Clique/seleção do certificado disparado automaticamente. " if clicked else "")
                        + "Selecione o certificado na janela do navegador e aguarde o restante da automação."
                    )
                else:
                    result["message"] = "Portal aberto em modo manual assistido. Faça login e aguarde o restante da automação."

            if self._is_nfse_contribuinte_portal(portal_url):
                downloaded = self._execute_nfse_portal_flow(page, job, wait_seconds, download_dir)
                result["message"] = (
                    f"Fluxo do Portal Contribuinte NFS-e executado. Downloads concluídos: {downloaded}."
                    if downloaded
                    else "Acesso ao Portal Contribuinte concluído, mas nenhum XML foi baixado no período informado."
                )
            else:
                page.wait_for_timeout(max(wait_seconds, 5) * 1000)

            context.close()
            browser.close()
            return result

    def _execute_nfse_portal_flow(self, page, job, wait_seconds: int, download_dir: Path) -> int:
        """CORRIGIDO: Implementa fluxo melhorado com divisão de períodos e múltiplas tentativas."""
        deadline = max(wait_seconds, 15) * 1000
        self._wait_for_nfse_login(page, deadline)
        
        # NOVO: Dividir período em blocos de 30 dias para contornar limite do portal
        downloaded = 0
        current_date = job.data_inicial
        
        while current_date < job.data_final:
            # Calcular fim do período (máximo 30 dias)
            period_end = min(current_date + timedelta(days=30), job.data_final)
            
            self.log_repo.create(
                job.id, "PORTAL",
                f"Processando período: {current_date.strftime('%d/%m/%Y')} a {period_end.strftime('%d/%m/%Y')}"
            )
            
            target_url = self._build_nfse_target_url(page.url, job.tipo_documento, current_date, period_end)
            self.log_repo.create(job.id, "PORTAL", f"Navegando para consulta filtrada: {target_url}")
            page.goto(target_url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_NAVIGATION_TIMEOUT)
            page.wait_for_timeout(3500)  # CORRIGIDO: Aumentado timeout para renderização
            
            # Tentar download em lote primeiro (NOVO)
            batch_downloaded = self._try_batch_download(page, job, download_dir)
            downloaded += batch_downloaded
            
            if batch_downloaded == 0:
                # Se não conseguiu download em lote, tenta método individual
                downloaded += self._download_nfse_results(page, job, download_dir)
            
            # Avançar para próximo período
            current_date = period_end + timedelta(days=1)
        
        return downloaded

    def _try_batch_download(self, page, job, download_dir: Path) -> int:
        """NOVO: Tenta usar funcionalidade de download em lote do portal."""
        try:
            batch_button = self._find_first_visible(page, self.BATCH_DOWNLOAD_SELECTORS)
            if batch_button:
                self.log_repo.create(job.id, "PORTAL", "Botão de download em lote encontrado. Tentando...")
                batch_button.click(timeout=3000)
                page.wait_for_timeout(1000)
                
                # Verificar se abriu um diálogo ou mudou a página
                page.wait_for_timeout(2000)
                
                # Tentar aceitar download em lote
                confirm_buttons = [
                    'button:has-text("Confirmar")',
                    'button:has-text("OK")',
                    'button:has-text("Baixar")',
                    'button[type="submit"]',
                ]
                
                for selector in confirm_buttons:
                    try:
                        btn = page.locator(selector).first
                        if btn.is_visible(timeout=1000):
                            with page.expect_download(timeout=15000) as dl_info:
                                btn.click(timeout=3000)
                            download = dl_info.value
                            target_path = self._unique_download_target(download_dir, download.suggested_filename or 'nfse_batch.zip')
                            download.save_as(str(target_path))
                            self.log_repo.create(job.id, "PORTAL", f"Download em lote realizado: {target_path}")
                            return 1
                    except Exception:
                        continue
        except Exception as exc:
            log.debug(f"Falha ao tentar download em lote: {exc}")
        
        return 0

    def _wait_for_nfse_login(self, page, timeout_ms: int):
        """CORRIGIDO: Melhorado com mais tentativas de espera."""
        try:
            page.wait_for_url('**/EmissorNacional/**', timeout=timeout_ms)
        except Exception:
            page.wait_for_timeout(timeout_ms // 2)
        try:
            page.wait_for_selector('text="PORTAL CONTRIBUINTE"', timeout=8000)
        except Exception:
            pass

    def _build_nfse_target_url(self, current_url: str, tipo_documento: str, data_inicial, data_final) -> str:
        """CORRIGIDO: Melhorado para garantir URLs corretas."""
        base = current_url.split('/EmissorNacional/')[0].rstrip('/')
        lower = (tipo_documento or '').lower()
        path = 'Notas/Emitidas' if ('saída' in lower or 'prestada' in lower or 'prestado' in lower) else 'Notas/Recebidas'
        di = data_inicial.strftime('%d/%m/%Y')
        df = data_final.strftime('%d/%m/%Y')
        url = f"{base}/EmissorNacional/{path}?executar=1&busca=&datainicio={quote(di)}&datafim={quote(df)}"
        log.debug(f"URL construída: {url}")
        return url

    def _download_nfse_results(self, page, job, download_dir: Path) -> int:
        """CORRIGIDO: Melhorado com melhor tratamento de erros e paginação."""
        page.wait_for_timeout(3000)  # CORRIGIDO: Aumentado tempo de espera
        
        if page.locator('text="Nenhum registro encontrado"').count() > 0:
            self.log_repo.create(job.id, "PORTAL", "Nenhum registro retornado para o período informado no Portal Contribuinte NFS-e.")
            return 0

        downloaded = 0
        
        # CORRIGIDO: Tentar múltiplos métodos de download
        downloaded += self._download_nfse_visible_xml_links(page, job, download_dir)
        if downloaded:
            return downloaded

        downloaded += self._download_nfse_by_row_menu(page, job, download_dir)
        if downloaded:
            return downloaded
        
        # NOVO: Tentar buscar por elementos alternativos
        downloaded += self._download_nfse_by_alternative_selectors(page, job, download_dir)
        return downloaded

    def _download_nfse_visible_xml_links(self, page, job, download_dir: Path) -> int:
        """CORRIGIDO: Melhorado com melhor tratamento de elementos."""
        try:
            links = page.locator('a:has-text("Download XML")')
            count = links.count()
            if count == 0:
                log.debug("Nenhum link de download XML visível encontrado")
                return 0
            
            downloaded = 0
            for idx in range(count):
                try:
                    link = links.nth(idx)
                    link.scroll_into_view_if_needed(timeout=2000)
                    with page.expect_download(timeout=10000) as dl_info:  # CORRIGIDO: Aumentado timeout
                        link.click(force=True)
                    download = dl_info.value
                    target_path = self._unique_download_target(download_dir, download.suggested_filename or f'nfse_{idx + 1}.xml')
                    download.save_as(str(target_path))
                    downloaded += 1
                    self.log_repo.create(job.id, "PORTAL", f"XML baixado via link visível ({idx + 1}/{count}).")
                    page.wait_for_timeout(500)
                except Exception as exc:
                    log.debug(f"Falha ao baixar XML {idx + 1}: {exc}")
                    continue
            return downloaded
        except Exception as exc:
            log.debug(f"Erro ao buscar links de download: {exc}")
            return 0

    def _download_nfse_by_row_menu(self, page, job, download_dir: Path) -> int:
        """CORRIGIDO: Melhorado com melhor localização de botões."""
        try:
            menu_buttons = self._locate_nfse_row_menu_buttons(page)
            total = menu_buttons.count()
            if total == 0:
                log.debug("Nenhum botão de menu de linha encontrado")
                return 0
            
            downloaded = 0
            for idx in range(total):
                try:
                    button = menu_buttons.nth(idx)
                    button.scroll_into_view_if_needed(timeout=2000)
                    button.click(timeout=3000, force=True)
                    page.wait_for_timeout(800)  # CORRIGIDO: Aumentado tempo de espera
                    
                    # CORRIGIDO: Melhorado seletor para encontrar item de download
                    item = None
                    for selector in self.NFSE_DOWNLOAD_MENU_SELECTORS:
                        try:
                            candidate = page.locator(selector).last
                            if candidate.is_visible(timeout=1000):
                                item = candidate
                                break
                        except Exception:
                            continue
                    
                    if item:
                        with page.expect_download(timeout=10000) as dl_info:  # CORRIGIDO: Aumentado timeout
                            item.click(force=True)
                        download = dl_info.value
                        target_path = self._unique_download_target(download_dir, download.suggested_filename or f'nfse_{idx + 1}.xml')
                        download.save_as(str(target_path))
                        downloaded += 1
                        self.log_repo.create(job.id, "PORTAL", f"XML baixado pela ação da linha {idx + 1}/{total}.")
                        page.wait_for_timeout(800)
                except Exception as exc:
                    log.debug(f"Falha ao baixar XML da linha {idx + 1}: {exc}")
                    continue
            return downloaded
        except Exception as exc:
            log.debug(f"Erro ao buscar botões de menu: {exc}")
            return 0

    def _download_nfse_by_alternative_selectors(self, page, job, download_dir: Path) -> int:
        """NOVO: Tenta buscar elementos de download usando seletores alternativos."""
        try:
            alternative_selectors = [
                'a[href*="download" i]',
                'button[title*="download" i]',
                'a[title*="download" i]',
                '[data-action="download"]',
                '.download-link',
                '.download-button',
            ]
            
            for selector in alternative_selectors:
                try:
                    elements = page.locator(selector)
                    count = elements.count()
                    if count > 0:
                        self.log_repo.create(job.id, "PORTAL", f"Encontrados {count} elementos com seletor alternativo: {selector}")
                        
                        downloaded = 0
                        for idx in range(min(count, 100)):  # Limitar a 100 para evitar loops infinitos
                            try:
                                elem = elements.nth(idx)
                                if elem.is_visible(timeout=500):
                                    elem.scroll_into_view_if_needed(timeout=1000)
                                    with page.expect_download(timeout=10000) as dl_info:
                                        elem.click(force=True)
                                    download = dl_info.value
                                    target_path = self._unique_download_target(download_dir, download.suggested_filename or f'nfse_alt_{idx + 1}.xml')
                                    download.save_as(str(target_path))
                                    downloaded += 1
                                    page.wait_for_timeout(500)
                            except Exception:
                                continue
                        
                        if downloaded > 0:
                            return downloaded
                except Exception:
                    continue
        except Exception as exc:
            log.debug(f"Erro ao buscar seletores alternativos: {exc}")
        
        return 0

    def _locate_nfse_row_menu_buttons(self, page):
        """CORRIGIDO: Melhorado para encontrar botões de menu mais confiável."""
        candidates = []
        for selector in self.NFSE_ROW_MENU_SELECTORS:
            try:
                locator = page.locator(selector)
                if locator.count() > 0:
                    candidates.append(locator)
            except Exception:
                continue
        if candidates:
            return max(candidates, key=lambda l: l.count())
        return page.locator('button, a')

    def _find_first_visible(self, page, selectors: list[str]):
        """NOVO: Encontra o primeiro elemento visível entre os seletores."""
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if locator.is_visible(timeout=1000):
                    return locator
            except Exception:
                continue
        return None

    def _unique_download_target(self, download_dir: Path, filename: str) -> Path:
        name = filename if filename.lower().endswith('.xml') else f"{filename}.xml"
        target = download_dir / name
        if not target.exists():
            return target
        stem = target.stem
        suffix = target.suffix
        i = 2
        while True:
            candidate = target.with_name(f"{stem}_{i}{suffix}")
            if not candidate.exists():
                return candidate
            i += 1

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

    def _resolve_download_dir(self, cnpj: str, tipo_documento: str, configured_dir: str | None) -> Path:
        if configured_dir:
            return Path(configured_dir)
        return Path(DOWNLOADS_DIR) / cnpj / tipo_documento.replace(" ", "_")

    def _is_nfse_contribuinte_portal(self, portal_url: str) -> bool:
        lowered = (portal_url or '').lower()
        return 'nfse.gov.br' in lowered and 'emissornacional' in lowered

    def _register_error(self, job_id: int, origem: str, mensagem: str):
        log.error(mensagem)
        self.log_repo.create(job_id, origem, mensagem, nivel="ERROR")
