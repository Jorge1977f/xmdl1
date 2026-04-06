"""
Orquestrador principal do sistema XML Downloader
Coordena todos os motores de captura e gerencia fluxo de execução
"""
from datetime import datetime
from typing import List, Tuple, Optional
from app.utils.logger import log
from app.utils.dates import DateManager
from app.core.cache_manager import CacheManager
from app.core.status_manager import StatusManager
from app.db import get_db_session, JobDownloadRepository, DocumentoRepository, LogEventoRepository
from config.settings import EXECUTION_MODES


class Orchestrator:
    """Orquestrador central do sistema"""
    
    def __init__(self, job_id: int):
        """
        Inicializa orquestrador para um job específico.
        
        Args:
            job_id: ID do job de download
        """
        self.job_id = job_id
        self.session = get_db_session()
        self.job_repo = JobDownloadRepository(self.session)
        self.doc_repo = DocumentoRepository(self.session)
        self.log_repo = LogEventoRepository(self.session)
        
        self.job = self.job_repo.get_by_id(job_id)
        if not self.job:
            raise ValueError(f"Job {job_id} não encontrado")
        
        log.info(f"Orquestrador inicializado para job {job_id}")
    
    def plan_execution(self) -> List[Tuple[datetime, datetime]]:
        """
        Monta plano de execução quebrando período se necessário.
        
        Returns:
            Lista de tuplas (data_inicio, data_fim) para cada lote
        """
        log.info(f"Montando plano de execução para job {self.job_id}")
        
        # Quebra período se necessário
        chunks = DateManager.break_period_into_chunks(
            self.job.data_inicial,
            self.job.data_final
        )
        
        log.info(f"Período quebrado em {len(chunks)} lote(s)")
        return chunks
    
    def execute_motor_cache(self, cnpj: str, chave: str, doc_type: str, date: datetime) -> dict:
        """
        Motor 1: Busca em cache local.
        
        Args:
            cnpj: CNPJ da empresa
            chave: Chave da NF-e
            doc_type: Tipo de documento
            date: Data do documento
            
        Returns:
            Dicionário com resultado
        """
        log.debug(f"Motor Cache: buscando {chave}")
        
        result = CacheManager.get_from_cache(cnpj, chave, doc_type, date)
        
        if result:
            self.log_repo.create(
                self.job_id,
                "MOTOR_CACHE",
                f"Documento encontrado em cache: {chave}"
            )
            return {
                "motor": "CACHE",
                "status": "LOCAL_XML_VALIDO",
                "found": True,
                "data": result,
            }
        
        return {
            "motor": "CACHE",
            "status": "NAO_LOCALIZADO",
            "found": False,
        }
    
    def execute_motor_nsu(self, cnpj: str, chave: str, doc_type: str) -> dict:
        """
        Motor 2: Busca via NSU/distribuição.
        
        Args:
            cnpj: CNPJ da empresa
            chave: Chave da NF-e
            doc_type: Tipo de documento
            
        Returns:
            Dicionário com resultado
        """
        log.debug(f"Motor NSU: buscando {chave}")
        
        # TODO: Implementar integração com NSU
        self.log_repo.create(
            self.job_id,
            "MOTOR_NSU",
            f"Motor NSU ainda não implementado para {chave}"
        )
        
        return {
            "motor": "NSU",
            "status": "NAO_LOCALIZADO",
            "found": False,
        }
    
    def execute_motor_portal(self, cnpj: str, chave: str, doc_type: str) -> dict:
        """
        Motor 3: Busca via portal com login.
        
        Args:
            cnpj: CNPJ da empresa
            chave: Chave da NF-e
            doc_type: Tipo de documento
            
        Returns:
            Dicionário com resultado
        """
        log.debug(f"Motor Portal: buscando {chave}")
        
        # TODO: Implementar automação de portal
        self.log_repo.create(
            self.job_id,
            "MOTOR_PORTAL",
            f"Motor Portal ainda não implementado para {chave}"
        )
        
        return {
            "motor": "PORTAL",
            "status": "NAO_LOCALIZADO",
            "found": False,
        }
    
    def execute_motor_manifest(self, cnpj: str, chave: str, doc_type: str) -> dict:
        """
        Motor 4: Manifestação de NF-e de entrada.
        
        Args:
            cnpj: CNPJ da empresa
            chave: Chave da NF-e
            doc_type: Tipo de documento
            
        Returns:
            Dicionário com resultado
        """
        log.debug(f"Motor Manifestação: processando {chave}")
        
        # TODO: Implementar manifestação
        self.log_repo.create(
            self.job_id,
            "MOTOR_MANIFEST",
            f"Motor Manifestação ainda não implementado para {chave}"
        )
        
        return {
            "motor": "MANIFEST",
            "status": "MANIFESTACAO_PENDENTE",
            "found": False,
        }
    
    def execute_automatic_mode(self, cnpj: str, chave: str, doc_type: str, date: datetime) -> dict:
        """
        Executa modo automático (tenta todos os motores em sequência).
        
        Args:
            cnpj: CNPJ da empresa
            chave: Chave da NF-e
            doc_type: Tipo de documento
            date: Data do documento
            
        Returns:
            Dicionário com resultado final
        """
        log.debug(f"Modo Automático: processando {chave}")
        
        # Etapa A: Cache
        result = self.execute_motor_cache(cnpj, chave, doc_type, date)
        if result["found"]:
            return result
        
        # Etapa B: NSU
        result = self.execute_motor_nsu(cnpj, chave, doc_type)
        if result["found"]:
            return result
        
        # Etapa C: Portal
        result = self.execute_motor_portal(cnpj, chave, doc_type)
        if result["found"]:
            return result
        
        # Etapa D: Manifestação (se aplicável)
        if doc_type == "NFE_ENTRADA":
            result = self.execute_motor_manifest(cnpj, chave, doc_type)
            if result["found"]:
                return result
        
        # Nenhum motor encontrou
        return {
            "motor": "NONE",
            "status": "NAO_LOCALIZADO",
            "found": False,
        }
    
    def execute_job(self) -> dict:
        """
        Executa job completo.
        
        Returns:
            Dicionário com resumo da execução
        """
        log.info(f"Iniciando execução do job {self.job_id}")
        
        self.job_repo.update(self.job_id, status="EXECUTANDO")
        
        try:
            # Monta plano
            chunks = self.plan_execution()
            
            # Executa cada lote
            total_encontrado = 0
            total_baixado = 0
            total_erros = 0
            
            for chunk_start, chunk_end in chunks:
                log.info(f"Processando lote: {chunk_start.date()} a {chunk_end.date()}")
                # TODO: Processar lote
            
            # Atualiza job
            self.job_repo.update(
                self.job_id,
                status="CONCLUIDO",
                fim_em=datetime.utcnow(),
                total_encontrado=total_encontrado,
                total_baixado=total_baixado,
                total_erros=total_erros,
            )
            
            log.info(f"Job {self.job_id} concluído com sucesso")
            
            return {
                "status": "SUCESSO",
                "total_encontrado": total_encontrado,
                "total_baixado": total_baixado,
                "total_erros": total_erros,
            }
        
        except Exception as e:
            log.error(f"Erro na execução do job {self.job_id}: {str(e)}")
            self.job_repo.update(self.job_id, status="ERRO")
            
            return {
                "status": "ERRO",
                "erro": str(e),
            }
        
        finally:
            self.session.close()
