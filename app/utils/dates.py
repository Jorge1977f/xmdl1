"""
Utilitários para manipulação de datas
"""
from datetime import datetime, timedelta
from typing import List, Tuple
from config.settings import MAX_PERIOD_DAYS


class DateManager:
    """Gerencia operações com datas e períodos"""
    
    @staticmethod
    def break_period_into_chunks(
        start_date: datetime,
        end_date: datetime,
        max_days: int = MAX_PERIOD_DAYS
    ) -> List[Tuple[datetime, datetime]]:
        """
        Quebra um período em chunks menores se necessário.
        
        Args:
            start_date: Data inicial
            end_date: Data final
            max_days: Máximo de dias por chunk
            
        Returns:
            Lista de tuplas (data_inicio, data_fim)
        """
        chunks = []
        current_start = start_date
        
        while current_start < end_date:
            current_end = current_start + timedelta(days=max_days - 1)
            if current_end > end_date:
                current_end = end_date
            
            chunks.append((current_start, current_end))
            current_start = current_end + timedelta(days=1)
        
        return chunks
    
    @staticmethod
    def get_period_days(start_date: datetime, end_date: datetime) -> int:
        """Retorna número de dias entre duas datas"""
        return (end_date - start_date).days + 1
    
    @staticmethod
    def needs_breaking(start_date: datetime, end_date: datetime, max_days: int = MAX_PERIOD_DAYS) -> bool:
        """Verifica se período precisa ser quebrado"""
        return DateManager.get_period_days(start_date, end_date) > max_days
    
    @staticmethod
    def format_date(date: datetime, format_str: str = "%d/%m/%Y") -> str:
        """Formata data para string"""
        return date.strftime(format_str)
    
    @staticmethod
    def parse_date(date_str: str, format_str: str = "%d/%m/%Y") -> datetime:
        """Converte string para datetime"""
        return datetime.strptime(date_str, format_str)
    
    @staticmethod
    def get_month_range(year: int, month: int) -> Tuple[datetime, datetime]:
        """Retorna primeiro e último dia do mês"""
        first_day = datetime(year, month, 1)
        if month == 12:
            last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = datetime(year, month + 1, 1) - timedelta(days=1)
        return first_day, last_day
