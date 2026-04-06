"""
Repositório de dados para operações CRUD
"""
from typing import List, Optional
from datetime import date, datetime, time
from sqlalchemy.orm import Session
from sqlalchemy import or_, cast, String
from app.db.models import Empresa, Credencial, JobDownload, Documento, LogEvento, FilaManifestacao, CadastroLicenca, LicencaLocal
from app.utils.logger import log


class AttrDict(dict):
    """Dicionário com acesso por atributo para compatibilidade entre telas antigas e novas."""

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as exc:
            raise AttributeError(item) from exc

    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__



class CredencialRepository:
    """Repositório para operações com Credencial"""

    def __init__(self, session: Session):
        self.session = session

    def create(self, empresa_id: int, tipo_credencial: str, **kwargs) -> Credencial:
        """Cria nova credencial"""
        credencial = Credencial(
            empresa_id=empresa_id,
            tipo_credencial=tipo_credencial,
            **kwargs,
        )
        self.session.add(credencial)
        self.session.commit()
        log.info(f"Credencial criada para empresa {empresa_id} ({tipo_credencial})")
        return credencial

    def get_by_id(self, credencial_id: int) -> Optional[Credencial]:
        """Busca credencial por ID"""
        return self.session.query(Credencial).filter(Credencial.id == credencial_id).first()

    def get_ativo_by_empresa(self, empresa_id: int, tipo_credencial: Optional[str] = None) -> Optional[Credencial]:
        """Retorna a credencial ativa da empresa"""
        query = self.session.query(Credencial).filter(
            Credencial.empresa_id == empresa_id,
            Credencial.ativo == True,
        )
        if tipo_credencial:
            query = query.filter(Credencial.tipo_credencial == tipo_credencial)
        return query.order_by(Credencial.id.desc()).first()

    def list_by_empresa(self, empresa_id: int, ativo_only: bool = True) -> List[Credencial]:
        """Lista credenciais da empresa"""
        query = self.session.query(Credencial).filter(Credencial.empresa_id == empresa_id)
        if ativo_only:
            query = query.filter(Credencial.ativo == True)
        return query.order_by(Credencial.id.desc()).all()

    def update(self, credencial_id: int, **kwargs) -> Optional[Credencial]:
        """Atualiza credencial"""
        credencial = self.get_by_id(credencial_id)
        if credencial:
            for key, value in kwargs.items():
                if hasattr(credencial, key):
                    setattr(credencial, key, value)
            self.session.commit()
            log.info(f"Credencial atualizada: {credencial_id}")
        return credencial

    def delete(self, credencial_id: int) -> bool:
        """Remove credencial"""
        credencial = self.get_by_id(credencial_id)
        if credencial:
            self.session.delete(credencial)
            self.session.commit()
            log.info(f"Credencial removida: {credencial_id}")
            return True
        return False


