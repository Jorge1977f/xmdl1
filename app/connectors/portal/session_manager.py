"""
Gerenciador de sessão para portais
"""
from datetime import datetime, timedelta
from typing import Optional
from app.utils.logger import log


class SessionManager:
    """Gerencia sessões autenticadas com portais"""
    
    def __init__(self):
        self.sessions = {}  # Dicionário de sessões ativas
    
    def create_session(self, empresa_id: int, session_data: dict) -> str:
        """
        Cria nova sessão.
        
        Args:
            empresa_id: ID da empresa
            session_data: Dados da sessão (cookies, tokens, etc)
            
        Returns:
            ID da sessão
        """
        session_id = f"session_{empresa_id}_{datetime.utcnow().timestamp()}"
        
        self.sessions[session_id] = {
            "empresa_id": empresa_id,
            "data": session_data,
            "criado_em": datetime.utcnow(),
            "ultimo_uso": datetime.utcnow(),
            "ativo": True,
        }
        
        log.info(f"Sessão criada: {session_id}")
        return session_id
    
    def get_session(self, session_id: str) -> Optional[dict]:
        """Recupera sessão"""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session["ultimo_uso"] = datetime.utcnow()
            return session
        return None
    
    def is_session_valid(self, session_id: str, max_age_hours: int = 24) -> bool:
        """Verifica se sessão ainda é válida"""
        session = self.get_session(session_id)
        if not session:
            return False
        
        age = datetime.utcnow() - session["criado_em"]
        return age < timedelta(hours=max_age_hours)
    
    def close_session(self, session_id: str) -> bool:
        """Fecha sessão"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            log.info(f"Sessão fechada: {session_id}")
            return True
        return False
    
    def cleanup_expired_sessions(self, max_age_hours: int = 24):
        """Remove sessões expiradas"""
        expired = []
        for session_id, session in self.sessions.items():
            age = datetime.utcnow() - session["criado_em"]
            if age > timedelta(hours=max_age_hours):
                expired.append(session_id)
        
        for session_id in expired:
            self.close_session(session_id)
        
        if expired:
            log.info(f"Limpas {len(expired)} sessões expiradas")
