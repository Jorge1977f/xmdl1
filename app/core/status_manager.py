"""
Gerenciador de status de documentos
"""
from datetime import datetime
from typing import Optional
from app.utils.logger import log
from config.settings import DOCUMENT_STATUS


class StatusManager:
    """Gerencia status de documentos com auditoria"""
    
    # Mapeamento de status válidos
    VALID_STATUS = set(DOCUMENT_STATUS.keys())
    
    @staticmethod
    def is_valid_status(status: str) -> bool:
        """Verifica se status é válido"""
        return status in StatusManager.VALID_STATUS
    
    @staticmethod
    def get_status_description(status: str) -> str:
        """Retorna descrição do status"""
        return DOCUMENT_STATUS.get(status, "Status desconhecido")
    
    @staticmethod
    def is_success_status(status: str) -> bool:
        """Verifica se status indica sucesso"""
        success_statuses = {
            "LOCAL_CACHE",
            "LOCAL_XML_VALIDO",
            "NSU_LOCALIZADO",
            "PORTAL_LOCALIZADO",
            "PORTAL_BAIXADO",
            "MANIFESTADO",
            "XML_PROCESSADO",
        }
        return status in success_statuses
    
    @staticmethod
    def is_error_status(status: str) -> bool:
        """Verifica se status indica erro"""
        error_statuses = {
            "XML_INVALIDO",
            "ERRO_LOGIN",
            "ERRO_DOWNLOAD",
            "ERRO_PARSE",
        }
        return status in error_statuses
    
    @staticmethod
    def is_pending_status(status: str) -> bool:
        """Verifica se status indica pendência"""
        pending_statuses = {
            "MANIFESTACAO_PENDENTE",
            "AGUARDANDO_DISPONIBILIDADE",
        }
        return status in pending_statuses
    
    @staticmethod
    def is_final_status(status: str) -> bool:
        """Verifica se status é final (não muda mais)"""
        final_statuses = {
            "LOCAL_XML_VALIDO",
            "XML_PROCESSADO",
            "XML_INVALIDO",
            "ERRO_LOGIN",
            "ERRO_PARSE",
            "NAO_LOCALIZADO",
        }
        return status in final_statuses
    
    @staticmethod
    def can_transition(current_status: str, new_status: str) -> bool:
        """
        Verifica se transição de status é permitida.
        
        Args:
            current_status: Status atual
            new_status: Status desejado
            
        Returns:
            True se transição é válida
        """
        # Não permite transição de status final
        if StatusManager.is_final_status(current_status):
            # Exceção: pode voltar para reprocessamento
            if new_status in ["MANIFESTACAO_PENDENTE", "AGUARDANDO_DISPONIBILIDADE"]:
                return True
            return False
        
        # Transições válidas
        valid_transitions = {
            "NAO_LOCALIZADO": {
                "LOCAL_CACHE",
                "NSU_LOCALIZADO",
                "PORTAL_LOCALIZADO",
                "MANIFESTACAO_PENDENTE",
                "ERRO_LOGIN",
                "ERRO_DOWNLOAD",
            },
            "LOCAL_CACHE": {
                "LOCAL_XML_VALIDO",
                "XML_INVALIDO",
                "ERRO_PARSE",
            },
            "NSU_LOCALIZADO": {
                "RAW_SALVO",
                "XML_PROCESSADO",
                "XML_INVALIDO",
                "ERRO_PARSE",
            },
            "PORTAL_LOCALIZADO": {
                "PORTAL_BAIXADO",
                "ERRO_DOWNLOAD",
            },
            "PORTAL_BAIXADO": {
                "XML_PROCESSADO",
                "XML_INVALIDO",
                "ERRO_PARSE",
            },
            "MANIFESTACAO_PENDENTE": {
                "MANIFESTADO",
                "AGUARDANDO_DISPONIBILIDADE",
                "ERRO_LOGIN",
            },
            "MANIFESTADO": {
                "LOCAL_CACHE",
                "PORTAL_LOCALIZADO",
                "AGUARDANDO_DISPONIBILIDADE",
            },
            "AGUARDANDO_DISPONIBILIDADE": {
                "LOCAL_CACHE",
                "PORTAL_LOCALIZADO",
                "MANIFESTACAO_PENDENTE",
            },
            "RAW_SALVO": {
                "XML_PROCESSADO",
                "XML_INVALIDO",
                "ERRO_PARSE",
            },
        }
        
        if current_status not in valid_transitions:
            return False
        
        return new_status in valid_transitions[current_status]
    
    @staticmethod
    def get_next_action(status: str) -> Optional[str]:
        """
        Retorna próxima ação recomendada baseada no status.
        
        Args:
            status: Status atual
            
        Returns:
            Descrição da próxima ação ou None
        """
        actions = {
            "NAO_LOCALIZADO": "Tentar buscar via cache, NSU ou portal",
            "LOCAL_CACHE": "Validar XML",
            "NSU_LOCALIZADO": "Processar conteúdo bruto",
            "PORTAL_LOCALIZADO": "Baixar XML",
            "PORTAL_BAIXADO": "Processar XML",
            "MANIFESTACAO_PENDENTE": "Aguardar manifestação ou tentar novamente",
            "MANIFESTADO": "Tentar buscar XML completo",
            "AGUARDANDO_DISPONIBILIDADE": "Aguardar e tentar novamente",
            "RAW_SALVO": "Processar conteúdo bruto",
            "LOCAL_XML_VALIDO": "Documento pronto",
            "XML_PROCESSADO": "Documento pronto",
            "XML_INVALIDO": "Revisar documento",
            "ERRO_LOGIN": "Verificar credenciais",
            "ERRO_DOWNLOAD": "Tentar novamente",
            "ERRO_PARSE": "Revisar XML",
        }
        
        return actions.get(status)
    
    @staticmethod
    def log_status_change(
        documento_id: int,
        old_status: str,
        new_status: str,
        reason: str = "",
    ):
        """Registra mudança de status"""
        log.info(
            f"Documento {documento_id}: {old_status} → {new_status} | {reason}"
        )
