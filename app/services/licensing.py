"""Serviço de licenciamento com cache local e sincronização opcional com backend."""
from __future__ import annotations

import base64
import hashlib
import os
import platform
import socket
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import requests

from app.db import get_db_session, LicencaCadastroRepository, LicencaLocalRepository
from app.utils.logger import log
from config.settings import (
    APP_VERSION,
    LICENSE_ALLOW_HTTP_LOCAL,
    LICENSE_API_TIMEOUT_SECONDS,
    LICENSE_API_URL,
    LICENSE_DISCOUNT_RATE,
    LICENSE_DISCOUNT_START_FROM,
    LICENSE_OFFLINE_GRACE_DAYS,
    LICENSE_PRICE_PER_MACHINE,
    LICENSE_TRIAL_DAYS,
)


@dataclass
class BackendHealth:
    ok: bool = False
    mode: str = "unknown"
    database_ready: bool = False
    mercadopago_ready: bool = False
    webhook_url: str = ""
    detail: str = ""


STATUS_NAO_CADASTRADO = "NAO_CADASTRADO"
STATUS_TRIAL = "TRIAL"
STATUS_ATIVA = "ATIVA"
STATUS_TRIAL_EXPIRADO = "TRIAL_EXPIRADO"
STATUS_PAGAMENTO_PENDENTE = "PAGAMENTO_PENDENTE"
STATUS_BLOQUEADA = "BLOQUEADA"
STATUS_DEV_LOCAL = "LOCAL_DEV"


@dataclass
class LicenseSnapshot:
    status: str
    status_label: str
    message: str
    buyer_name: str = ""
    documento: str = ""
    email: str = ""
    telefone: str = ""
    machine_id: str = ""
    machine_name: str = ""
    trial_expires_at: Optional[datetime] = None
    trial_started_at: Optional[datetime] = None
    days_left: Optional[int] = None
    downloads_allowed: bool = True
    backend_configured: bool = False
    last_sync_at: Optional[datetime] = None
    server_time: Optional[datetime] = None
    licenses_total: int = 0
    licenses_in_use: int = 0
    pending_order_id: str = ""
    pix_copy_paste: str = ""
    pix_qr_code_base64: str = ""
    pix_expires_at: Optional[datetime] = None
    offline_error: str = ""


