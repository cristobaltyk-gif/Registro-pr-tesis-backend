# modules/rut_utils.py
"""
Validación de RUT chileno — canónica.
Usado por todos los routers del Registro Nacional de Prótesis.
"""

import re


def normalize_rut(rut: str) -> str:
    """Normaliza RUT: quita puntos/espacios, mayúsculas, añade guion si falta."""
    if not rut:
        return ""
    rut = rut.strip().upper().replace(".", "").replace(" ", "")
    if "-" not in rut and len(rut) > 1:
        rut = f"{rut[:-1]}-{rut[-1]}"
    return rut


def is_valid_rut_format(rut: str) -> bool:
    """Valida solo formato (sin calcular DV)."""
    if not rut:
        return False
    return bool(re.match(r"^\d{7,8}-[\dK]$", rut))


def is_valid_rut(rut: str) -> bool:
    """
    Valida RUT chileno completo: formato + dígito verificador (módulo 11).
    Acepta '12345678-9' o '12345678-K'.
    """
    if not rut:
        return False

    clean = normalize_rut(rut)

    if not is_valid_rut_format(clean):
        return False

    body, dv = clean.split("-")
    total = 0
    multiplier = 2

    for digit in reversed(body):
        total += int(digit) * multiplier
        multiplier = 2 if multiplier == 7 else multiplier + 1

    mod = 11 - (total % 11)

    if mod == 11:
        expected_dv = "0"
    elif mod == 10:
        expected_dv = "K"
    else:
        expected_dv = str(mod)

    return dv == expected_dv