class EmpresaRepository:
    """Repositório para operações com Empresa"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, razao_social: str, cnpj: str, uf: str, **kwargs) -> Empresa:
        """Cria nova empresa"""
        empresa = Empresa(razao_social=razao_social, cnpj=cnpj, uf=uf, **kwargs)
        self.session.add(empresa)
        self.session.commit()
        log.info(f"Empresa criada: {cnpj} - {razao_social}")
        return empresa
    
    def get_by_cnpj(self, cnpj: str) -> Optional[Empresa]:
        """Busca empresa por CNPJ"""
        return self.session.query(Empresa).filter(Empresa.cnpj == cnpj).first()
    
    def get_by_id(self, empresa_id: int) -> Optional[Empresa]:
        """Busca empresa por ID"""
        return self.session.query(Empresa).filter(Empresa.id == empresa_id).first()
    
    def list_all(self, ativo_only: bool = True) -> List[Empresa]:
        """Lista todas as empresas"""
        query = self.session.query(Empresa)
        if ativo_only:
            query = query.filter(Empresa.ativo == True)
        return query.all()
    
    def update(self, empresa_id: int, **kwargs) -> Optional[Empresa]:
        """Atualiza empresa"""
        empresa = self.get_by_id(empresa_id)
        if empresa:
            for key, value in kwargs.items():
                if hasattr(empresa, key):
                    setattr(empresa, key, value)
            self.session.commit()
            log.info(f"Empresa atualizada: {empresa_id}")
        return empresa
    
    def delete(self, empresa_id: int) -> bool:
        """Deleta empresa"""
        empresa = self.get_by_id(empresa_id)
        if empresa:
            self.session.delete(empresa)
            self.session.commit()
            log.info(f"Empresa deletada: {empresa_id}")
            return True
        return False


class DocumentoRepository:
    """Repositório para operações com Documento"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, empresa_id: int, tipo_documento: str, **kwargs) -> Documento:
        """Cria novo documento"""
        documento = Documento(empresa_id=empresa_id, tipo_documento=tipo_documento, **kwargs)
        self.session.add(documento)
        self.session.commit()
        return documento
    
    def get_by_chave(self, empresa_id: int, chave: str) -> Optional[Documento]:
        """Busca documento por chave"""
        return self.session.query(Documento).filter(
            Documento.empresa_id == empresa_id,
            Documento.chave == chave
        ).first()
    
    def get_by_id(self, documento_id: int) -> Optional[Documento]:
        """Busca documento por ID"""
        return self.session.query(Documento).filter(Documento.id == documento_id).first()
    
    def list_by_empresa(self, empresa_id: int, tipo_documento: Optional[str] = None) -> List[Documento]:
        """Lista documentos de uma empresa"""
        query = self.session.query(Documento).filter(Documento.empresa_id == empresa_id)
        if tipo_documento:
            query = query.filter(Documento.tipo_documento == tipo_documento)
        return query.all()
    
    def _as_datetime_bounds(self, start_date=None, end_date=None):
        """Normaliza limites de data para consultas por período."""
        start_dt = None
        end_dt = None

        if isinstance(start_date, datetime):
            start_dt = start_date
        elif isinstance(start_date, date):
            start_dt = datetime.combine(start_date, time.min)

        if isinstance(end_date, datetime):
            end_dt = end_date
        elif isinstance(end_date, date):
            end_dt = datetime.combine(end_date, time.max)

        return start_dt, end_dt

    def _to_report_payload(self, documento: Documento) -> AttrDict:
        """Converte Documento em payload compatível com as telas de relatórios."""
        tipo_documento = (getattr(documento, "tipo_documento", "") or "").strip()
        situacao = (getattr(documento, "situacao", "") or "").strip()
        status = (getattr(documento, "status", "") or "").strip() or situacao or "VALIDO"
        status_upper = status.upper()
        situacao_upper = situacao.upper()
        cancelada = "CANCEL" in status_upper or "CANCEL" in situacao_upper
        valor_total = float(getattr(documento, "valor_total", 0) or 0)

        cliente = documento.destinatario_nome or documento.emitente_nome or "Desconhecido"
        if "TOMADA" in tipo_documento.upper() or "ENTRADA" in tipo_documento.upper():
            cliente = documento.emitente_nome or documento.destinatario_nome or "Desconhecido"

        servico_descricao = tipo_documento or documento.schema or documento.modelo or "Documento fiscal"

        return AttrDict(
            id=documento.id,
            empresa_id=documento.empresa_id,
            tipo_documento=tipo_documento,
            chave=documento.chave,
            numero=documento.numero,
            serie=documento.serie,
            modelo=documento.modelo,
            data_emissao=documento.data_emissao,
            emitente_cnpj=documento.emitente_cnpj,
            emitente_nome=documento.emitente_nome,
            destinatario_cnpj=documento.destinatario_cnpj,
            destinatario_nome=documento.destinatario_nome,
            valor_total=valor_total,
            valor_servico=valor_total,
            situacao=situacao or status,
            status="CANCELADA" if cancelada else (situacao or status or "VALIDO"),
            status_cancelada=cancelada,
            tomador_razao_social=cliente,
            descricao_servico=servico_descricao,
            servico_descricao=servico_descricao,
            valor_issqn=0.0,
            valor_ir=0.0,
            valor_irrf=0.0,
            valor_pis=0.0,
            valor_cofins=0.0,
            valor_csll=0.0,
            issqn_valor=0.0,
            irrf_valor=0.0,
            pis_valor=0.0,
            cofins_valor=0.0,
            csll_valor=0.0,
            origem_captura=documento.origem_captura,
            schema=documento.schema,
            arquivo_xml=documento.arquivo_xml,
        )

    def get_by_empresa_and_period(self, empresa_id: int, start_date=None, end_date=None, tipo_documento: Optional[str] = None) -> List[AttrDict]:
        """Retorna documentos da empresa no período em formato compatível com os relatórios."""
        query = self.session.query(Documento).filter(Documento.empresa_id == empresa_id)
        start_dt, end_dt = self._as_datetime_bounds(start_date, end_date)

        if start_dt:
            query = query.filter(Documento.data_emissao >= start_dt)
        if end_dt:
            query = query.filter(Documento.data_emissao <= end_dt)
        if tipo_documento and tipo_documento != "Todos":
            query = query.filter(Documento.tipo_documento == tipo_documento)

        documentos = query.order_by(Documento.data_emissao.asc(), Documento.id.asc()).all()
        return [self._to_report_payload(doc) for doc in documentos]

    def _parse_report_value(self, search_text: str) -> Optional[float]:
        raw = (search_text or "").strip().upper().replace("R$", "").replace(" ", "")
        if not raw:
            return None
        try:
            normalized = raw.replace(".", "").replace(",", ".")
            return float(normalized)
        except ValueError:
            pass
        try:
            return float(raw.replace(",", "."))
        except ValueError:
            return None

    def search_for_reports(self, empresa_id: int, start_date=None, end_date=None, tipo_documento=None, search_text=None) -> List[Documento]:
        """Busca avançada de documentos para relatórios"""
        query = self.session.query(Documento).filter(Documento.empresa_id == empresa_id)
        start_dt, end_dt = self._as_datetime_bounds(start_date, end_date)
        
        if start_dt:
            query = query.filter(Documento.data_emissao >= start_dt)
        if end_dt:
            query = query.filter(Documento.data_emissao <= end_dt)
        if tipo_documento and tipo_documento != "Todos":
            query = query.filter(Documento.tipo_documento == tipo_documento)
        if search_text:
            term = f"%{search_text}%"
            filters = [
                Documento.emitente_nome.ilike(term),
                Documento.emitente_cnpj.ilike(term),
                Documento.destinatario_nome.ilike(term),
                Documento.destinatario_cnpj.ilike(term),
                Documento.numero.ilike(term),
                Documento.chave.ilike(term),
                cast(Documento.valor_total, String).ilike(term),
            ]

            numeric_value = self._parse_report_value(search_text)
            if numeric_value is not None:
                filters.append(Documento.valor_total >= numeric_value - 0.01)
                filters.append(Documento.valor_total <= numeric_value + 0.01)
                query = query.filter(or_(
                    Documento.emitente_nome.ilike(term),
                    Documento.emitente_cnpj.ilike(term),
                    Documento.destinatario_nome.ilike(term),
                    Documento.destinatario_cnpj.ilike(term),
                    Documento.numero.ilike(term),
                    Documento.chave.ilike(term),
                    cast(Documento.valor_total, String).ilike(term),
                    ((Documento.valor_total >= numeric_value - 0.01) & (Documento.valor_total <= numeric_value + 0.01)),
                ))
            else:
                query = query.filter(or_(*filters))
            
        return query.order_by(Documento.data_emissao.desc()).all()
    
    def list_by_status(self, empresa_id: int, status: str) -> List[Documento]:
        """Lista documentos por status"""
        return self.session.query(Documento).filter(
            Documento.empresa_id == empresa_id,
            Documento.status == status
        ).all()
    
    def update(self, documento_id: int, **kwargs) -> Optional[Documento]:
        """Atualiza documento"""
        documento = self.get_by_id(documento_id)
        if documento:
            for key, value in kwargs.items():
                if hasattr(documento, key):
                    setattr(documento, key, value)
            self.session.commit()
        return documento
    
    def update_status(self, documento_id: int, status: str, **kwargs) -> Optional[Documento]:
        """Atualiza status do documento"""
        from datetime import datetime
        kwargs['status'] = status
        kwargs['ultimo_evento_em'] = datetime.utcnow()
        return self.update(documento_id, **kwargs)

    def delete(self, documento_id: int) -> bool:
        """Remove documento do banco de dados."""
        documento = self.get_by_id(documento_id)
        if documento:
            self.session.delete(documento)
            self.session.commit()
            log.info(f"Documento removido: {documento_id}")
            return True
        return False


