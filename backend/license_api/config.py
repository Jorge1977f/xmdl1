from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: str = 'false') -> bool:
    return os.getenv(name, default).strip().lower() == 'true'


@dataclass(frozen=True)
class Settings:
    api_base_url: str = os.getenv('LICENSE_API_BASE_URL', '').strip().rstrip('/')
    signing_secret: str = os.getenv('LICENSE_SIGNING_SECRET', '').strip() or 'troque-este-segredo-em-producao'
    trial_days: int = int(os.getenv('LICENSE_TRIAL_DAYS', '7'))
    price_per_machine: float = float(os.getenv('LICENSE_PRICE_PER_MACHINE', '49.90'))
    discount_start_from: int = int(os.getenv('LICENSE_DISCOUNT_START_FROM', '6'))
    discount_rate: float = float(os.getenv('LICENSE_DISCOUNT_RATE', '0.10'))
    pix_expiration_minutes: int = int(os.getenv('LICENSE_PIX_EXPIRATION_MINUTES', '60'))
    pix_mode: str = os.getenv('LICENSE_PIX_MODE', 'simulated').strip().lower() or 'simulated'
    allow_test_payment: bool = _env_bool('LICENSE_ALLOW_TEST_PAYMENT', 'false')
    mercadopago_access_token: str = os.getenv('LICENSE_MP_ACCESS_TOKEN', '').strip()
    mercadopago_webhook_secret: str = os.getenv('LICENSE_MP_WEBHOOK_SECRET', '').strip()
    mercadopago_notification_url: str = os.getenv('LICENSE_MP_WEBHOOK_URL', '').strip()
    mercadopago_timeout_seconds: int = int(os.getenv('LICENSE_MP_TIMEOUT_SECONDS', '30'))
    project_ref: str = os.getenv('LICENSE_SUPABASE_PROJECT_REF', '').strip()
    pg_password: str = os.getenv('LICENSE_PG_PASSWORD', '').strip()
    pg_user: str = os.getenv('LICENSE_PG_USER', 'postgres').strip() or 'postgres'
    pg_host: str = os.getenv('LICENSE_PG_HOST', '').strip()
    pg_port: int = int(os.getenv('LICENSE_PG_PORT', '5432'))
    pg_database: str = os.getenv('LICENSE_PG_DATABASE', 'postgres').strip() or 'postgres'
    pg_dsn: str = field(default='')

    def __post_init__(self) -> None:
        explicit_dsn = os.getenv('LICENSE_PG_DSN', '').strip()
        dsn = explicit_dsn
        if not dsn:
            host = self.pg_host or (f"db.{self.project_ref}.supabase.co" if self.project_ref else '')
            if host and self.pg_password:
                password = quote_plus(self.pg_password)
                dsn = f"postgresql://{self.pg_user}:{password}@{host}:{self.pg_port}/{self.pg_database}?sslmode=require"
        object.__setattr__(self, 'pg_dsn', dsn)

    @property
    def pg_ready(self) -> bool:
        return bool(self.pg_dsn)

    @property
    def mercadopago_ready(self) -> bool:
        if self.pix_mode != 'mercadopago':
            return False
        webhook_url = self.effective_mercadopago_webhook_url
        return bool(self.mercadopago_access_token and webhook_url)

    @property
    def effective_mercadopago_webhook_url(self) -> str:
        explicit = self.mercadopago_notification_url.strip().rstrip('/')
        if explicit:
            return explicit
        if self.api_base_url:
            return f"{self.api_base_url}/api/payments/mercadopago/webhook"
        return ''


settings = Settings()
