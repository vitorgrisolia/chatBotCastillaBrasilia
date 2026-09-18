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