class JobDownloadRepository:
    """Repositório para operações com JobDownload"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, empresa_id: int, tipo_documento: str, data_inicial, data_final, **kwargs) -> JobDownload:
        """Cria novo job"""
        job = JobDownload(
            empresa_id=empresa_id,
            tipo_documento=tipo_documento,
            data_inicial=data_inicial,
            data_final=data_final,
            **kwargs
        )
        self.session.add(job)
        self.session.commit()
        log.info(f"Job criado: {job.id} - {tipo_documento}")
        return job
    
    def get_by_id(self, job_id: int) -> Optional[JobDownload]:
        """Busca job por ID"""
        return self.session.query(JobDownload).filter(JobDownload.id == job_id).first()
    
    def list_by_empresa(self, empresa_id: int) -> List[JobDownload]:
        """Lista jobs de uma empresa"""
        return self.session.query(JobDownload).filter(JobDownload.empresa_id == empresa_id).all()
    
    def update(self, job_id: int, **kwargs) -> Optional[JobDownload]:
        """Atualiza job"""
        job = self.get_by_id(job_id)
        if job:
            for key, value in kwargs.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            self.session.commit()
        return job


class LogEventoRepository:
    """Repositório para operações com LogEvento"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, job_id: int, origem: str, mensagem: str, **kwargs) -> LogEvento:
        """Cria novo log"""
        log_evento = LogEvento(job_id=job_id, origem=origem, mensagem=mensagem, **kwargs)
        self.session.add(log_evento)
        self.session.commit()
        return log_evento
    
    def list_by_job(self, job_id: int) -> List[LogEvento]:
        """Lista logs de um job"""
        return self.session.query(LogEvento).filter(LogEvento.job_id == job_id).all()


