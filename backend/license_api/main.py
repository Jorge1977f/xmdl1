from __future__ import annotations

import base64
import io
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import psycopg2.extras
import qrcode
import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .config import settings
from .db import (
    apply_payment_result,
    calculate_total,
    cancel_order,
    create_order,
    ensure_activation,
    fetch_one,
    get_conn,
    get_or_create_client,
    get_or_create_license,
    get_or_create_trial,
    get_order_by_id,
    get_order_by_payment_id,
    get_pending_order,
    is_trial_bound_to_current_machine,
    recalc_license_totals,
    update_order_after_provider,
    utcnow,
)
from .schemas import OrderRequest, SyncRequest
from .security import sign_installation_token, validate_mercadopago_signature, verify_installation_token

app = FastAPI(title='XMDL License API', version='1.1.0')


def _to_iso(value):
    if not value:
        return None
    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _from_iso(value: Optional[str]):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        return None


def _qr_base64(payload: str) -> str:
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    image = qr.make_image(fill_color='black', back_color='white')
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode('ascii')


def _build_payment_block(order_row):
    if not order_row:
        return {
            'order_id': '',
            'pix_copy_paste': '',
            'pix_qr_code_base64': '',
            'expires_at': None,
        }
    return {
        'order_id': str(order_row['id']),
        'pix_copy_paste': order_row.get('pix_copy_paste') or '',
        'pix_qr_code_base64': order_row.get('pix_qr_code') or '',
        'expires_at': _to_iso(order_row.get('expires_at')),
    }


def _document_type(documento: str) -> str:
    digits = ''.join(ch for ch in str(documento or '') if ch.isdigit())
    return 'CNPJ' if len(digits) == 14 else 'CPF'


def _split_name(nome: str) -> tuple[str, str]:
    clean = (nome or '').strip()
    if not clean:
        return 'Cliente', 'XMDL'
    parts = clean.split()
    if len(parts) == 1:
        return parts[0], 'XMDL'
    return parts[0], ' '.join(parts[1:])


def _mercadopago_headers(*, with_idempotency: bool = False) -> dict[str, str]:
    headers = {
        'Authorization': f'Bearer {settings.mercadopago_access_token}',
        'Content-Type': 'application/json',
    }
    if with_idempotency:
        headers['X-Idempotency-Key'] = uuid.uuid4().hex
    return headers


def _ensure_mercadopago_ready() -> None:
    if settings.pix_mode != 'mercadopago':
        raise HTTPException(status_code=400, detail='O backend não está em modo Mercado Pago.')
    if not settings.mercadopago_access_token:
        raise HTTPException(status_code=500, detail='LICENSE_MP_ACCESS_TOKEN não configurado no Render.')
    if not settings.effective_mercadopago_webhook_url:
        raise HTTPException(status_code=500, detail='LICENSE_MP_WEBHOOK_URL ou LICENSE_API_BASE_URL não configurado para o webhook do Mercado Pago.')


def _mercadopago_create_pix_payment(*, buyer: dict[str, Any], order_row: dict[str, Any]) -> dict[str, Any]:
    _ensure_mercadopago_ready()
    first_name, last_name = _split_name(buyer['nome'])
    expires_at = utcnow() + timedelta(minutes=settings.pix_expiration_minutes)
    payload = {
        'transaction_amount': float(order_row['total_amount']),
        'description': f"Licença XMDL - {order_row['quantidade']} máquina(s)",
        'payment_method_id': 'pix',
        'date_of_expiration': expires_at.isoformat(),
        'notification_url': settings.effective_mercadopago_webhook_url,
        'external_reference': str(order_row['id']),
        'payer': {
            'email': buyer['email'],
            'first_name': first_name,
            'last_name': last_name,
            'identification': {
                'type': _document_type(buyer['documento']),
                'number': buyer['documento'],
            },
        },
    }
    response = requests.post(
        'https://api.mercadopago.com/v1/payments',
        json=payload,
        headers=_mercadopago_headers(with_idempotency=True),
        timeout=settings.mercadopago_timeout_seconds,
    )
    if response.status_code >= 400:
        detail = response.text[:1000]
        raise HTTPException(status_code=502, detail=f'Erro ao criar pagamento Pix no Mercado Pago: {detail}')
    return response.json() or {}


