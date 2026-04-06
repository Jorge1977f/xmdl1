"""
Gerenciador de caminhos e organização de arquivos
"""
from pathlib import Path
from datetime import datetime
from config.settings import XML_DIR


class PathManager:
    """Gerencia estrutura de diretórios para XMLs organizados"""
    
    @staticmethod
    def get_company_root(cnpj: str) -> Path:
        """Retorna raiz de diretório da empresa"""
        return XML_DIR / cnpj
    
    @staticmethod
    def get_document_type_dir(cnpj: str, doc_type: str) -> Path:
        """Retorna diretório para tipo de documento"""
        company_root = PathManager.get_company_root(cnpj)
        return company_root / doc_type
    
    @staticmethod
    def get_year_month_dir(cnpj: str, doc_type: str, date: datetime) -> Path:
        """Retorna diretório organizado por ano/mês"""
        doc_dir = PathManager.get_document_type_dir(cnpj, doc_type)
        year = str(date.year)
        month = f"{date.month:02d}"
        return doc_dir / year / month
    
    @staticmethod
    def ensure_directory_exists(path: Path) -> Path:
        """Cria diretório se não existir"""
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @staticmethod
    def get_xml_file_path(cnpj: str, doc_type: str, date: datetime, chave: str) -> Path:
        """Retorna caminho completo para arquivo XML"""
        year_month_dir = PathManager.get_year_month_dir(cnpj, doc_type, date)
        PathManager.ensure_directory_exists(year_month_dir)
        filename = f"{chave}.xml"
        return year_month_dir / filename
    
    @staticmethod
    def get_raw_file_path(cnpj: str, doc_type: str, date: datetime, chave: str) -> Path:
        """Retorna caminho para arquivo bruto (não processado)"""
        year_month_dir = PathManager.get_year_month_dir(cnpj, doc_type, date)
        PathManager.ensure_directory_exists(year_month_dir)
        filename = f"{chave}.raw"
        return year_month_dir / filename
    
    @staticmethod
    def get_backup_file_path(cnpj: str, doc_type: str, date: datetime, chave: str) -> Path:
        """Retorna caminho para backup de arquivo"""
        year_month_dir = PathManager.get_year_month_dir(cnpj, doc_type, date)
        backup_dir = year_month_dir / ".backup"
        PathManager.ensure_directory_exists(backup_dir)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{chave}_{timestamp}.bak"
        return backup_dir / filename


# Estrutura esperada:
# XMLs/
#   12345678000199/
#     NFE_ENTRADAS/
#       2026/
#         01/
#           35260101234567890123456789012345.xml
#           35260101234567890123456789012346.xml
#     NFE_SAIDAS/
#       2026/
#         01/
#     NFSE_PRESTADAS/
#       2026/
#         01/
#     NFSE_TOMADAS/
#       2026/
#         01/
