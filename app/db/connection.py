"""
Gerenciador de conexão com banco de dados
"""
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from config.settings import DATABASE_URL, DATABASE_ECHO, DB_DIR
from app.db.models import Base
from app.utils.logger import log


class DatabaseConnection:
    """Gerencia conexão com banco de dados"""

    _engine = None
    _session_factory = None

    EMPRESAS_EXTRA_COLUMNS = {
        "nome_fantasia": "VARCHAR(255)",
        "matriz_filial": "VARCHAR(20)",
        "data_abertura": "VARCHAR(20)",
        "porte": "VARCHAR(50)",
        "natureza_juridica": "VARCHAR(255)",
        "atividade_principal": "TEXT",
        "atividades_secundarias": "TEXT",
        "logradouro": "VARCHAR(255)",
        "numero": "VARCHAR(50)",
        "complemento": "VARCHAR(255)",
        "cep": "VARCHAR(20)",
        "bairro": "VARCHAR(100)",
        "email": "VARCHAR(255)",
        "telefone": "VARCHAR(100)",
        "situacao_cadastral": "VARCHAR(50)",
        "data_situacao_cadastral": "VARCHAR(20)",
        "motivo_situacao_cadastral": "VARCHAR(255)",
        "situacao_especial": "VARCHAR(255)",
        "data_situacao_especial": "VARCHAR(20)",
        "efr": "VARCHAR(255)",
    }

    CREDENCIAIS_EXTRA_COLUMNS = {
        "portal_url": "VARCHAR(500)",
        "downloads_dir": "VARCHAR(500)",
        "modo_login": "VARCHAR(50) DEFAULT 'MANUAL_ASSISTIDO'",
        "navegador_headless": "BOOLEAN DEFAULT 0",
        "tempo_espera_login": "INTEGER DEFAULT 120",
        "ultimo_nsu_api": "INTEGER",
        "ultimo_nsu_api_prestadas": "INTEGER",
        "ultimo_nsu_api_tomadas": "INTEGER",
        "lote_nsu_api": "INTEGER",
    }

    @classmethod
    def initialize(cls):
        """Inicializa conexão com banco de dados"""
        if cls._engine is None:
            log.info(f"Inicializando banco de dados: {DATABASE_URL}")
            connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
            cls._engine = create_engine(DATABASE_URL, echo=DATABASE_ECHO, connect_args=connect_args)
            cls._session_factory = sessionmaker(bind=cls._engine, expire_on_commit=False)

            Base.metadata.create_all(cls._engine)
            cls.ensure_schema()
            log.info("Banco de dados inicializado com sucesso")

    @classmethod
    def ensure_schema(cls):
        """Garante colunas novas em bases SQLite já existentes."""
        if not DATABASE_URL.startswith("sqlite"):
            return

        cls._ensure_table_columns("empresas", cls.EMPRESAS_EXTRA_COLUMNS)
        cls._ensure_table_columns("credenciais", cls.CREDENCIAIS_EXTRA_COLUMNS)

    @classmethod
    def _ensure_table_columns(cls, table_name: str, column_map: dict[str, str]):
        with cls._engine.begin() as conn:
            existing_columns = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table_name})"))}
            for column_name, sql_type in column_map.items():
                if column_name not in existing_columns:
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {sql_type}"))
                    log.info(f"Coluna adicionada automaticamente: {table_name}.{column_name}")

    @classmethod
    def get_session(cls) -> Session:
        """Retorna nova sessão de banco de dados"""
        if cls._session_factory is None:
            cls.initialize()
        return cls._session_factory()

    @classmethod
    def get_database_path(cls) -> str:
        db_path = Path(DB_DIR) / "xml_downloader.db"
        return str(db_path)

    @classmethod
    def test_connection(cls) -> tuple[bool, str]:
        try:
            if cls._engine is None:
                cls.initialize()
            with cls._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True, cls.get_database_path()
        except Exception as exc:
            log.exception(f"Falha ao testar conexão: {exc}")
            return False, str(exc)

    @classmethod
    def close(cls):
        """Fecha conexão com banco de dados"""
        if cls._engine is not None:
            cls._engine.dispose()
            log.info("Conexão com banco de dados fechada")


def get_db_session() -> Session:
    """Retorna sessão de banco de dados"""
    return DatabaseConnection.get_session()