def _mercadopago_get_payment(payment_id: str) -> dict[str, Any]:
    _ensure_mercadopago_ready()
    response = requests.get(
        f'https://api.mercadopago.com/v1/payments/{payment_id}',
        headers=_mercadopago_headers(),
        timeout=settings.mercadopago_timeout_seconds,
    )
    if response.status_code >= 400:
        detail = response.text[:1000]
        raise HTTPException(status_code=502, detail=f'Erro ao consultar pagamento {payment_id} no Mercado Pago: {detail}')
    return response.json() or {}


def _sync_pending_order_from_provider(cur, pending_order: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not pending_order or settings.pix_mode != 'mercadopago':
        return pending_order
    payment_id = pending_order.get('mercadopago_payment_id')
    if not payment_id:
        return pending_order
    payment_data = _mercadopago_get_payment(str(payment_id))
    updated_order = apply_payment_result(cur, pending_order, payment_data)
    return updated_order


def _resolve_payment_order(cur, payment_data: dict[str, Any]) -> Optional[dict[str, Any]]:
    payment_id = str(payment_data.get('id') or '')
    external_reference = str(payment_data.get('external_reference') or '')
    order_row = get_order_by_payment_id(cur, payment_id) if payment_id else None
    if not order_row and external_reference:
        order_row = get_order_by_id(cur, external_reference)
    return order_row


@app.get('/')
def root():
    return {
        'ok': True,
        'name': 'XMDL License API',
        'docs': '/docs',
        'health': '/health',
        'database_ready': settings.pg_ready,
    }


@app.get('/health')
def health():
    return {
        'ok': True,
        'mode': settings.pix_mode,
        'database_ready': settings.pg_ready,
        'mercadopago_ready': settings.mercadopago_ready,
        'webhook_url': settings.effective_mercadopago_webhook_url,
    }


@app.post('/api/licensing/installations/sync')
def sync_installation(payload: SyncRequest):
    if not settings.pg_ready:
        raise HTTPException(status_code=500, detail='Banco não configurado. Preencha LICENSE_PG_PASSWORD no arquivo backend/.env.')

    buyer = payload.buyer.model_dump()
    installation = payload.installation.model_dump()
    token = (payload.token or '').strip()
    if token:
        token_payload = verify_installation_token(token)
        if not token_payload:
            raise HTTPException(status_code=401, detail='Token de instalação inválido.')
        if str(token_payload.get('documento') or '') != buyer['documento']:
            raise HTTPException(status_code=401, detail='Token de instalação não pertence a este CPF/CNPJ.')
        if str(token_payload.get('machine_id') or '') != installation['machine_id']:
            raise HTTPException(status_code=401, detail='Token de instalação não pertence a esta máquina.')

    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        client_row = get_or_create_client(cur, buyer)
        trial_row = get_or_create_trial(cur, str(client_row['id']), installation)
        license_row = get_or_create_license(cur, str(client_row['id']))
        license_row = recalc_license_totals(cur, license_row, str(client_row['id']))
        pending_order = get_pending_order(cur, str(client_row['id']))
        if pending_order and settings.pix_mode == 'mercadopago' and pending_order.get('mercadopago_payment_id'):
            pending_order = _sync_pending_order_from_provider(cur, pending_order)
            license_row = recalc_license_totals(cur, license_row, str(client_row['id']))
        now = utcnow()

        downloads_allowed = False
        status = 'TRIAL'
        message = 'Você tem 7 dias para testar.'
        licenses_total = int(license_row['total_comprado'] or 0)
        licenses_in_use = int(license_row['total_em_uso'] or 0)
        installation_id = str(trial_row['id'])

        if licenses_total > 0:
            activated, licenses_total, licenses_in_use, activation = ensure_activation(cur, license_row, str(client_row['id']), installation)
            if activated:
                status = 'ATIVA'
                downloads_allowed = True
                message = 'Licença ativa. Novos downloads estão liberados.'
                if trial_row['status'] != 'converted':
                    cur.execute("update public.trials set status = 'converted', updated_at = now() where id = %s", (trial_row['id'],))
                installation_id = str((activation or {}).get('id') or trial_row['id'])
            else:
                status = 'BLOQUEADA'
                downloads_allowed = False
                message = 'Todas as licenças compradas já estão em uso em outras máquinas.'
        else:
            trial_expires = trial_row['expires_at']
            trial_same_machine = is_trial_bound_to_current_machine(trial_row, installation)
            if not trial_same_machine:
                status = 'BLOQUEADA'
                downloads_allowed = False
                message = 'Este teste já está vinculado a outra máquina. Para usar em outro computador, compre uma licença ou libere a máquina anterior no painel administrativo.'
                if pending_order:
                    status = 'PAGAMENTO_PENDENTE'
                    message = 'Existe um Pix pendente para este cliente. Quando o pagamento for confirmado, a licença será liberada conforme a quantidade de máquinas compradas.'
            elif trial_expires > now:
                status = 'TRIAL'
                downloads_allowed = True
                message = 'Você tem 7 dias para testar nesta máquina.'
                if pending_order:
                    status = 'PAGAMENTO_PENDENTE'
                    downloads_allowed = False
                    message = 'Existe um Pix pendente. Quando o pagamento for confirmado, a licença será liberada no servidor. Use Atualizar status no app apenas se quiser conferir na hora.'
            else:
                status = 'TRIAL_EXPIRADO'
                downloads_allowed = False
                message = 'O período de teste terminou. Os XMLs já baixados continuam acessíveis, mas novos downloads ficam bloqueados até a compra da licença.'
                if pending_order:
                    status = 'PAGAMENTO_PENDENTE'
                    message = 'Existe um Pix pendente. Quando o pagamento for confirmado, a licença será liberada no servidor. Use Atualizar status no app apenas se quiser conferir na hora.'

        token = sign_installation_token(
            {
                'client_id': str(client_row['id']),
                'installation_id': installation_id,
                'machine_id': installation['machine_id'],
                'documento': buyer['documento'],
            }
        )
        return {
            'client_id': str(client_row['id']),
            'installation_id': installation_id,
            'token': token,
            'server_time': _to_iso(now),
            'buyer': {
                'nome': client_row['nome'],
                'documento': client_row['cpf_cnpj'],
                'email': client_row['email'],
                'telefone': client_row['telefone'],
            },
            'trial': {
                'started_at': _to_iso(trial_row['started_at']),
                'expires_at': _to_iso(trial_row['expires_at']),
            },
            'license': {
                'status': status,
                'message': message,
                'downloads_allowed': downloads_allowed,
                'licenses_total': licenses_total,
                'licenses_in_use': licenses_in_use,
            },
            'payment': _build_payment_block(pending_order),
        }


@app.post('/api/licensing/orders')
def create_license_order(payload: OrderRequest):
    if not settings.pg_ready:
        raise HTTPException(status_code=500, detail='Banco não configurado. Preencha LICENSE_PG_PASSWORD no arquivo backend/.env.')

    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        buyer = payload.buyer.model_dump()
        client_row = get_or_create_client(cur, buyer)
        total = calculate_total(payload.order.quantity)
        if round(total, 2) != round(payload.order.expected_total, 2):
            raise HTTPException(status_code=400, detail=f'Total esperado divergente. Backend calculou R$ {total:.2f}.')

        if settings.pix_mode == 'mercadopago':
            order_row = create_order(cur, str(client_row['id']), payload.order.quantity, total, '', '')
            try:
                payment_data = _mercadopago_create_pix_payment(buyer=buyer, order_row=order_row)
            except Exception:
                cancel_order(cur, str(order_row['id']), reason='provider_error')
                raise
            transaction_data = ((payment_data.get('point_of_interaction') or {}).get('transaction_data') or {})
            order_row = update_order_after_provider(
                cur,
                order_id=str(order_row['id']),
                payment_id=str(payment_data.get('id') or ''),
                external_reference=str(payment_data.get('external_reference') or order_row['id']),
                pix_copy_paste=transaction_data.get('qr_code') or '',
                qr_base64=transaction_data.get('qr_code_base64') or '',
                expires_at=_from_iso(payment_data.get('date_of_expiration')),
                provider_status=payment_data.get('status'),
                provider_status_detail=payment_data.get('status_detail'),
                provider_payload=payment_data,
            )
            return {
                'payment': {
                    'order_id': str(order_row['id']),
                    'pix_copy_paste': order_row.get('pix_copy_paste') or '',
                    'pix_qr_code_base64': order_row.get('pix_qr_code') or '',
                    'expires_at': _to_iso(order_row.get('expires_at')),
                    'message': 'Pedido Pix gerado pelo Mercado Pago. A confirmação será automática via webhook; no app, o botão Atualizar status continua útil como conferência manual.',
                }
            }

        pix_copy = f"SIMULADO|XMDL|{buyer['documento']}|QTD={payload.order.quantity}|TOTAL={total:.2f}"
        qr_base64 = _qr_base64(pix_copy)
        order_row = create_order(cur, str(client_row['id']), payload.order.quantity, total, pix_copy, qr_base64)

        return {
            'payment': {
                'order_id': str(order_row['id']),
                'pix_copy_paste': pix_copy,
                'pix_qr_code_base64': qr_base64,
                'expires_at': _to_iso(order_row['expires_at']),
                'message': 'Pedido Pix gerado em modo simulado. Você pode testar a interface e, se quiser, confirmar manualmente o pagamento no endpoint de teste.',
            }
        }


@app.post('/api/payments/mercadopago/webhook')
async def mercadopago_webhook(request: Request):
    if settings.pix_mode != 'mercadopago':
        return JSONResponse({'ok': True, 'ignored': True, 'reason': 'pix_mode_not_mercadopago'})
    if not settings.pg_ready:
        raise HTTPException(status_code=500, detail='Banco não configurado.')

    raw_body = await request.body()
    try:
        body = await request.json()
    except Exception:
        body = {}

    notif_type = str(request.query_params.get('type') or body.get('type') or body.get('topic') or '')
    action = str(body.get('action') or '')
    data = body.get('data') if isinstance(body, dict) else {}
    payment_id = str(request.query_params.get('data.id') or request.query_params.get('id') or (data or {}).get('id') or body.get('id') or '')

    if notif_type not in {'payment', 'payments'} and not action.startswith('payment.'):
        return JSONResponse({'ok': True, 'ignored': True, 'reason': 'topic_not_supported'})
    if not payment_id:
        return JSONResponse({'ok': True, 'ignored': True, 'reason': 'payment_id_missing'})

    if settings.mercadopago_webhook_secret:
        is_valid = validate_mercadopago_signature(
            data_id=payment_id,
            x_request_id=request.headers.get('x-request-id', ''),
            x_signature=request.headers.get('x-signature', ''),
            secret=settings.mercadopago_webhook_secret,
        )
        if not is_valid:
            raise HTTPException(status_code=401, detail='Assinatura do webhook do Mercado Pago inválida.')

    payment_data = _mercadopago_get_payment(payment_id)
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        order_row = _resolve_payment_order(cur, payment_data)
        if not order_row:
            return JSONResponse({'ok': True, 'ignored': True, 'reason': 'order_not_found'})
        updated_order = apply_payment_result(cur, order_row, payment_data)
        return JSONResponse({'ok': True, 'order_id': str(updated_order['id']), 'status': updated_order['status']})


@app.post('/api/licensing/orders/{order_id}/simulate-payment')
def simulate_payment(order_id: str):
    if not settings.allow_test_payment:
        raise HTTPException(status_code=403, detail='Simulação de pagamento desativada.')
    if not settings.pg_ready:
        raise HTTPException(status_code=500, detail='Banco não configurado. Preencha LICENSE_PG_PASSWORD no arquivo backend/.env.')

    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        row = fetch_one(cur, 'select * from public.pedidos where id = %s', (order_id,))
        if not row:
            raise HTTPException(status_code=404, detail='Pedido não encontrado.')
        cur.execute('select public.fn_marcar_pedido_como_pago(%s, %s, %s)', (order_id, f'SIM-{order_id[:8]}', f'TX-{order_id[:8]}'))
        return JSONResponse({'ok': True, 'message': 'Pagamento simulado com sucesso. A licença já foi liberada no servidor. Atualize o status no app quando quiser conferir.'})
