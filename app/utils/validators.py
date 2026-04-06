"""
Utilitários para validação e formatação de dados.
"""
from __future__ import annotations

import re
from datetime import datetime


class Validators:
    """Validadores e formatadores usados na interface."""

    @staticmethod
    def only_digits(value: str) -> str:
        return re.sub(r"\D", "", value or "")

    @staticmethod
    def validate_cpf(cpf: str) -> bool:
        cpf = Validators.only_digits(cpf)
        if len(cpf) != 11 or cpf == cpf[0] * 11:
            return False

        total = sum(int(cpf[i]) * (10 - i) for i in range(9))
        resto = (total * 10) % 11
        dig1 = 0 if resto == 10 else resto
        if dig1 != int(cpf[9]):
            return False

        total = sum(int(cpf[i]) * (11 - i) for i in range(10))
        resto = (total * 10) % 11
        dig2 = 0 if resto == 10 else resto
        return dig2 == int(cpf[10])

    @staticmethod
    def validate_cnpj(cnpj: str) -> bool:
        cnpj = Validators.only_digits(cnpj)
        if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
            return False

        pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        pesos2 = [6] + pesos1

        total = sum(int(cnpj[i]) * pesos1[i] for i in range(12))
        resto = total % 11
        dig1 = 0 if resto < 2 else 11 - resto
        if dig1 != int(cnpj[12]):
            return False

        total = sum(int(cnpj[i]) * pesos2[i] for i in range(13))
        resto = total % 11
        dig2 = 0 if resto < 2 else 11 - resto
        return dig2 == int(cnpj[13])

    @staticmethod
    def validate_cpf_or_cnpj(value: str) -> bool:
        digits = Validators.only_digits(value)
        if len(digits) == 11:
            return Validators.validate_cpf(digits)
        if len(digits) == 14:
            return Validators.validate_cnpj(digits)
        return False

    @staticmethod
    def validate_nfe_key(chave: str) -> bool:
        chave = Validators.only_digits(chave)
        if len(chave) != 44:
            return False
        sequence = "2987654321" * 4 + "29"
        sum_value = sum(int(chave[i]) * int(sequence[i]) for i in range(43))
        digit = 11 - (sum_value % 11)
        digit = 0 if digit > 9 else digit
        return int(chave[43]) == digit

    @staticmethod
    def validate_date_range(start_date: datetime, end_date: datetime) -> bool:
        return start_date <= end_date

    @staticmethod
    def validate_email(email: str) -> bool:
        email = (email or "").strip()
        if " " in email or "@" not in email:
            return False
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return re.match(pattern, email) is not None

    @staticmethod
    def format_phone(phone: str) -> str:
        digits = Validators.only_digits(phone)[:11]
        if not digits:
            return ""
        if len(digits) <= 2:
            return f"({digits}"
        if len(digits) <= 6:
            return f"({digits[:2]}) {digits[2:]}"
        if len(digits) <= 10:
            return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:11]}"

    @staticmethod
    def validate_phone(phone: str) -> bool:
        digits = Validators.only_digits(phone)
        return len(digits) in {10, 11}

    @staticmethod
    def validate_certificate_path(path: str) -> bool:
        from pathlib import Path
        cert_path = Path(path)
        return cert_path.exists() and cert_path.suffix.lower() in [".pfx", ".p12"]

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        filename = re.sub(r"\s+", " ", filename)
        return filename.strip()
