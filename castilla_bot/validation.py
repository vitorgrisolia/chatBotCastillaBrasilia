"""Validação dos dados solicitados na pré-matrícula."""

from __future__ import annotations

import re


def normalize_cpf(value: str) -> str | None:
    """Retorna os 11 dígitos de um CPF válido, sem pontuação."""
    if not re.fullmatch(r"[0-9.\-\s]+", value):
        return None
    digits = re.sub(r"[^0-9]", "", value)
    if len(digits) != 11 or len(set(digits)) == 1:
        return None
    for size in (9, 10):
        total = sum(int(digit) * weight for digit, weight in zip(digits[:size], range(size + 1, 1, -1)))
        remainder = (total * 10) % 11
        expected = 0 if remainder == 10 else remainder
        if expected != int(digits[size]):
            return None
    return digits


_EMAIL_LOCAL = re.compile(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+")
_DOMAIN_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")


def normalize_email(value: str) -> str | None:
    """Valida a forma do endereço; não afirma que a caixa de e-mail existe."""
    address = value.strip()
    if len(address) > 254 or address.count("@") != 1:
        return None
    local, domain = address.rsplit("@", 1)
    if (
        not local
        or len(local) > 64
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
        or not _EMAIL_LOCAL.fullmatch(local)
    ):
        return None
    labels = domain.split(".")
    if len(labels) < 2 or any(not _DOMAIN_LABEL.fullmatch(label) for label in labels):
        return None
    if len(labels[-1]) < 2 or labels[-1].isdigit():
        return None
    return f"{local}@{domain.lower()}"


def normalize_whatsapp(value: str) -> str | None:
    """Aceita DDD brasileiro com 8/9 dígitos e devolve 55 + DDD + número."""
    raw = value.strip()
    if not re.fullmatch(r"\+?[0-9\s().-]+", raw):
        return None
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+") and not (len(digits) in (12, 13) and digits.startswith("55")):
        return None
    if len(digits) in (12, 13) and digits.startswith("55"):
        digits = digits[2:]
    if len(digits) not in (10, 11):
        return None
    if not 11 <= int(digits[:2]) <= 99 or int(digits[2:]) == 0:
        return None
    return "55" + digits
