"""
Configurações centralizadas do sistema XML Downloader.

Separação importante:
- APP_ROOT = onde o programa/arquivos embarcados estão.
- APP_HOME = pasta externa gravável do usuário/instalação (padrão C:/xmdl no Windows).

Isso evita gravar banco/logs dentro da pasta do executável e facilita o uso com
Nuitka, Inno Setup e até modo onefile.
"""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

APP_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = APP_ROOT  # compatibilidade com o restante do projeto
BUNDLED_DATA_DIR = APP_ROOT / "data"

# Carrega .env ao lado do projeto/executável ou do diretório atual.
# Isso permite definir XMLDLK_HOME antes de calcular APP_HOME.
for env_path in [APP_ROOT / ".env", Path.cwd() / ".env"]:
    if env_path.exists():
        load_dotenv(env_path, override=False)

DEFAULT_APP_HOME = Path(r"C:/xmdl") if os.name == "nt" else (Path.home() / ".xmdl")
APP_HOME = Path(os.getenv("XMLDLK_HOME", str(DEFAULT_APP_HOME))).expanduser()

# Se existir .env dentro da pasta externa, carrega por último.
external_env = APP_HOME / ".env"
if external_env.exists():
    load_dotenv(external_env, override=False)

DATA_DIR = APP_HOME / "data"
DB_DIR = DATA_DIR / "db"
CACHE_DIR = DATA_DIR / "cache_raw"
XML_DIR = DATA_DIR / "xml_processados"
DEFAULT_WINDOWS_DOWNLOADS_DIR = APP_HOME / "data" / "downloads"
DOWNLOADS_DIR = Path(
    os.getenv(
        "XMLDLK_DOWNLOADS_DIR",
        str(DEFAULT_WINDOWS_DOWNLOADS_DIR if os.name == "nt" else DATA_DIR / "downloads"),
    )
).expanduser()
CERTIFICATES_DIR = DATA_DIR / "certificados"
LOGS_DIR = DATA_DIR / "logs"
BACKUPS_DIR = DATA_DIR / "backups"
CLEANUP_LOGS_DIR = DATA_DIR / "logs_limpeza"

MUNICIPIOS_IBGE_FILE = Path(
    os.getenv("XMLDLK_MUNICIPIOS_IBGE_PATH", str(BUNDLED_DATA_DIR / "municipios_ibge.json"))
).expanduser()

for directory in [
    APP_HOME,
    DATA_DIR,
    DB_DIR,
    CACHE_DIR,
    XML_DIR,
    DOWNLOADS_DIR,
    CERTIFICATES_DIR,
    LOGS_DIR,
    BACKUPS_DIR,
    CLEANUP_LOGS_DIR,
]:
    directory.mkdir(parents=True, exist_ok=True)

LICENSE_API_URL = os.getenv("XMLDLK_LICENSE_API_URL", "").strip()
LICENSE_API_TIMEOUT_SECONDS = int(os.getenv("XMLDLK_LICENSE_API_TIMEOUT", "30"))
LICENSE_TRIAL_DAYS = int(os.getenv("XMLDLK_LICENSE_TRIAL_DAYS", "7"))
LICENSE_PRICE_PER_MACHINE = float(os.getenv("XMLDLK_LICENSE_PRICE", "49.90"))
LICENSE_DISCOUNT_START_FROM = int(os.getenv("XMLDLK_LICENSE_DISCOUNT_START_FROM", "6"))
LICENSE_DISCOUNT_RATE = float(os.getenv("XMLDLK_LICENSE_DISCOUNT_RATE", "0.10"))
LICENSE_OFFLINE_GRACE_DAYS = int(os.getenv("XMLDLK_LICENSE_OFFLINE_GRACE_DAYS", "0"))
LICENSE_ALLOW_HTTP_LOCAL = os.getenv("XMLDLK_LICENSE_ALLOW_HTTP_LOCAL", "False").lower() == "true"
APP_VERSION = os.getenv("XMLDLK_APP_VERSION", "1.0.0").strip() or "1.0.0"

DATABASE_URL = f"sqlite:///{DB_DIR / 'xml_downloader.db'}"
DATABASE_ECHO = os.getenv("DATABASE_ECHO", "False").lower() == "true"

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = LOGS_DIR / "xml_downloader.log"

MAX_PERIOD_DAYS = 30
MIN_PERIOD_DAYS = 1

PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "True").lower() == "true"
PLAYWRIGHT_TIMEOUT = 30000
PLAYWRIGHT_NAVIGATION_TIMEOUT = 60000

DEFAULT_NFSE_CONTRIBUINTE_URL = "https://www.nfse.gov.br/EmissorNacional/Login?ReturnUrl=%2fEmissorNacional"

MANIFEST_MAX_RETRIES = 5
MANIFEST_RETRY_DELAY = 3600
MANIFEST_CHECK_INTERVAL = 300

CACHE_HASH_ALGORITHM = "sha256"
CACHE_EXPIRATION_DAYS = 365

DOCUMENT_STATUS = {
    "LOCAL_CACHE": "Encontrado em cache local",
    "LOCAL_XML_VALIDO": "XML válido em cache local",
    "NSU_LOCALIZADO": "NSU localizado",
    "NSU_SEM_XML_COMPLETO": "NSU encontrado mas XML incompleto",
    "RAW_SALVO": "Retorno bruto salvo",
    "PORTAL_LOCALIZADO": "Localizado no portal",
    "PORTAL_BAIXADO": "Baixado do portal",
    "MANIFESTACAO_PENDENTE": "Aguardando manifestação",
    "MANIFESTADO": "Manifestação enviada",
    "AGUARDANDO_DISPONIBILIDADE": "Aguardando disponibilidade",
    "XML_PROCESSADO": "XML processado com sucesso",
    "XML_INVALIDO": "XML inválido ou corrompido",
    "ERRO_LOGIN": "Erro de autenticação",
    "ERRO_DOWNLOAD": "Erro ao baixar",
    "ERRO_PARSE": "Erro ao processar XML",
    "NAO_LOCALIZADO": "Não localizado",
}

DOCUMENT_TYPES = {
    "NFE_ENTRADA": "NF-e de Entrada",
    "NFE_SAIDA": "NF-e de Saída",
    "NFSE_PRESTADA": "NFS-e Prestada",
    "NFSE_TOMADA": "NFS-e Tomada",
    "CTE": "CT-e (Futuro)",
    "NFCE": "NFC-e (Futuro)",
}

EXECUTION_MODES = {
    "AUTOMATICO": "Automático (todos os motores)",
    "CACHE_ONLY": "Somente cache",
    "PORTAL_ONLY": "Somente portal",
    "NSU_ONLY": "Somente NSU",
    "MANIFEST_ONLY": "Somente manifestação",
}

ENVIRONMENTS = {
    "PRODUCAO": "Produção",
    "HOMOLOGACAO": "Homologação",
}

TAX_REGIMES = {
    "SIMPLES": "Simples Nacional",
    "LUCRO_REAL": "Lucro Real",
    "LUCRO_PRESUMIDO": "Lucro Presumido",
}
