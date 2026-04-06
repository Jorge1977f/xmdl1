"""
Serviço de sincronização de notas via API NFSE Nacional
Com retry, logs detalhados e gerenciamento de pasta temporária
"""

import requests
import logging
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import tempfile
import shutil

logger = logging.getLogger(__name__)


class SincronizadorNFSEv2:
    """Sincronizador de notas NFSE com retry e logs"""
    
    def __init__(self, empresa_id: int, cert_path: str, cert_password: str, 
                 temp_dir: Optional[Path] = None, max_tentativas: int = 3):
        self.empresa_id = empresa_id
        self.cert_path = cert_path
        self.cert_password = cert_password
        self.max_tentativas = max_tentativas
        self.nsu = 0
        self.documentos = []
        self.erros = []
        
        # Pasta temporária
        if temp_dir is None:
            temp_dir = Path(tempfile.gettempdir()) / "xmdl_sync"
        self.temp_dir = temp_dir / f"job_{empresa_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Sincronizador NFSE iniciado para empresa {empresa_id}")
        logger.info(f"Pasta temporária: {self.temp_dir}")
        
        self.session = self._criar_sessao()
    
    def _criar_sessao(self) -> requests.Session:
        """Criar sessão com certificado"""
        session = requests.Session()
        try:
            session.cert = (self.cert_path, self.cert_password)
            session.verify = True
            logger.info(f"Sessão criada com certificado: {self.cert_path}")
        except Exception as e:
            logger.error(f"Erro ao carregar certificado: {e}")
            raise
        return session
    
    def sincronizar(self, data_inicial: str = None, data_final: str = None) -> Dict:
        """
        Sincronizar notas com retry
        
        Args:
            data_inicial: Data inicial (YYYY-MM-DD)
            data_final: Data final (YYYY-MM-DD)
        
        Returns:
            Dict com resultado da sincronização
        """
        try:
            logger.info(f"Iniciando sincronização: NSU inicial = {self.nsu}")
            
            tentativas_globais = 0
            while tentativas_globais < self.max_tentativas:
                try:
                    self._sincronizar_lote()
                    tentativas_globais = 0  # Reset
                
                except requests.exceptions.Timeout:
                    tentativas_globais += 1
                    tempo_espera = 2 ** tentativas_globais
                    logger.warning(f"Timeout na sincronização. Tentativa {tentativas_globais}/{self.max_tentativas}. Aguardando {tempo_espera}s...")
                    time.sleep(tempo_espera)
                
                except requests.exceptions.ConnectionError as e:
                    tentativas_globais += 1
                    tempo_espera = 2 ** tentativas_globais
                    logger.warning(f"Erro de conexão: {e}. Tentativa {tentativas_globais}/{self.max_tentativas}. Aguardando {tempo_espera}s...")
                    time.sleep(tempo_espera)
                
                except Exception as e:
                    logger.error(f"Erro na sincronização: {e}")
                    self.erros.append(str(e))
                    break
            
            resultado = {
                'sucesso': len(self.erros) == 0,
                'quantidade_notas': len(self.documentos),
                'nsu_final': self.nsu,
                'pasta_temp': str(self.temp_dir),
                'erros': self.erros
            }
            
            logger.info(f"Sincronização concluída: {len(self.documentos)} notas, {len(self.erros)} erros")
            return resultado
        
        except Exception as e:
            logger.exception(f"Erro fatal na sincronização: {e}")
            return {
                'sucesso': False,
                'quantidade_notas': len(self.documentos),
                'nsu_final': self.nsu,
                'pasta_temp': str(self.temp_dir),
                'erros': [str(e)]
            }
    
    def _sincronizar_lote(self):
        """Sincronizar um lote de notas"""
        url_base = "https://adn.nfse.gov.br/contribuintes/DFe"
        
        while True:
            url = f"{url_base}/{self.nsu}"
            
            logger.debug(f"Requisitando NSU {self.nsu}...")
            
            try:
                response = self.session.get(url, timeout=60)
                
                if response.status_code == 200:
                    doc = response.json()
                    self.documentos.append(doc)
                    
                    # Salvar em arquivo
                    arquivo = self.temp_dir / f"nfse_{self.nsu}.json"
                    with open(arquivo, 'w') as f:
                        json.dump(doc, f)
                    
                    logger.info(f"✓ NSU {self.nsu} sincronizado e salvo em {arquivo}")
                    self.nsu += 1
                
                elif response.status_code == 404:
                    logger.info(f"✓ Fim da sincronização. Último NSU: {self.nsu - 1}")
                    break
                
                elif response.status_code == 401:
                    raise Exception("Certificado inválido ou expirado")
                
                elif response.status_code == 503:
                    logger.warning("Servidor indisponível (503). Aguardando...")
                    time.sleep(5)
                
                else:
                    raise Exception(f"Erro {response.status_code}: {response.text}")
            
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout ao sincronizar NSU {self.nsu}")
                raise
            
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"Erro de conexão ao sincronizar NSU {self.nsu}: {e}")
                raise
            
            except Exception as e:
                logger.error(f"Erro ao sincronizar NSU {self.nsu}: {e}")
                self.erros.append(f"NSU {self.nsu}: {str(e)}")
                break
    
    def mover_para_final(self, pasta_final: Path) -> bool:
        """
        Mover arquivos da pasta temporária para pasta final
        
        Args:
            pasta_final: Caminho da pasta final
        
        Returns:
            True se sucesso, False caso contrário
        """
        try:
            pasta_final.mkdir(parents=True, exist_ok=True)
            
            for arquivo in self.temp_dir.glob("*.json"):
                destino = pasta_final / arquivo.name
                shutil.copy2(arquivo, destino)
                logger.info(f"Movido {arquivo.name} para {pasta_final}")
            
            logger.info(f"Todos os arquivos movidos para {pasta_final}")
            return True
        
        except Exception as e:
            logger.error(f"Erro ao mover arquivos: {e}")
            return False
    
    def limpar_temp(self):
        """Limpar pasta temporária"""
        try:
            shutil.rmtree(self.temp_dir)
            logger.info(f"Pasta temporária limpa: {self.temp_dir}")
        except Exception as e:
            logger.warning(f"Erro ao limpar pasta temporária: {e}")
    
    def manter_temp(self):
        """Manter pasta temporária (para debug)"""
        logger.info(f"Pasta temporária mantida para debug: {self.temp_dir}")


# Exemplo de uso
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    sync = SincronizadorNFSEv2(
        empresa_id=1,
        cert_path="/caminho/para/certificado.pfx",
        cert_password="senha"
    )
    
    resultado = sync.sincronizar()
    print(f"Resultado: {resultado}")
    
    if resultado['sucesso']:
        sync.mover_para_final(Path("./downloads/final"))
        sync.limpar_temp()
    else:
        sync.manter_temp()

