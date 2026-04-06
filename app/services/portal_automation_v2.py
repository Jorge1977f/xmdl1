"""Automação de portal NFSe - VERSÃO 2 COM ABORDAGEM CORRETA.

Esta versão implementa a abordagem correta:
1. Deixa o usuário fazer login manualmente
2. Usa a sessão autenticada do navegador
3. Navega por todas as páginas de resultados
4. Extrai dados do HTML da tabela
5. Baixa XMLs um por um
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote
import re

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


class PortalAutomationService:
    """Executa um job de download com abordagem correta."""

    def __init__(self):
        self.session = get_db_session()
        self.job_repo = JobDownloadRepository(self.session)
        self.empresa_repo = EmpresaRepository(self.session)
        self.cred_repo = CredencialRepository(self.session)
        self.log_repo = LogEventoRepository(self.session)
        self.xml_import = XMLImportService(self.session)

    def execute_job(self, job_id: int) -> JobExecutionSummary:
        """Executa o job de download."""
        job = self.job_repo.get_by_id(job_id)
        if not job:
            raise ValueError(f"Job {job_id} não encontrado")
        
        empresa = self.empresa_repo.get_by_id(job.empresa_id)
        if not empresa:
            raise ValueError(f"Empresa do job {job_id} não encontrada")

        portal = self.cred_repo.get_ativo_by_empresa(empresa.id, "PORTAL")
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

        wait_seconds = int(portal.tempo_espera_login or 180)
        self.job_repo.update(job.id, status="PROCESSANDO", inicio_em=datetime.utcnow(), log_resumo="Iniciando automação do portal.")
        self.log_repo.create(job.id, "PORTAL", f"Abrindo portal {portal.portal_url}", detalhe=f"Pasta de download: {download_dir}")

        start_mark = datetime.utcnow()
        try:
            downloaded = self._run_browser_session(
                portal_url=portal.portal_url,
                download_dir=download_dir,
                wait_seconds=wait_seconds,
                headless=bool(portal.navegador_headless),
                job=job,
                empresa=empresa,
            )
            summary.opened_portal = True
            
            if downloaded > 0:
                self.log_repo.create(job.id, "PORTAL", f"Portal aberto e {downloaded} XML(s) baixado(s).")
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

        # Importar XMLs baixados
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
                "Verifique se completou o acesso ao portal e se há notas no período selecionado."
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
        download_dir: Path,
        wait_seconds: int,
        headless: bool,
        job,
        empresa,
    ) -> int:
        """Executa a sessão do navegador com abordagem correta."""
        download_dir.mkdir(parents=True, exist_ok=True)
        
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=headless,
                downloads_path=str(download_dir),
            )
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            
            # Abrir portal
            page.goto(portal_url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_NAVIGATION_TIMEOUT)
            self.log_repo.create(job.id, "PORTAL", f"Portal aberto. Aguardando login manual... (Tempo limite: {wait_seconds}s)")
            
            # Deixar usuário fazer login manualmente
            # Esperar até que a URL mude para a página de notas (indicando login bem-sucedido)
            login_detected = False
            try:
                # Esperar pela mudança de URL que indica login bem-sucedido
                page.wait_for_url(
                    lambda url: 'EmissorNacional' in url and 'Login' not in url,
                    timeout=wait_seconds * 1000
                )
                login_detected = True
                self.log_repo.create(job.id, "PORTAL", "✓ Login detectado com sucesso! Iniciando busca de notas...")
            except PlaywrightTimeoutError:
                self.log_repo.create(
                    job.id, "PORTAL",
                    f"✗ Timeout de {wait_seconds}s aguardando login. Verifique se completou o acesso ao portal."
                )
                context.close()
                browser.close()
                return 0
            except Exception as exc:
                self.log_repo.create(job.id, "PORTAL", f"Erro ao aguardar login: {exc}")
                context.close()
                browser.close()
                return 0
            
            if not login_detected:
                context.close()
                browser.close()
                return 0
            
            # Dar um tempo extra para a página carregar completamente
            page.wait_for_timeout(2000)
            
            # Executar fluxo de download
            downloaded = self._execute_download_flow(page, job, download_dir)
            
            context.close()
            browser.close()
            return downloaded

    def _execute_download_flow(self, page, job, download_dir: Path) -> int:
        """Executa o fluxo de download com navegação por páginas."""
        downloaded = 0
        current_date = job.data_inicial
        
        while current_date < job.data_final:
            # Calcular período (máximo 31 dias como o portal permite)
            period_end = min(current_date + timedelta(days=31), job.data_final)
            
            self.log_repo.create(
                job.id, "PORTAL",
                f"Processando período: {current_date.strftime('%d/%m/%Y')} a {period_end.strftime('%d/%m/%Y')}"
            )
            
            # Navegar para página de notas
            tipo_documento = (job.tipo_documento or '').lower()
            if 'saída' in tipo_documento or 'prestada' in tipo_documento or 'prestado' in tipo_documento:
                notas_path = 'Notas/Emitidas'
            else:
                notas_path = 'Notas/Recebidas'
            
            base_url = page.url.split('/EmissorNacional/')[0]
            notas_url = f"{base_url}/EmissorNacional/{notas_path}"
            
            page.goto(notas_url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_NAVIGATION_TIMEOUT)
            page.wait_for_timeout(2000)
            
            # Preencher filtros de data
            try:
                self._fill_date_filters(page, current_date, period_end, job)
            except Exception as exc:
                self.log_repo.create(job.id, "PORTAL", f"Erro ao preencher filtros: {exc}")
                current_date = period_end + timedelta(days=1)
                continue
            
            # Clicar em "Filtrar"
            try:
                filter_button = page.locator('button:has-text("Filtrar"), button:has-text("Buscar")')
                if filter_button.count() > 0:
                    filter_button.first.click()
                    page.wait_for_timeout(3000)
                    self.log_repo.create(job.id, "PORTAL", "Filtro aplicado. Buscando notas...")
            except Exception as exc:
                self.log_repo.create(job.id, "PORTAL", f"Erro ao clicar em filtrar: {exc}")
                current_date = period_end + timedelta(days=1)
                continue
            
            # Verificar se há resultados
            if page.locator('text="Nenhum registro encontrado"').count() > 0:
                self.log_repo.create(job.id, "PORTAL", "Nenhum registro encontrado para este período.")
                current_date = period_end + timedelta(days=1)
                continue
            
            # Navegar por todas as páginas e baixar XMLs
            downloaded += self._download_from_all_pages(page, job, download_dir)
            
            # Avançar para próximo período
            current_date = period_end + timedelta(days=1)
        
        return downloaded

    def _fill_date_filters(self, page, data_inicial, data_final, job):
        """Preenche os filtros de data na página."""
        # Tentar diferentes seletores para campos de data
        date_selectors = [
            'input[name="datainicio"]',
            'input[name="dataInicio"]',
            'input[id*="inicio" i]',
            'input[placeholder*="Data" i]',
        ]
        
        data_inicial_str = data_inicial.strftime('%d/%m/%Y')
        data_final_str = data_final.strftime('%d/%m/%Y')
        
        # Preencher data inicial
        for selector in date_selectors:
            try:
                field = page.locator(selector).first
                if field.is_visible(timeout=1000):
                    field.fill(data_inicial_str)
                    self.log_repo.create(job.id, "PORTAL", f"Data inicial preenchida: {data_inicial_str}")
                    break
            except Exception:
                continue
        
        # Preencher data final
        date_selectors_final = [
            'input[name="datafim"]',
            'input[name="dataFim"]',
            'input[id*="fim" i]',
        ]
        
        for selector in date_selectors_final:
            try:
                field = page.locator(selector).first
                if field.is_visible(timeout=1000):
                    field.fill(data_final_str)
                    self.log_repo.create(job.id, "PORTAL", f"Data final preenchida: {data_final_str}")
                    break
            except Exception:
                continue

    def _download_from_all_pages(self, page, job, download_dir: Path) -> int:
        """Navega por todas as páginas e baixa XMLs."""
        downloaded = 0
        page_num = 1
        
        while True:
            self.log_repo.create(job.id, "PORTAL", f"Processando página {page_num}...")
            
            # Extrair dados da tabela e baixar XMLs
            downloaded += self._download_from_current_page(page, job, download_dir)
            
            # Verificar se há próxima página
            next_button = page.locator('a:has-text("Próxima"), button:has-text("Próxima")')
            if next_button.count() == 0:
                break
            
            try:
                next_button.first.click()
                page.wait_for_timeout(2000)
                page_num += 1
            except Exception:
                break
        
        self.log_repo.create(job.id, "PORTAL", f"Total de XMLs baixados: {downloaded}")
        return downloaded

    def _download_from_current_page(self, page, job, download_dir: Path) -> int:
        """Baixa XMLs da página atual."""
        downloaded = 0
        
        try:
            # Encontrar todas as linhas da tabela
            rows = page.locator('table tbody tr')
            row_count = rows.count()
            
            if row_count == 0:
                self.log_repo.create(job.id, "PORTAL", "Nenhuma linha encontrada na tabela.")
                return 0
            
            self.log_repo.create(job.id, "PORTAL", f"Encontradas {row_count} notas nesta página.")
            
            for idx in range(row_count):
                try:
                    row = rows.nth(idx)
                    
                    # Tentar encontrar link de download
                    download_link = None
                    
                    # Procurar por link direto
                    links = row.locator('a')
                    for link_idx in range(links.count()):
                        link = links.nth(link_idx)
                        href = link.get_attribute('href') or ''
                        if 'download' in href.lower() or 'xml' in href.lower():
                            download_link = link
                            break
                    
                    # Se não encontrou link, procurar por botão de menu
                    if not download_link:
                        menu_button = row.locator('button[aria-haspopup="menu"], button[aria-haspopup="true"]')
                        if menu_button.count() > 0:
                            menu_button.first.click()
                            page.wait_for_timeout(500)
                            download_link = page.locator('a:has-text("Download"), a:has-text("XML")').first
                    
                    # Baixar XML
                    if download_link:
                        try:
                            with page.expect_download(timeout=10000) as dl_info:
                                download_link.click()
                            
                            download = dl_info.value
                            filename = download.suggested_filename or f'nfse_{idx + 1}.xml'
                            target_path = self._unique_download_target(download_dir, filename)
                            download.save_as(str(target_path))
                            downloaded += 1
                            self.log_repo.create(job.id, "PORTAL", f"XML {idx + 1}/{row_count} baixado.")
                            page.wait_for_timeout(300)
                        except Exception as exc:
                            self.log_repo.create(job.id, "PORTAL", f"Erro ao baixar XML {idx + 1}: {exc}")
                            continue
                    else:
                        self.log_repo.create(job.id, "PORTAL", f"Link de download não encontrado para nota {idx + 1}.")
                
                except Exception as exc:
                    self.log_repo.create(job.id, "PORTAL", f"Erro ao processar linha {idx + 1}: {exc}")
                    continue
        
        except Exception as exc:
            self.log_repo.create(job.id, "PORTAL", f"Erro ao processar página: {exc}")
        
        return downloaded

    def _unique_download_target(self, download_dir: Path, filename: str) -> Path:
        """Gera um caminho único para o arquivo."""
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

    def _resolve_download_dir(self, cnpj: str, tipo_documento: str, configured_dir: str | None) -> Path:
        """Resolve o diretório de download."""
        if configured_dir:
            return Path(configured_dir)
        return Path(DOWNLOADS_DIR) / cnpj / tipo_documento.replace(" ", "_")

    def _register_error(self, job_id: int, origem: str, mensagem: str):
        """Registra um erro."""
        log.error(mensagem)
        self.log_repo.create(job_id, origem, mensagem, nivel="ERROR")
