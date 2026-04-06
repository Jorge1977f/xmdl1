"""Persistência simples de estado de interface com QSettings."""
from __future__ import annotations

import json
from typing import Iterable

from PySide6.QtCore import QDate, QSettings, Qt

ORG_NAME = "JFL"
APP_NAME = "XMLDownloader"


def get_settings() -> QSettings:
    return QSettings(ORG_NAME, APP_NAME)


def save_qdate(settings: QSettings, key: str, value: QDate) -> None:
    settings.setValue(key, value.toString(Qt.ISODate))


def load_qdate(settings: QSettings, key: str, default: QDate) -> QDate:
    raw = settings.value(key)
    if not raw:
        return default
    if isinstance(raw, QDate):
        return raw
    parsed = QDate.fromString(str(raw), Qt.ISODate)
    return parsed if parsed.isValid() else default


def save_list(settings: QSettings, key: str, values: Iterable[int]) -> None:
    settings.setValue(key, json.dumps(list(values)))


def load_int_list(settings: QSettings, key: str) -> list[int]:
    raw = settings.value(key)
    if not raw:
        return []
    try:
        data = json.loads(str(raw))
    except Exception:
        return []
    result: list[int] = []
    for item in data:
        try:
            result.append(int(item))
        except Exception:
            continue
    return result
