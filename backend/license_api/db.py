from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import psycopg2
import psycopg2.extras

from .config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def calculate_total(quantity: int) -> float:
    base_limit = settings.discount_start_from - 1
    base_qty = min(quantity, base_limit)
    discounted_qty = max(0, quantity - base_limit)
    discounted_unit = round(settings.price_per_machine * (1 - settings.discount_rate), 2)
    total = (base_qty * settings.price_per_machine) + (discounted_qty * discounted_unit)
    return round(total, 2)


@contextmanager
def get_conn():
    conn = psycopg2.connect(settings.pg_dsn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_one(cur, query: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]:
    cur.execute(query, params)
    return cur.fetchone()


def get_or_create_client(cur, buyer: dict[str, Any]) -> dict[str, Any]:
    row = fetch_one(cur, "select * from public.clientes where cpf_cnpj = %s", (buyer["documento"],))
    if row:
        cur.execute(
            """
            update public.clientes
               set nome = %s,
                   email = %s,
                   telefone = %s,
                   updated_at = now()
             where id = %s
            """,
            (buyer["nome"], buyer["email"], buyer["telefone"], row["id"]),
        )
        row.update({"nome": buyer["nome"], "email": buyer["email"], "telefone": buyer["telefone"]})
        return row

    cur.execute(
        """
        insert into public.clientes (nome, cpf_cnpj, email, telefone)
        values (%s, %s, %s, %s)
        returning *
        """,
        (buyer["nome"], buyer["documento"], buyer["email"], buyer["telefone"]),
    )
    return cur.fetchone()


def get_or_create_trial(cur, client_id: str, installation: dict[str, Any]) -> dict[str, Any]:
    """Cria o trial preso à primeira máquina do cliente."""
    row = fetch_one(cur, "select * from public.trials where cliente_id = %s", (client_id,))
    now = utcnow()
    if row:
        status = row["status"]
        if status == "active" and row["expires_at"] <= now:
            status = "expired"

        same_machine = (row.get("machine_id") or "") == installation["machine_id"]
        if same_machine:
            cur.execute(
                """
                update public.trials
                   set machine_name = %s,
                       app_version = %s,
                       install_id = %s,
                       status = %s,
                       last_sync_at = now(),
                       updated_at = now()
                 where id = %s
                returning *
                """,
                (
                    installation["machine_name"],
                    installation.get("app_version") or "1.0.0",
                    installation.get("install_id"),
                    status,
                    row["id"],
                ),
            )
            return cur.fetchone()

        cur.execute(
            """
            update public.trials
               set status = %s,
                   updated_at = now()
             where id = %s
            returning *
            """,
            (status, row["id"]),
        )
        return cur.fetchone()

    expires_at = now + timedelta(days=settings.trial_days)
    cur.execute(
        """
        insert into public.trials (
            cliente_id, machine_id, machine_name, install_id, app_version, started_at, expires_at, status, last_sync_at
        )
        values (%s, %s, %s, %s, %s, %s, %s, 'active', now())
        returning *
        """,
        (
            client_id,
            installation["machine_id"],
            installation["machine_name"],
            installation.get("install_id"),
            installation.get("app_version") or "1.0.0",
            now,
            expires_at,
        ),
    )
    return cur.fetchone()



def is_trial_bound_to_current_machine(trial_row: dict[str, Any], installation: dict[str, Any]) -> bool:
    return (trial_row.get("machine_id") or "") == installation.get("machine_id")


def get_or_create_license(cur, client_id: str) -> dict[str, Any]:
    row = fetch_one(cur, "select * from public.licencas where cliente_id = %s", (client_id,))
    if row:
        return row
    cur.execute(
        """
        insert into public.licencas (cliente_id, total_comprado, total_em_uso, status)
        values (%s, 0, 0, 'inactive')
        returning *
        """,
        (client_id,),
    )
    return cur.fetchone()


def get_pending_order(cur, client_id: str) -> Optional[dict[str, Any]]:
    return fetch_one(
        cur,
        """
        select *
          from public.pedidos
         where cliente_id = %s
           and status = 'pending'
           and expires_at > now()
         order by created_at desc
         limit 1
        """,
        (client_id,),
    )


def get_order_by_id(cur, order_id: str) -> Optional[dict[str, Any]]:
    return fetch_one(cur, "select * from public.pedidos where id = %s", (order_id,))


def get_order_by_payment_id(cur, payment_id: str) -> Optional[dict[str, Any]]:
    return fetch_one(cur, "select * from public.pedidos where mercadopago_payment_id = %s", (payment_id,))


def recalc_license_totals(cur, license_row: dict[str, Any], client_id: str) -> dict[str, Any]:
    paid_row = fetch_one(
        cur,
        """
        select coalesce(sum(quantidade), 0) as total
          from public.pedidos
         where cliente_id = %s
           and status = 'paid'
        """,
        (client_id,),
    )
    active_row = fetch_one(
        cur,
        """
        select coalesce(count(*), 0) as total
          from public.ativacoes
         where licenca_id = %s
           and status = 'active'
        """,
        (license_row["id"],),
    )
    total_comprado = int((paid_row or {}).get("total") or 0)
    total_em_uso = int((active_row or {}).get("total") or 0)
    status = "active" if total_comprado > 0 else "inactive"
    cur.execute(
        """
        update public.licencas
           set total_comprado = %s,
               total_em_uso = %s,
               status = %s,
               updated_at = now()
         where id = %s
        returning *
        """,
        (total_comprado, total_em_uso, status, license_row["id"]),
    )
    return cur.fetchone()


def ensure_activation(cur, license_row: dict[str, Any], client_id: str, installation: dict[str, Any]) -> tuple[bool, int, int, Optional[dict[str, Any]]]:
    license_row = recalc_license_totals(cur, license_row, client_id)
    activation = fetch_one(
        cur,
        "select * from public.ativacoes where licenca_id = %s and machine_id = %s",
        (license_row["id"], installation["machine_id"]),
    )
    if activation and activation["status"] == "active":
        cur.execute(
            """
            update public.ativacoes
               set machine_name = %s,
                   app_version = %s,
                   install_id = %s,
                   last_ping_at = now(),
                   updated_at = now()
             where id = %s
         returning *
            """,
            (
                installation["machine_name"],
                installation.get("app_version") or "1.0.0",
                installation.get("install_id"),
                activation["id"],
            ),
        )
        activation = cur.fetchone()
        license_row = recalc_license_totals(cur, license_row, client_id)
        return True, int(license_row["total_comprado"]), int(license_row["total_em_uso"]), activation

    total_comprado = int(license_row["total_comprado"] or 0)
    total_em_uso = int(license_row["total_em_uso"] or 0)
    if total_comprado <= 0 or total_em_uso >= total_comprado:
        return False, total_comprado, total_em_uso, activation

    if activation:
        cur.execute(
            """
            update public.ativacoes
               set status = 'active',
                   machine_name = %s,
                   app_version = %s,
                   install_id = %s,
                   activated_at = coalesce(activated_at, now()),
                   last_ping_at = now(),
                   deactivated_at = null,
                   updated_at = now()
             where id = %s
            returning *
            """,
            (
                installation["machine_name"],
                installation.get("app_version") or "1.0.0",
                installation.get("install_id"),
                activation["id"],
            ),
        )
        activation = cur.fetchone()
    else:
        cur.execute(
            """
            insert into public.ativacoes (
                licenca_id, cliente_id, machine_id, machine_name, install_id, app_version, status, activated_at, last_ping_at
            )
            values (%s, %s, %s, %s, %s, %s, 'active', now(), now())
            returning *
            """,
            (
                license_row["id"],
                client_id,
                installation["machine_id"],
                installation["machine_name"],
                installation.get("install_id"),
                installation.get("app_version") or "1.0.0",
            ),
        )
        activation = cur.fetchone()

    updated_license = recalc_license_totals(cur, license_row, client_id)
    return True, int(updated_license["total_comprado"]), int(updated_license["total_em_uso"]), activation


def create_order(cur, client_id: str, quantity: int, total_amount: float, pix_copy_paste: str, qr_base64: str) -> dict[str, Any]:
    cur.execute(
        """
        update public.pedidos
           set status = 'cancelled',
               mercadopago_status = coalesce(mercadopago_status, 'cancelled'),
               updated_at = now()
         where cliente_id = %s
           and status = 'pending'
        """,
        (client_id,),
    )
    cur.execute(
        """
        insert into public.pedidos (
            cliente_id, quantidade, total_amount, status, pix_copy_paste, pix_qr_code, expires_at
        )
        values (%s, %s, %s, 'pending', %s, %s, now() + (%s || ' minutes')::interval)
        returning *
        """,
        (client_id, quantity, total_amount, pix_copy_paste, qr_base64, str(settings.pix_expiration_minutes)),
    )
    return cur.fetchone()


def update_order_after_provider(
    cur,
    *,
    order_id: str,
    payment_id: Optional[str],
    external_reference: Optional[str],
    pix_copy_paste: str,
    qr_base64: str,
    expires_at: Optional[datetime],
    provider_status: Optional[str],
    provider_status_detail: Optional[str],
    provider_payload: Optional[dict[str, Any]],
) -> dict[str, Any]:
    cur.execute(
        """
        update public.pedidos
           set mercadopago_payment_id = %s,
               external_reference = %s,
               pix_copy_paste = %s,
               pix_qr_code = %s,
               expires_at = coalesce(%s, expires_at),
               mercadopago_status = %s,
               mercadopago_status_detail = %s,
               mercadopago_payload = %s,
               updated_at = now()
         where id = %s
        returning *
        """,
        (
            payment_id,
            external_reference,
            pix_copy_paste,
            qr_base64,
            expires_at,
            provider_status,
            provider_status_detail,
            psycopg2.extras.Json(provider_payload) if provider_payload is not None else None,
            order_id,
        ),
    )
    return cur.fetchone()


def cancel_order(cur, order_id: str, reason: str = 'cancelled') -> dict[str, Any]:
    cur.execute(
        """
        update public.pedidos
           set status = 'cancelled',
               mercadopago_status = %s,
               updated_at = now()
         where id = %s
        returning *
        """,
        (reason, order_id),
    )
    return cur.fetchone()


def apply_payment_result(cur, order_row: dict[str, Any], payment_data: dict[str, Any]) -> dict[str, Any]:
    payment_status = (payment_data.get('status') or '').lower()
    status_detail = payment_data.get('status_detail') or ''
    paid_at = payment_data.get('date_approved') or payment_data.get('date_last_updated')
    raw_expires_at = payment_data.get('date_of_expiration')
    expires_at = None
    if raw_expires_at:
        try:
            expires_at = datetime.fromisoformat(str(raw_expires_at).replace('Z', '+00:00'))
        except Exception:
            expires_at = None

    transaction_data = ((payment_data.get('point_of_interaction') or {}).get('transaction_data') or {})
    pix_copy = transaction_data.get('qr_code') or order_row.get('pix_copy_paste') or ''
    qr_base64 = transaction_data.get('qr_code_base64') or order_row.get('pix_qr_code') or ''

    internal_status = 'pending'
    if payment_status == 'approved':
        internal_status = 'paid'
    elif payment_status in {'cancelled', 'rejected', 'refunded', 'charged_back'}:
        internal_status = 'cancelled'

    cur.execute(
        """
        update public.pedidos
           set status = %s,
               pix_copy_paste = %s,
               pix_qr_code = %s,
               expires_at = coalesce(%s, expires_at),
               mercadopago_status = %s,
               mercadopago_status_detail = %s,
               mercadopago_payload = %s,
               paid_at = case when %s = 'paid' then coalesce(paid_at, now()) else paid_at end,
               webhook_last_received_at = now(),
               updated_at = now()
         where id = %s
        returning *
        """,
        (
            internal_status,
            pix_copy,
            qr_base64,
            expires_at,
            payment_status or None,
            status_detail or None,
            psycopg2.extras.Json(payment_data),
            internal_status,
            order_row['id'],
        ),
    )
    return cur.fetchone()
