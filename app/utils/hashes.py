"""
Utilitários para hashing e validação de integridade
"""
import hashlib
from pathlib import Path
from config.settings import CACHE_HASH_ALGORITHM


class HashManager:
    """Gerencia hashing e validação de arquivos"""
    
    @staticmethod
    def calculate_file_hash(file_path: Path, algorithm: str = CACHE_HASH_ALGORITHM) -> str:
        """
        Calcula hash de um arquivo.
        
        Args:
            file_path: Caminho do arquivo
            algorithm: Algoritmo de hash (padrão: sha256)
            
        Returns:
            Hash em formato hexadecimal
        """
        hash_obj = hashlib.new(algorithm)
        
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_obj.update(chunk)
        
        return hash_obj.hexdigest()
    
    @staticmethod
    def calculate_content_hash(content: bytes, algorithm: str = CACHE_HASH_ALGORITHM) -> str:
        """
        Calcula hash de conteúdo em bytes.
        
        Args:
            content: Conteúdo em bytes
            algorithm: Algoritmo de hash
            
        Returns:
            Hash em formato hexadecimal
        """
        hash_obj = hashlib.new(algorithm)
        hash_obj.update(content)
        return hash_obj.hexdigest()
    
    @staticmethod
    def verify_file_hash(file_path: Path, expected_hash: str, algorithm: str = CACHE_HASH_ALGORITHM) -> bool:
        """
        Verifica se hash do arquivo corresponde ao esperado.
        
        Args:
            file_path: Caminho do arquivo
            expected_hash: Hash esperado
            algorithm: Algoritmo de hash
            
        Returns:
            True se hashes correspondem, False caso contrário
        """
        calculated_hash = HashManager.calculate_file_hash(file_path, algorithm)
        return calculated_hash.lower() == expected_hash.lower()
    
    @staticmethod
    def generate_document_key(cnpj: str, chave: str, doc_type: str) -> str:
        """
        Gera chave única para documento (evita duplicidade).
        
        Args:
            cnpj: CNPJ da empresa
            chave: Chave da NF-e
            doc_type: Tipo de documento
            
        Returns:
            Chave única em formato hash
        """
        unique_str = f"{cnpj}:{chave}:{doc_type}"
        return hashlib.sha256(unique_str.encode()).hexdigest()
