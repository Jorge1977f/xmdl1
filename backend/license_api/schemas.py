from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def only_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


class BuyerIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    nome: str = Field(min_length=3, max_length=255)
    documento: str = Field(min_length=11, max_length=20)
    email: EmailStr
    telefone: str = Field(min_length=10, max_length=20)

    @field_validator("documento")
    @classmethod
    def normalize_document(cls, value: str) -> str:
        digits = only_digits(value)
        if len(digits) not in {11, 14}:
            raise ValueError("CPF/CNPJ inválido")
        return digits

    @field_validator("telefone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        digits = only_digits(value)
        if len(digits) not in {10, 11}:
            raise ValueError("Telefone inválido")
        return digits


class InstallationIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    machine_id: str = Field(min_length=16, max_length=128)
    machine_name: str = Field(min_length=1, max_length=255)
    install_id: str = Field(min_length=8, max_length=64)
    app_version: Optional[str] = Field(default="1.0.0", max_length=32)
    platform: Optional[str] = Field(default="", max_length=255)


class SyncRequest(BaseModel):
    buyer: BuyerIn
    installation: InstallationIn
    token: Optional[str] = None


class OrderPayload(BaseModel):
    quantity: int = Field(ge=1, le=999)
    expected_total: float = Field(gt=0)


class OrderRequest(BaseModel):
    buyer: BuyerIn
    installation: InstallationIn
    order: OrderPayload