class LicensingService:
    """Camada central de licenciamento e trial."""

    def __init__(self, session=None):
        self.session = session or get_db_session()
        self.cadastro_repo = LicencaCadastroRepository(self.session)
        self.licenca_repo = LicencaLocalRepository(self.session)
        self._http = requests.Session()
        self._http.headers.update({
            "User-Agent": f"XMDL/{APP_VERSION}",
            "Accept": "application/json",
        })

    @staticmethod
    def get_machine_name() -> str:
        return platform.node() or socket.gethostname() or "maquina-desconhecida"

    @staticmethod
    def _read_windows_machine_guid() -> Optional[str]:
        if os.name != "nt":
            return None
        try:
            import winreg  # type: ignore

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
                value, _ = winreg.QueryValueEx(key, "MachineGuid")
                return str(value).strip() or None
        except Exception:
            return None

    @staticmethod
    def _read_linux_machine_id() -> Optional[str]:
        for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    value = handle.read().strip()
                    if value:
                        return value
            except Exception:
                continue
        return None

    @staticmethod
    def _read_macos_platform_uuid() -> Optional[str]:
        if platform.system().lower() != "darwin":
            return None
        try:
            output = subprocess.check_output(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], text=True)
            for line in output.splitlines():
                if "IOPlatformUUID" in line:
                    return line.split("=", 1)[1].strip().strip('"') or None
        except Exception:
            return None
        return None

    @classmethod
    def get_machine_id(cls) -> str:
        raw_id = (
            cls._read_windows_machine_guid()
            or cls._read_linux_machine_id()
            or cls._read_macos_platform_uuid()
            or str(uuid.getnode())
        )
        seed = f"stable-machine|{raw_id}"
        return hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()

    @staticmethod
    def _new_install_id() -> str:
        return uuid.uuid4().hex

    @staticmethod
    def _parse_dt(value: Any) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value.replace(tzinfo=None)
        text = str(value).strip()
        if not text:
            return None
        text = text.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except Exception:
            return None

    @staticmethod
    def _dt_to_iso(value: Optional[datetime]) -> Optional[str]:
        if not value:
            return None
        return value.replace(microsecond=0).isoformat() + "Z"

    @staticmethod
    def _validate_backend_url(url: str) -> tuple[bool, str]:
        normalized = (url or "").strip().rstrip("/")
        if not normalized:
            return True, ""
        parsed = urlparse(normalized)
        if parsed.scheme == "https":
            return True, normalized
        if parsed.scheme == "http" and LICENSE_ALLOW_HTTP_LOCAL and parsed.hostname in {"127.0.0.1", "localhost"}:
            return True, normalized
        return False, normalized

    def _get_api_base_url(self) -> tuple[Optional[str], Optional[str]]:
        ok, normalized = self._validate_backend_url(LICENSE_API_URL)
        if ok:
            return (normalized or None), None
        return None, "A API de licença deve usar HTTPS. HTTP só é aceito para localhost se XMLDLK_LICENSE_ALLOW_HTTP_LOCAL=True."

    def _ensure_local_records(self):
        cadastro = self.cadastro_repo.get_singleton()
        if cadastro is None:
            cadastro = self.cadastro_repo.save(
                machine_id=self.get_machine_id(),
                machine_name=self.get_machine_name(),
                install_id=self._new_install_id(),
            )
        else:
            changed = False
            if not cadastro.machine_id:
                cadastro.machine_id = self.get_machine_id()
                changed = True
            if not cadastro.machine_name:
                cadastro.machine_name = self.get_machine_name()
                changed = True
            if not cadastro.install_id:
                cadastro.install_id = self._new_install_id()
                changed = True
            if changed:
                self.session.commit()

        licenca = self.licenca_repo.get_singleton()
        api_base_url, api_error = self._get_api_base_url()
        if licenca is None:
            licenca = self.licenca_repo.save(
                cadastro_id=cadastro.id,
                status=STATUS_NAO_CADASTRADO,
                origem_tempo="LOCAL_DEV" if not api_base_url else "BACKEND",
                downloads_liberados=True,
                mensagem_status=api_error,
            )
        elif not licenca.cadastro_id:
            licenca.cadastro_id = cadastro.id
            self.session.commit()
        if api_error:
            licenca.ultimo_erro = api_error
            licenca.mensagem_status = api_error
            self.session.commit()
        return cadastro, licenca

    def _has_required_registration(self, cadastro) -> bool:
        return bool(
            (cadastro.nome or "").strip()
            and (cadastro.documento or "").strip()
            and (cadastro.email or "").strip()
            and (cadastro.telefone or "").strip()
        )

    def _compute_days_left(self, expires_at: Optional[datetime], now_utc: Optional[datetime] = None) -> Optional[int]:
        if not expires_at:
            return None
        now_utc = now_utc or datetime.utcnow()
        delta = expires_at - now_utc
        return max(0, delta.days + (1 if delta.seconds > 0 else 0))

    def calculate_price(self, quantity: int) -> dict[str, Any]:
        qty = max(1, int(quantity or 1))
        base_qty = min(qty, LICENSE_DISCOUNT_START_FROM - 1)
        discounted_qty = max(0, qty - (LICENSE_DISCOUNT_START_FROM - 1))
        unit_discounted = round(LICENSE_PRICE_PER_MACHINE * (1 - LICENSE_DISCOUNT_RATE), 2)
        total = round(base_qty * LICENSE_PRICE_PER_MACHINE + discounted_qty * unit_discounted, 2)
        return {
            "quantity": qty,
            "base_quantity": base_qty,
            "discounted_quantity": discounted_qty,
            "base_unit_price": round(LICENSE_PRICE_PER_MACHINE, 2),
            "discounted_unit_price": unit_discounted,
            "total": total,
        }

    def save_buyer(self, nome: str, documento: str, email: str, telefone: str) -> LicenseSnapshot:
        cadastro, licenca = self._ensure_local_records()
        cadastro = self.cadastro_repo.save(
            nome=(nome or "").strip(),
            documento=(documento or "").strip(),
            email=(email or "").strip(),
            telefone=(telefone or "").strip(),
            machine_id=cadastro.machine_id,
            machine_name=cadastro.machine_name,
            install_id=cadastro.install_id,
            backend_cliente_id=cadastro.backend_cliente_id,
            backend_instalacao_id=cadastro.backend_instalacao_id,
            token_ativacao=cadastro.token_ativacao,
        )

        api_base_url, api_error = self._get_api_base_url()
        if api_error:
            licenca.status = STATUS_BLOQUEADA
            licenca.downloads_liberados = False
            licenca.mensagem_status = api_error
            licenca.ultimo_erro = api_error
            self.session.commit()
        elif not api_base_url:
            now = datetime.utcnow()
            if not licenca.trial_iniciado_em:
                licenca.trial_iniciado_em = now
                licenca.trial_expira_em = now + timedelta(days=LICENSE_TRIAL_DAYS)
            licenca.status = STATUS_TRIAL if (licenca.trial_expira_em and licenca.trial_expira_em > now) else STATUS_TRIAL_EXPIRADO
            licenca.downloads_liberados = licenca.status == STATUS_TRIAL
            licenca.mensagem_status = (
                "Modo local de desenvolvimento ativo. Configure o backend de licença para usar a data do servidor."
            )
            licenca.ultima_sincronizacao_em = now
            licenca.ultimo_server_time = now
            licenca.ultimo_erro = None
            self.session.commit()
        else:
            self.sync_status(force=True)
        return self.get_snapshot(force_sync=False)

    def _apply_backend_payload(self, cadastro, licenca, payload: dict[str, Any]) -> None:
        server_time = self._parse_dt(payload.get("server_time")) or datetime.utcnow()
        trial = payload.get("trial") or {}
        license_data = payload.get("license") or {}
        buyer = payload.get("buyer") or {}
        payment = payload.get("payment") or {}

        if buyer:
            cadastro.nome = buyer.get("nome") or cadastro.nome
            cadastro.documento = buyer.get("documento") or cadastro.documento
            cadastro.email = buyer.get("email") or cadastro.email
            cadastro.telefone = buyer.get("telefone") or cadastro.telefone

        cadastro.backend_cliente_id = payload.get("client_id") or cadastro.backend_cliente_id
        cadastro.backend_instalacao_id = payload.get("installation_id") or cadastro.backend_instalacao_id
        cadastro.token_ativacao = payload.get("token") or cadastro.token_ativacao

        licenca.status = license_data.get("status") or STATUS_TRIAL
        licenca.origem_tempo = "BACKEND"
        licenca.mensagem_status = license_data.get("message") or payload.get("message") or "Status sincronizado com o servidor."
        licenca.trial_iniciado_em = self._parse_dt(trial.get("started_at")) or licenca.trial_iniciado_em
        licenca.trial_expira_em = self._parse_dt(trial.get("expires_at")) or licenca.trial_expira_em
        licenca.ultima_sincronizacao_em = datetime.utcnow()
        licenca.ultimo_server_time = server_time
        licenca.ultimo_erro = None
        licenca.downloads_liberados = bool(license_data.get("downloads_allowed", licenca.status in {STATUS_TRIAL, STATUS_ATIVA}))
        licenca.licencas_total = int(license_data.get("licenses_total") or 0)
        licenca.licencas_em_uso = int(license_data.get("licenses_in_use") or 0)
        licenca.pedido_pendente_id = str(payment.get("order_id") or "")
        licenca.pix_copia_cola = payment.get("pix_copy_paste") or ""
        licenca.pix_qr_code_base64 = payment.get("pix_qr_code_base64") or ""
        licenca.pix_expira_em = self._parse_dt(payment.get("expires_at"))
        self.session.commit()

    def _local_dev_snapshot(self, cadastro, licenca) -> LicenseSnapshot:
        now = datetime.utcnow()
        if self._has_required_registration(cadastro) and not licenca.trial_iniciado_em:
            licenca.trial_iniciado_em = now
            licenca.trial_expira_em = now + timedelta(days=LICENSE_TRIAL_DAYS)
            licenca.status = STATUS_TRIAL
            licenca.downloads_liberados = True
            licenca.ultima_sincronizacao_em = now
            licenca.ultimo_server_time = now
            licenca.mensagem_status = "Modo local de desenvolvimento ativo. Configure o backend de licença para usar a data do servidor."
            licenca.ultimo_erro = None
            self.session.commit()
        elif licenca.trial_expira_em and licenca.trial_expira_em <= now and licenca.status != STATUS_ATIVA:
            licenca.status = STATUS_TRIAL_EXPIRADO
            licenca.downloads_liberados = False
            self.session.commit()
        return self._build_snapshot(cadastro, licenca, backend_configured=False)

    def sync_status(self, force: bool = False) -> LicenseSnapshot:
        cadastro, licenca = self._ensure_local_records()
        api_base_url, api_error = self._get_api_base_url()

        if not self._has_required_registration(cadastro):
            licenca.status = STATUS_NAO_CADASTRADO
            licenca.downloads_liberados = True
            licenca.mensagem_status = "Preencha nome, CPF/CNPJ, e-mail e telefone para iniciar o teste."
            licenca.ultimo_erro = api_error
            self.session.commit()
            return self._build_snapshot(cadastro, licenca, backend_configured=bool(api_base_url))

        if api_error:
            licenca.status = STATUS_BLOQUEADA
            licenca.downloads_liberados = False
            licenca.mensagem_status = api_error
            licenca.ultimo_erro = api_error
            self.session.commit()
            return self._build_snapshot(cadastro, licenca, backend_configured=False)

        if not api_base_url:
            return self._local_dev_snapshot(cadastro, licenca)

        if not force and licenca.ultima_sincronizacao_em and (datetime.utcnow() - licenca.ultima_sincronizacao_em) < timedelta(minutes=5):
            return self._build_snapshot(cadastro, licenca, backend_configured=True)

        payload = {
            "buyer": {
                "nome": cadastro.nome,
                "documento": cadastro.documento,
                "email": cadastro.email,
                "telefone": cadastro.telefone,
            },
            "installation": {
                "machine_id": cadastro.machine_id,
                "machine_name": cadastro.machine_name,
                "install_id": cadastro.install_id,
                "app_version": APP_VERSION,
                "platform": platform.platform(),
            },
            "token": None,
        }
        try:
            response = self._http.post(
                f"{api_base_url}/api/licensing/installations/sync",
                json=payload,
                timeout=LICENSE_API_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json() or {}
            self._apply_backend_payload(cadastro, licenca, data)
        except Exception as exc:
            licenca.ultimo_erro = str(exc)
            licenca.ultima_sincronizacao_em = datetime.utcnow()
            if licenca.status not in {STATUS_ATIVA} or LICENSE_OFFLINE_GRACE_DAYS <= 0:
                licenca.downloads_liberados = False
                if not licenca.mensagem_status:
                    licenca.mensagem_status = "Sem comunicação com o servidor de licenças."
            self.session.commit()
            log.warning(f"Falha ao sincronizar licença: {exc}")
        return self._build_snapshot(cadastro, licenca, backend_configured=True)

    def get_backend_health(self) -> BackendHealth:
        api_base_url, api_error = self._get_api_base_url()
        if api_error:
            return BackendHealth(detail=api_error)
        if not api_base_url:
            return BackendHealth(detail="XMLDLK_LICENSE_API_URL não configurado.")
        try:
            response = self._http.get(
                f"{api_base_url}/health",
                timeout=LICENSE_API_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json() or {}
            return BackendHealth(
                ok=bool(data.get("ok")),
                mode=str(data.get("mode") or "unknown"),
                database_ready=bool(data.get("database_ready")),
                mercadopago_ready=bool(data.get("mercadopago_ready")),
                webhook_url=str(data.get("webhook_url") or ""),
                detail="",
            )
        except Exception as exc:
            log.warning(f"Falha ao consultar health do backend de licença: {exc}")
            return BackendHealth(detail=str(exc))

    def simulate_pending_payment(self) -> tuple[bool, str, LicenseSnapshot]:
        cadastro, licenca = self._ensure_local_records()
        api_base_url, api_error = self._get_api_base_url()
        if api_error:
            return False, api_error, self.get_snapshot(force_sync=False)
        if not api_base_url:
            return False, "O backend de licença ainda não está configurado no programa. Ajuste a variável XMLDLK_LICENSE_API_URL.", self.get_snapshot(force_sync=False)

        order_id = (licenca.pedido_pendente_id or "").strip()
        if not order_id:
            return False, "Não existe pedido Pix pendente para simular.", self.get_snapshot(force_sync=False)

        try:
            response = self._http.post(
                f"{api_base_url}/api/licensing/orders/{order_id}/simulate-payment",
                timeout=LICENSE_API_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json() or {}
            snapshot = self.sync_status(force=True)
            return True, str(data.get("message") or "Pagamento simulado com sucesso."), snapshot
        except Exception as exc:
            log.warning(f"Falha ao simular pagamento Pix: {exc}")
            return False, str(exc), self.get_snapshot(force_sync=False)

    def create_pix_order(self, quantity: int) -> tuple[bool, str, LicenseSnapshot]:
        cadastro, licenca = self._ensure_local_records()
        api_base_url, api_error = self._get_api_base_url()
        if not self._has_required_registration(cadastro):
            return False, "Preencha o cadastro do comprador antes de gerar o Pix.", self.get_snapshot(force_sync=False)
        if api_error:
            licenca.status = STATUS_BLOQUEADA
            licenca.downloads_liberados = False
            licenca.mensagem_status = api_error
            licenca.ultimo_erro = api_error
            self.session.commit()
            return False, api_error, self.get_snapshot(force_sync=False)
        if not api_base_url:
            return False, "O backend de licença ainda não está configurado no programa. Ajuste a variável XMLDLK_LICENSE_API_URL.", self.get_snapshot(force_sync=False)

        pricing = self.calculate_price(quantity)
        payload = {
            "buyer": {
                "nome": cadastro.nome,
                "documento": cadastro.documento,
                "email": cadastro.email,
                "telefone": cadastro.telefone,
            },
            "installation": {
                "machine_id": cadastro.machine_id,
                "machine_name": cadastro.machine_name,
                "install_id": cadastro.install_id,
                "app_version": APP_VERSION,
                "platform": platform.platform(),
            },
            "order": {
                "quantity": pricing["quantity"],
                "expected_total": pricing["total"],
            },
        }
        try:
            response = self._http.post(
                f"{api_base_url}/api/licensing/orders",
                json=payload,
                timeout=LICENSE_API_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json() or {}
            payment = data.get("payment") or data
            licenca.pedido_pendente_id = str(payment.get("order_id") or "")
            licenca.pix_copia_cola = payment.get("pix_copy_paste") or ""
            licenca.pix_qr_code_base64 = payment.get("pix_qr_code_base64") or ""
            licenca.pix_expira_em = self._parse_dt(payment.get("expires_at"))
            licenca.status = STATUS_PAGAMENTO_PENDENTE
            licenca.downloads_liberados = False
            licenca.mensagem_status = payment.get("message") or "Pedido Pix gerado."
            licenca.ultimo_erro = None
            self.session.commit()
            return True, licenca.mensagem_status, self.get_snapshot(force_sync=False)
        except Exception as exc:
            log.warning(f"Falha ao gerar pedido Pix: {exc}")
            return False, str(exc), self.get_snapshot(force_sync=False)

    def get_snapshot(self, force_sync: bool = False) -> LicenseSnapshot:
        if force_sync:
            return self.sync_status(force=True)
        cadastro, licenca = self._ensure_local_records()
        api_base_url, api_error = self._get_api_base_url()
        if api_error:
            licenca.status = STATUS_BLOQUEADA
            licenca.downloads_liberados = False
            licenca.mensagem_status = api_error
            licenca.ultimo_erro = api_error
            self.session.commit()
            return self._build_snapshot(cadastro, licenca, backend_configured=False)
        if not api_base_url:
            return self._local_dev_snapshot(cadastro, licenca)
        return self._build_snapshot(cadastro, licenca, backend_configured=True)

    def _build_snapshot(self, cadastro, licenca, backend_configured: bool) -> LicenseSnapshot:
        status = licenca.status or STATUS_NAO_CADASTRADO
        status_label = {
            STATUS_NAO_CADASTRADO: "Cadastro pendente",
            STATUS_TRIAL: "Teste ativo",
            STATUS_ATIVA: "Licença ativa",
            STATUS_TRIAL_EXPIRADO: "Teste expirado",
            STATUS_PAGAMENTO_PENDENTE: "Pagamento pendente",
            STATUS_BLOQUEADA: "Bloqueada",
            STATUS_DEV_LOCAL: "Desenvolvimento local",
        }.get(status, status)
        days_left = self._compute_days_left(licenca.trial_expira_em, licenca.ultimo_server_time or datetime.utcnow())
        message = licenca.mensagem_status or "Sem status de licença disponível."
        if status == STATUS_TRIAL and licenca.trial_expira_em:
            message = f"Você tem {days_left} dia(s) restantes para testar. Após isso, novos downloads serão bloqueados."
        elif status == STATUS_TRIAL_EXPIRADO:
            message = "O período de teste terminou. Os XMLs já baixados continuam acessíveis, mas novos downloads ficam bloqueados até a compra da licença."
        elif status == STATUS_NAO_CADASTRADO:
            message = "Preencha nome, CPF/CNPJ, e-mail e telefone para iniciar o teste de 7 dias."
        elif status == STATUS_ATIVA:
            message = "Licença ativa nesta máquina. Novos downloads estão liberados."
        elif status == STATUS_PAGAMENTO_PENDENTE:
            message = "Pedido Pix gerado. Quando o pagamento for confirmado, a licença será liberada no servidor. Use Atualizar status apenas se quiser conferir na hora."
        elif status == STATUS_BLOQUEADA and licenca.mensagem_status:
            message = licenca.mensagem_status

        if licenca.ultimo_erro and licenca.ultimo_erro not in message:
            message = f"{message} Último erro de sincronização: {licenca.ultimo_erro}"

        return LicenseSnapshot(
            status=status,
            status_label=status_label,
            message=message,
            buyer_name=cadastro.nome or "",
            documento=cadastro.documento or "",
            email=cadastro.email or "",
            telefone=cadastro.telefone or "",
            machine_id=cadastro.machine_id or self.get_machine_id(),
            machine_name=cadastro.machine_name or self.get_machine_name(),
            trial_expires_at=licenca.trial_expira_em,
            trial_started_at=licenca.trial_iniciado_em,
            days_left=days_left,
            downloads_allowed=bool(licenca.downloads_liberados),
            backend_configured=backend_configured,
            last_sync_at=licenca.ultima_sincronizacao_em,
            server_time=licenca.ultimo_server_time,
            licenses_total=int(licenca.licencas_total or 0),
            licenses_in_use=int(licenca.licencas_em_uso or 0),
            pending_order_id=licenca.pedido_pendente_id or "",
            pix_copy_paste=licenca.pix_copia_cola or "",
            pix_qr_code_base64=licenca.pix_qr_code_base64 or "",
            pix_expires_at=licenca.pix_expira_em,
            offline_error=licenca.ultimo_erro or "",
        )

    def can_start_download(self) -> tuple[bool, str, LicenseSnapshot]:
        api_base_url, api_error = self._get_api_base_url()
        snapshot = self.sync_status(force=True) if api_base_url and not api_error else self.get_snapshot(force_sync=False)
        if snapshot.status == STATUS_NAO_CADASTRADO:
            return False, "Preencha o cadastro do comprador para iniciar o teste e liberar o download.", snapshot
        if snapshot.downloads_allowed:
            return True, snapshot.message, snapshot
        if snapshot.status == STATUS_TRIAL_EXPIRADO:
            return False, "O período de teste expirou. Os arquivos já baixados continuam disponíveis, mas novos downloads exigem licença ativa.", snapshot
        if snapshot.status == STATUS_PAGAMENTO_PENDENTE:
            return False, "Existe um pagamento pendente. Conclua o Pix; a licença será liberada no servidor assim que o pagamento for confirmado. Se quiser, use Atualizar status para conferir na hora.", snapshot
        if snapshot.status == STATUS_BLOQUEADA and snapshot.offline_error:
            return False, snapshot.offline_error, snapshot
        return False, snapshot.message or "Novos downloads estão bloqueados até a ativação da licença.", snapshot

    def decode_qr_code(self, base64_data: str) -> bytes:
        if not base64_data:
            return b""
        try:
            return base64.b64decode(base64_data)
        except Exception:
            return b""
