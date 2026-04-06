from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Optional

from .config import settings


def _b64encode(payload: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")


def sign_installation_token(payload: dict[str, Any]) -> str:
    body = dict(payload)
    body.setdefault("issued_at", datetime.now(timezone.utc).isoformat())
    encoded = _b64encode(body)
    signature = hmac.new(settings.signing_secret.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def verify_installation_token(token: str) -> Optional[dict[str, Any]]:
    try:
        encoded, signature = token.split('.', 1)
    except ValueError:
        return None
    expected = hmac.new(settings.signing_secret.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        raw = base64.urlsafe_b64decode(encoded.encode('ascii'))
        payload = json.loads(raw.decode('utf-8'))
        if isinstance(payload, dict):
            return payload
    except Exception:
        return None
    return None


def validate_mercadopago_signature(*, data_id: str, x_request_id: str, x_signature: str, secret: str) -> bool:
    if not secret:
        return True
    if not data_id or not x_request_id or not x_signature:
        return False

    parts: dict[str, str] = {}
    for item in x_signature.split(','):
        item = item.strip()
        if '=' not in item:
            continue
        key, value = item.split('=', 1)
        parts[key.strip().lower()] = value.strip()

    ts = parts.get('ts')
    received_v1 = parts.get('v1')
    if not ts or not received_v1:
        return False

    manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"
    expected_v1 = hmac.new(secret.encode('utf-8'), manifest.encode('utf-8'), hashlib.sha256).hexdigest()
    return hmac.compare_digest(received_v1, expected_v1)