class LicencaCadastroRepository:
    """Repositório para o cadastro do comprador do software."""

    def __init__(self, session: Session):
        self.session = session

    def get_singleton(self) -> Optional[CadastroLicenca]:
        return self.session.query(CadastroLicenca).order_by(CadastroLicenca.id.asc()).first()

    def save(self, **kwargs) -> CadastroLicenca:
        cadastro = self.get_singleton()
        if cadastro is None:
            cadastro = CadastroLicenca(**kwargs)
            self.session.add(cadastro)
        else:
            for key, value in kwargs.items():
                if hasattr(cadastro, key):
                    setattr(cadastro, key, value)
        self.session.commit()
        log.info("Cadastro de licença salvo/atualizado")
        return cadastro


class LicencaLocalRepository:
    """Repositório do cache local da licença/trial."""

    def __init__(self, session: Session):
        self.session = session

    def get_singleton(self) -> Optional[LicencaLocal]:
        return self.session.query(LicencaLocal).order_by(LicencaLocal.id.asc()).first()

    def save(self, **kwargs) -> LicencaLocal:
        licenca = self.get_singleton()
        if licenca is None:
            licenca = LicencaLocal(**kwargs)
            self.session.add(licenca)
        else:
            for key, value in kwargs.items():
                if hasattr(licenca, key):
                    setattr(licenca, key, value)
        self.session.commit()
        return licenca
