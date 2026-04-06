"""
Gerenciador de cache local de XMLs
"""
from pathlib import Path
from datetime import datetime
from typing import Optional
from app.utils.logger import log
from app.utils.hashes import HashManager
from config.paths import PathManager


class CacheManager:
    """Gerencia cache local de XMLs"""
    
    @staticmethod
    def get_from_cache(cnpj: str, chave: str, doc_type: str, date: datetime) -> dict:
        """
        Busca documento no cache local.
        
        Args:
            cnpj: CNPJ da empresa
            chave: Chave da NF-e
            doc_type: Tipo de documento
            date: Data do documento
            
        Returns:
            Dicionário com informações do cache ou None
        """
        xml_path = PathManager.get_xml_file_path(cnpj, doc_type, date, chave)
        
        if not xml_path.exists():
            log.debug(f"XML não encontrado em cache: {chave}")
            return None
        
        try:
            with open(xml_path, "rb") as f:
                content = f.read()
            
            hash_value = HashManager.calculate_content_hash(content)
            
            return {
                "status": "LOCAL_XML_VALIDO",
                "path": str(xml_path),
                "hash": hash_value,
                "size": len(content),
                "found_at": datetime.utcnow(),
            }
        except Exception as e:
            log.error(f"Erro ao ler XML do cache: {chave} - {str(e)}")
            return None
    
    @staticmethod
    def save_to_cache(cnpj: str, chave: str, doc_type: str, date: datetime, content: bytes) -> bool:
        """
        Salva documento no cache local.
        
        Args:
            cnpj: CNPJ da empresa
            chave: Chave da NF-e
            doc_type: Tipo de documento
            date: Data do documento
            content: Conteúdo do arquivo em bytes
            
        Returns:
            True se salvo com sucesso
        """
        try:
            xml_path = PathManager.get_xml_file_path(cnpj, doc_type, date, chave)
            
            with open(xml_path, "wb") as f:
                f.write(content)
            
            hash_value = HashManager.calculate_content_hash(content)
            log.info(f"XML salvo em cache: {chave} ({hash_value})")
            
            return True
        except Exception as e:
            log.error(f"Erro ao salvar XML em cache: {chave} - {str(e)}")
            return False
    
    @staticmethod
    def save_raw_to_cache(cnpj: str, chave: str, doc_type: str, date: datetime, content: bytes) -> bool:
        """
        Salva conteúdo bruto (não processado) no cache.
        
        Args:
            cnpj: CNPJ da empresa
            chave: Chave da NF-e
            doc_type: Tipo de documento
            date: Data do documento
            content: Conteúdo bruto em bytes
            
        Returns:
            True se salvo com sucesso
        """
        try:
            raw_path = PathManager.get_raw_file_path(cnpj, doc_type, date, chave)
            
            with open(raw_path, "wb") as f:
                f.write(content)
            
            log.info(f"Conteúdo bruto salvo em cache: {chave}")
            return True
        except Exception as e:
            log.error(f"Erro ao salvar conteúdo bruto: {chave} - {str(e)}")
            return False
    
    @staticmethod
    def check_cache_exists(cnpj: str, chave: str, doc_type: str, date: datetime) -> bool:
        """
        Verifica se documento existe em cache.
        
        Args:
            cnpj: CNPJ da empresa
            chave: Chave da NF-e
            doc_type: Tipo de documento
            date: Data do documento
            
        Returns:
            True se existe
        """
        xml_path = PathManager.get_xml_file_path(cnpj, doc_type, date, chave)
        return xml_path.exists()
    
    @staticmethod
    def verify_cache_integrity(cnpj: str, chave: str, doc_type: str, date: datetime, expected_hash: str) -> bool:
        """
        Verifica integridade do arquivo em cache.
        
        Args:
            cnpj: CNPJ da empresa
            chave: Chave da NF-e
            doc_type: Tipo de documento
            date: Data do documento
            expected_hash: Hash esperado
            
        Returns:
            True se hash corresponde
        """
        xml_path = PathManager.get_xml_file_path(cnpj, doc_type, date, chave)
        
        if not xml_path.exists():
            return False
        
        return HashManager.verify_file_hash(xml_path, expected_hash)
    
    @staticmethod
    def get_cache_stats(cnpj: str) -> dict:
        """
        Retorna estatísticas do cache da empresa.
        
        Args:
            cnpj: CNPJ da empresa
            
        Returns:
            Dicionário com estatísticas
        """
        company_root = PathManager.get_company_root(cnpj)
        
        if not company_root.exists():
            return {
                "total_files": 0,
                "total_size": 0,
                "by_type": {},
            }
        
        stats = {
            "total_files": 0,
            "total_size": 0,
            "by_type": {},
        }
        
        for xml_file in company_root.rglob("*.xml"):
            stats["total_files"] += 1
            stats["total_size"] += xml_file.stat().st_size
            
            # Categorizar por tipo
            relative_path = xml_file.relative_to(company_root)
            doc_type = str(relative_path.parts[0])
            if doc_type not in stats["by_type"]:
                stats["by_type"][doc_type] = {"count": 0, "size": 0}
            stats["by_type"][doc_type]["count"] += 1
            stats["by_type"][doc_type]["size"] += xml_file.stat().st_size
        
        return stats
    
    @staticmethod
    def clear_cache(cnpj: str, doc_type: Optional[str] = None) -> bool:
        """
        Limpa cache da empresa.
        
        Args:
            cnpj: CNPJ da empresa
            doc_type: Tipo de documento (opcional, limpa tudo se não informado)
            
        Returns:
            True se limpo com sucesso
        """
        try:
            if doc_type:
                path = PathManager.get_document_type_dir(cnpj, doc_type)
            else:
                path = PathManager.get_company_root(cnpj)
            
            if path.exists():
                import shutil
                shutil.rmtree(path)
                log.info(f"Cache limpo: {cnpj}/{doc_type or 'todos'}")
                return True
            return False
        except Exception as e:
            log.error(f"Erro ao limpar cache: {str(e)}")
            return False
