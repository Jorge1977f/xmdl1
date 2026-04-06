"""
Modelos de banco de dados do XML Downloader
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Float, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Empresa(Base):
    """Modelo de empresa"""
    __tablename__ = "empresas"

    id = Column(Integer, primary_key=True)
    razao_social = Column(String(255), nullable=False)
    nome_fantasia = Column(String(255), nullable=True)
    cnpj = Column(String(14), nullable=False, unique=True, index=True)
    inscricao_estadual = Column(String(30), nullable=True)
    inscricao_municipal = Column(String(30), nullable=True)
    regime_tributario = Column(String(50), nullable=True)
    ambiente = Column(String(50), default="PRODUCAO")
    certificado_tipo = Column(String(20), default="A1")
    municipio = Column(String(120), nullable=True)
    uf = Column(String(2), nullable=False)
    matriz_filial = Column(String(20), nullable=True)
    data_abertura = Column(String(20), nullable=True)
    porte = Column(String(50), nullable=True)
    natureza_juridica = Column(String(255), nullable=True)
    atividade_principal = Column(Text, nullable=True)
    atividades_secundarias = Column(Text, nullable=True)
    logradouro = Column(String(255), nullable=True)
    numero = Column(String(50), nullable=True)
    complemento = Column(String(255), nullable=True)
    cep = Column(String(20), nullable=True)
    bairro = Column(String(100), nullable=True)
    email = Column(String(255), nullable=True)
    telefone = Column(String(100), nullable=True)
    situacao_cadastral = Column(String(50), nullable=True)
    data_situacao_cadastral = Column(String(20), nullable=True)
    motivo_situacao_cadastral = Column(String(255), nullable=True)
    situacao_especial = Column(String(255), nullable=True)
    data_situacao_especial = Column(String(20), nullable=True)
    efr = Column(String(255), nullable=True)
    ativo = Column(Boolean, default=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    credenciais = relationship("Credencial", back_populates="empresa", cascade="all, delete-orphan")
    jobs = relationship("JobDownload", back_populates="empresa", cascade="all, delete-orphan")
    documentos = relationship("Documento", back_populates="empresa", cascade="all, delete-orphan")
    manifestacoes = relationship("FilaManifestacao", back_populates="empresa", cascade="all, delete-orphan")


class Credencial(Base):
    """Modelo de credencial (certificado ou login)"""
    __tablename__ = "credenciais"

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    tipo_credencial = Column(String(50), nullable=False)
    login = Column(String(255), nullable=True)
    senha = Column(String(255), nullable=True)
    cert_path = Column(String(500), nullable=True)
    cert_senha = Column(String(255), nullable=True)
    portal_url = Column(String(500), nullable=True)
    downloads_dir = Column(String(500), nullable=True)
    modo_login = Column(String(50), default="MANUAL_ASSISTIDO")
    navegador_headless = Column(Boolean, default=False)
    tempo_espera_login = Column(Integer, default=120)
    ultimo_nsu_api = Column(Integer, nullable=True)
    ultimo_nsu_api_prestadas = Column(Integer, nullable=True)
    ultimo_nsu_api_tomadas = Column(Integer, nullable=True)
    lote_nsu_api = Column(Integer, nullable=True)
    ambiente = Column(String(50), default="PRODUCAO")
    ativo = Column(Boolean, default=True)
    ultima_validacao = Column(DateTime, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    empresa = relationship("Empresa", back_populates="credenciais")


class JobDownload(Base):
    """Modelo de job de download"""
    __tablename__ = "jobs_download"

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    tipo_documento = Column(String(50), nullable=False)
    data_inicial = Column(DateTime, nullable=False)
    data_final = Column(DateTime, nullable=False)
    modo_execucao = Column(String(50), default="AUTOMATICO")
    status = Column(String(50), default="PENDENTE")
    inicio_em = Column(DateTime, nullable=True)
    fim_em = Column(DateTime, nullable=True)
    total_encontrado = Column(Integer, default=0)
    total_baixado = Column(Integer, default=0)
    total_erros = Column(Integer, default=0)
    log_resumo = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    empresa = relationship("Empresa", back_populates="jobs")
    lotes = relationship("LoteExecucao", back_populates="job", cascade="all, delete-orphan")
    eventos = relationship("LogEvento", back_populates="job", cascade="all, delete-orphan")


class LoteExecucao(Base):
    """Modelo de lote de execução"""
    __tablename__ = "lotes_execucao"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs_download.id"), nullable=False)
    data_inicial = Column(DateTime, nullable=False)
    data_final = Column(DateTime, nullable=False)
    status = Column(String(50), default="PENDENTE")
    motor_executado = Column(String(50), nullable=True)
    tentativas = Column(Integer, default=0)
    iniciado_em = Column(DateTime, nullable=True)
    concluido_em = Column(DateTime, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    job = relationship("JobDownload", back_populates="lotes")


class Documento(Base):
    """Modelo de documento (NF-e, NFS-e, etc)"""
    __tablename__ = "documentos"

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    tipo_documento = Column(String(50), nullable=False)
    chave = Column(String(44), nullable=True, index=True)
    nsu = Column(String(50), nullable=True)
    numero = Column(String(20), nullable=True)
    serie = Column(String(10), nullable=True)
    modelo = Column(String(10), nullable=True)
    data_emissao = Column(DateTime, nullable=True)
    emitente_cnpj = Column(String(14), nullable=True)
    emitente_nome = Column(String(255), nullable=True)
    destinatario_cnpj = Column(String(14), nullable=True)
    destinatario_nome = Column(String(255), nullable=True)
    valor_total = Column(Float, default=0.0)
    situacao = Column(String(50), nullable=True)
    origem_captura = Column(String(50), nullable=True)
    schema = Column(String(50), nullable=True)
    hash_xml = Column(String(64), nullable=True, index=True)
    arquivo_xml = Column(String(500), nullable=True)
    arquivo_raw = Column(String(500), nullable=True)
    manifestacao_status = Column(String(50), nullable=True)
    status = Column(String(50), default="NAO_LOCALIZADO", index=True)
    ultimo_evento_em = Column(DateTime, default=datetime.utcnow)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    empresa = relationship("Empresa", back_populates="documentos")


class LogEvento(Base):
    """Modelo de log de eventos"""
    __tablename__ = "logs_evento"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs_download.id"), nullable=False)
    documento_id = Column(Integer, ForeignKey("documentos.id"), nullable=True)
    nivel = Column(String(20), default="INFO")
    origem = Column(String(100), nullable=False)
    mensagem = Column(String(500), nullable=False)
    detalhe = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)

    job = relationship("JobDownload", back_populates="eventos")


class FilaManifestacao(Base):
    """Modelo de fila de manifestação"""
    __tablename__ = "filas_manifestacao"

    id = Column(Integer, primary_key=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    chave = Column(String(44), nullable=False, index=True)
    status = Column(String(50), default="PENDENTE")
    tentativas = Column(Integer, default=0)
    proxima_tentativa_em = Column(DateTime, nullable=True)
    ultimo_retorno = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    empresa = relationship("Empresa", back_populates="manifestacoes")


class CadastroLicenca(Base):
    """Cadastro do comprador/licenciante do software."""
    __tablename__ = "cadastro_licenca"

    id = Column(Integer, primary_key=True)
    nome = Column(String(255), nullable=True)
    documento = Column(String(20), nullable=True, index=True)
    email = Column(String(255), nullable=True)
    telefone = Column(String(40), nullable=True)
    machine_id = Column(String(128), nullable=True, index=True)
    machine_name = Column(String(255), nullable=True)
    install_id = Column(String(64), nullable=True, unique=True, index=True)
    backend_cliente_id = Column(String(64), nullable=True)
    backend_instalacao_id = Column(String(64), nullable=True)
    token_ativacao = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LicencaLocal(Base):
    """Cache local do status vindo do backend de licenciamento."""
    __tablename__ = "licenca_local"

    id = Column(Integer, primary_key=True)
    cadastro_id = Column(Integer, ForeignKey("cadastro_licenca.id"), nullable=True)
    status = Column(String(50), default="NAO_CADASTRADO", index=True)
    origem_tempo = Column(String(30), default="LOCAL_DEV")
    mensagem_status = Column(Text, nullable=True)
    trial_iniciado_em = Column(DateTime, nullable=True)
    trial_expira_em = Column(DateTime, nullable=True)
    ultima_sincronizacao_em = Column(DateTime, nullable=True)
    ultimo_server_time = Column(DateTime, nullable=True)
    ultimo_erro = Column(Text, nullable=True)
    downloads_liberados = Column(Boolean, default=True)
    licencas_total = Column(Integer, default=0)
    licencas_em_uso = Column(Integer, default=0)
    pedido_pendente_id = Column(String(64), nullable=True)
    pix_copia_cola = Column(Text, nullable=True)
    pix_qr_code_base64 = Column(Text, nullable=True)
    pix_expira_em = Column(DateTime, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    cadastro = relationship("CadastroLicenca")
