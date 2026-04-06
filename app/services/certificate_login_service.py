"""Serviço de automação de login com certificado digital para portal NFSe.

Este serviço automatiza o processo de:
1. Carregar o certificado PFX
2. Fazer login no portal com certificado
3. Obter a sessão autenticada
4. Navegar para a página de notas
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime
import time

from playwright.sync_api import Page, Browser, BrowserContext, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from app.utils.logger import log


class CertificateLoginService:
    """Serviço para automatizar login com certificado digital."""

    # Seletores CSS para elementos do portal
    SELECTORS = {
        # Página de login
        'certificado_btn': 'button:has-text("Certificado Digital"), a:has-text("Certificado Digital"), [aria-label*="Certificado"]',
        'certificado_tab': 'button[role="tab"]:has-text("Certificado"), div:has-text("ACESSO COM CERTIFICADO DIGITAL")',
        
        # Diálogo de seleção de certificado
        'cert_dialog': 'dialog, [role="dialog"]',
        'cert_list': 'table tbody tr, .certificate-list tr, [role="listbox"] [role="option"]',
        'cert_item': 'tr:has-text("MARAVILHAS"), tr:has-text("AC Syngular")',
        'cert_ok_btn': 'button:has-text("OK"), button:has-text("Confirmar"), button:has-text("Selecionar")',
        
        # Página de notas após login
        'notas_recebidas': 'a:has-text("Notas Recebidas"), button:has-text("Notas Recebidas")',
        'notas_emitidas': 'a:has-text("Notas Emitidas"), button:has-text("Notas Emitidas")',
        
        # Filtros de data
        'data_inicio': 'input[name="datainicio"], input[name="dataInicio"], input[placeholder*="Data Inicial"]',
        'data_fim': 'input[name="datafim"], input[name="dataFim"], input[placeholder*="Data Final"]',
        'filtrar_btn': 'button:has-text("Filtrar"), button:has-text("Buscar"), button:has-text("Pesquisar")',
        
        # Tabela de notas
        'notas_table': 'table tbody',
        'notas_rows': 'table tbody tr',
        'download_link': 'a[href*="download"], button[title*="Download"], i.fa-download',
        
        # Paginação
        'proxima_btn': 'a:has-text("Próxima"), button:has-text("Próxima"), a[aria-label*="Próxima"]',
    }

    def __init__(self, headless: bool = False):
        """Inicializa o serviço.
        
        Args:
            headless: Se True, executa sem interface gráfica
        """
        self.headless = headless
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    def login_with_certificate(
        self,
        portal_url: str,
        cert_path: str,
        cert_password: str | None = None,
        wait_seconds: int = 180,
    ) -> bool:
        """Faz login no portal com certificado digital.
        
        Args:
            portal_url: URL do portal (ex: https://www.nfse.gov.br/EmissorNacional/Login)
            cert_path: Caminho do arquivo PFX do certificado
            cert_password: Senha do certificado (opcional)
            wait_seconds: Tempo máximo de espera para login
            
        Returns:
            True se login foi bem-sucedido, False caso contrário
        """
        try:
            # Iniciar navegador
            with sync_playwright() as playwright:
                self.browser = playwright.chromium.launch(headless=self.headless)
                self.context = self.browser.new_context()
                self.page = self.context.new_page()
                
                # Abrir portal
                log.info(f"Abrindo portal: {portal_url}")
                self.page.goto(portal_url, wait_until="domcontentloaded", timeout=30000)
                
                # Aguardar carregamento da página
                self.page.wait_for_timeout(2000)
                
                # Clicar em "Certificado Digital"
                log.info("Procurando botão de certificado digital...")
                if not self._click_certificate_button():
                    log.error("Botão de certificado digital não encontrado")
                    return False
                
                # Aguardar diálogo de seleção de certificado
                log.info("Aguardando diálogo de seleção de certificado...")
                self.page.wait_for_timeout(2000)
                
                # Selecionar certificado
                log.info(f"Selecionando certificado: {cert_path}")
                if not self._select_certificate():
                    log.error("Erro ao selecionar certificado")
                    return False
                
                # Confirmar seleção
                log.info("Confirmando seleção de certificado...")
                if not self._confirm_certificate_selection():
                    log.error("Erro ao confirmar seleção")
                    return False
                
                # Aguardar redirecionamento após login
                log.info(f"Aguardando login (máximo {wait_seconds}s)...")
                try:
                    self.page.wait_for_url(
                        lambda url: 'EmissorNacional' in url and 'Login' not in url,
                        timeout=wait_seconds * 1000
                    )
                    log.info("✓ Login bem-sucedido!")
                    return True
                except PlaywrightTimeoutError:
                    log.error(f"Timeout aguardando login ({wait_seconds}s)")
                    return False
                    
        except Exception as exc:
            log.error(f"Erro ao fazer login: {exc}")
            return False
        finally:
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()

    def _click_certificate_button(self) -> bool:
        """Clica no botão de certificado digital.
        
        Returns:
            True se clicou com sucesso, False caso contrário
        """
        try:
            # Tentar diferentes seletores
            selectors = [
                'button:has-text("Certificado Digital")',
                'a:has-text("Certificado Digital")',
                'button[aria-label*="Certificado"]',
                'div:has-text("ACESSO COM CERTIFICADO DIGITAL")',
                '[class*="certificado"]',
            ]
            
            for selector in selectors:
                try:
                    btn = self.page.locator(selector).first
                    if btn.is_visible(timeout=1000):
                        btn.click()
                        log.info(f"Clicou em: {selector}")
                        return True
                except Exception:
                    continue
            
            log.warning("Nenhum botão de certificado encontrado")
            return False
            
        except Exception as exc:
            log.error(f"Erro ao clicar em certificado: {exc}")
            return False

    def _select_certificate(self) -> bool:
        """Seleciona o certificado no diálogo.
        
        Returns:
            True se selecionou com sucesso, False caso contrário
        """
        try:
            # Aguardar diálogo aparecer
            self.page.wait_for_timeout(1000)
            
            # Procurar por certificados na lista
            cert_rows = self.page.locator('table tbody tr, [role="listbox"] [role="option"]')
            count = cert_rows.count()
            
            if count == 0:
                log.warning("Nenhum certificado encontrado na lista")
                return False
            
            log.info(f"Encontrados {count} certificado(s)")
            
            # Selecionar o primeiro certificado (ou o que contém "MARAVILHAS")
            for i in range(count):
                row = cert_rows.nth(i)
                text = row.text_content()
                
                if 'MARAVILHAS' in text or 'AC Syngular' in text:
                    row.click()
                    log.info(f"Selecionado certificado: {text[:50]}")
                    return True
            
            # Se não encontrou específico, selecionar o primeiro
            cert_rows.first.click()
            log.info("Selecionado primeiro certificado disponível")
            return True
            
        except Exception as exc:
            log.error(f"Erro ao selecionar certificado: {exc}")
            return False

    def _confirm_certificate_selection(self) -> bool:
        """Confirma a seleção do certificado.
        
        Returns:
            True se confirmou com sucesso, False caso contrário
        """
        try:
            # Procurar por botão de confirmação
            confirm_selectors = [
                'button:has-text("OK")',
                'button:has-text("Confirmar")',
                'button:has-text("Selecionar")',
                'button:has-text("Continuar")',
                'button[type="submit"]',
            ]
            
            for selector in confirm_selectors:
                try:
                    btn = self.page.locator(selector)
                    if btn.count() > 0 and btn.first.is_visible(timeout=1000):
                        btn.first.click()
                        log.info(f"Clicou em: {selector}")
                        return True
                except Exception:
                    continue
            
            log.warning("Botão de confirmação não encontrado")
            return False
            
        except Exception as exc:
            log.error(f"Erro ao confirmar seleção: {exc}")
            return False

    def navigate_to_notas(self, tipo: str = "recebidas") -> bool:
        """Navega para página de notas.
        
        Args:
            tipo: "recebidas" ou "emitidas"
            
        Returns:
            True se navegou com sucesso, False caso contrário
        """
        try:
            if tipo.lower() == "recebidas":
                selector = 'a:has-text("Notas Recebidas"), button:has-text("Notas Recebidas")'
            else:
                selector = 'a:has-text("Notas Emitidas"), button:has-text("Notas Emitidas")'
            
            btn = self.page.locator(selector).first
            if btn.is_visible(timeout=5000):
                btn.click()
                self.page.wait_for_timeout(2000)
                log.info(f"Navegado para: Notas {tipo}")
                return True
            
            log.warning(f"Botão 'Notas {tipo}' não encontrado")
            return False
            
        except Exception as exc:
            log.error(f"Erro ao navegar para notas: {exc}")
            return False

    def fill_date_filters(self, data_inicio: str, data_fim: str) -> bool:
        """Preenche os filtros de data.
        
        Args:
            data_inicio: Data inicial (formato DD/MM/YYYY)
            data_fim: Data final (formato DD/MM/YYYY)
            
        Returns:
            True se preencheu com sucesso, False caso contrário
        """
        try:
            # Preencher data inicial
            date_selectors = [
                'input[name="datainicio"]',
                'input[name="dataInicio"]',
                'input[placeholder*="Data Inicial"]',
                'input[placeholder*="Inicial"]',
            ]
            
            for selector in date_selectors:
                try:
                    field = self.page.locator(selector).first
                    if field.is_visible(timeout=1000):
                        field.fill(data_inicio)
                        log.info(f"Data inicial preenchida: {data_inicio}")
                        break
                except Exception:
                    continue
            
            # Preencher data final
            date_selectors_fim = [
                'input[name="datafim"]',
                'input[name="dataFim"]',
                'input[placeholder*="Data Final"]',
                'input[placeholder*="Final"]',
            ]
            
            for selector in date_selectors_fim:
                try:
                    field = self.page.locator(selector).first
                    if field.is_visible(timeout=1000):
                        field.fill(data_fim)
                        log.info(f"Data final preenchida: {data_fim}")
                        break
                except Exception:
                    continue
            
            return True
            
        except Exception as exc:
            log.error(f"Erro ao preencher datas: {exc}")
            return False

    def click_filter_button(self) -> bool:
        """Clica no botão de filtrar.
        
        Returns:
            True se clicou com sucesso, False caso contrário
        """
        try:
            filter_selectors = [
                'button:has-text("Filtrar")',
                'button:has-text("Buscar")',
                'button:has-text("Pesquisar")',
                'button[type="submit"]',
            ]
            
            for selector in filter_selectors:
                try:
                    btn = self.page.locator(selector)
                    if btn.count() > 0 and btn.first.is_visible(timeout=1000):
                        btn.first.click()
                        self.page.wait_for_timeout(2000)
                        log.info(f"Clicou em: {selector}")
                        return True
                except Exception:
                    continue
            
            log.warning("Botão de filtrar não encontrado")
            return False
            
        except Exception as exc:
            log.error(f"Erro ao clicar em filtrar: {exc}")
            return False

    def get_notas_count(self) -> int:
        """Retorna o número de notas na página atual.
        
        Returns:
            Número de notas encontradas
        """
        try:
            rows = self.page.locator('table tbody tr')
            count = rows.count()
            log.info(f"Encontradas {count} notas na página")
            return count
        except Exception as exc:
            log.error(f"Erro ao contar notas: {exc}")
            return 0

    def get_page_html(self) -> str:
        """Retorna o HTML da página atual.
        
        Returns:
            HTML da página
        """
        try:
            return self.page.content()
        except Exception as exc:
            log.error(f"Erro ao obter HTML: {exc}")
            return ""

    def get_current_url(self) -> str:
        """Retorna a URL atual.
        
        Returns:
            URL da página
        """
        try:
            return self.page.url
        except Exception as exc:
            log.error(f"Erro ao obter URL: {exc}")
            return ""

    def screenshot(self, filename: str) -> bool:
        """Tira uma screenshot da página.
        
        Args:
            filename: Nome do arquivo para salvar
            
        Returns:
            True se conseguiu tirar screenshot, False caso contrário
        """
        try:
            self.page.screenshot(path=filename)
            log.info(f"Screenshot salvo: {filename}")
            return True
        except Exception as exc:
            log.error(f"Erro ao tirar screenshot: {exc}")
            return False


# Script de teste
if __name__ == "__main__":
    service = CertificateLoginService(headless=False)
    
    # Fazer login
    success = service.login_with_certificate(
        portal_url="https://www.nfse.gov.br/EmissorNacional/Login",
        cert_path="/path/to/certificate.pfx",
        wait_seconds=180,
    )
    
    if success:
        print("✓ Login bem-sucedido!")
        print(f"URL atual: {service.get_current_url()}")
    else:
        print("✗ Falha no login")
