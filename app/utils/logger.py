"""
Sistema centralizado de logging
"""
import sys
from loguru import logger
from config.settings import LOG_FILE, LOG_LEVEL


def setup_logger():
    """Configura o sistema de logging"""
    
    # Remove o handler padrão
    logger.remove()
    
    # Adiciona handler para console
    logger.add(
        sys.stdout,
        format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=LOG_LEVEL,
        colorize=True,
    )
    
    # Adiciona handler para arquivo
    logger.add(
        str(LOG_FILE),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=LOG_LEVEL,
        rotation="500 MB",
        retention="7 days",
    )
    
    return logger


# Instância global do logger
log = setup_logger()
