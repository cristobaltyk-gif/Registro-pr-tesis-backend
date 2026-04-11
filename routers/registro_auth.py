# routers/registro_auth.py
#
# Auth para registro de prótesis.
# Flujo:
#   1. Admin genera código para un RUT  → POST /api/registro/auth/generar
#   2. Paciente valida RUT + código     → POST /api/registro/auth/validar
#   3. Recibe token JWT de sesión
#   4. Usa token en headers para el resto de endpoints
#
# Tokens de acceso: un solo uso + expiran en 365 días

from __future__ import annotations

import json
import os
import re
import secrets
import string
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/registro/auth", tags=["registro-auth"])

# ============================================================
# CONFIG
# ============================================================
DATA_PATH   = Path(os.getenv("DATA_PATH", "/data"))
CODES_FILE  = DATA_PATH / "registro_protesis" / "access_codes.json"
JWT_SECRET  = os.getenv("REGISTRO_JWT_SECRET", "cambiar_en_produccion_registro_ica")
JWT_ALGO    = "HS256"
JWT_EXPIRE_DAYS = 365
CODE_LENGTH = 8   # ej: "A3X9K2M7"

ADMIN_KEY   = os.getenv("REGISTRO_ADMIN_KEY", "admin_registro_ica")  # para generar códigos


# ============================================================
# HELPERS
# ============================================================
def _normalize_rut(rut: str) -> str:
    rut = rut.strip().upper().replace(".", "").replace(" ", "")
    if "-" not in rut and len(rut) > 1:
        rut = f"{rut[:-1]}-{rut[-1]}"
    return rut


def _valid_rut(rut: str) -> bool:
    return bool(re.match(r"^\d{7,8}-[\dK]$", rut))


def _load_codes() -> dict:
    if not CODES_FILE.exists():
        return {}
    return json.loads(CODES_FILE.read_text(encoding="utf-8"))


def _save_codes(data: dict) -> None:
    CODES_FILE.parent.mkdir(parents=True, exist_ok=True)
    CODES_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def _generate_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(CODE_LENGTH))


def _create_token(rut: str) -> str:
    payload = {
        "sub": rut,
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def _decode_token(token: str) -> str:
    """Retorna rut si el token es válido. Lanza HTTPException si no."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sesión expirada")
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido")


# ============================================================
# DEPENDENCIA REUTILIZABLE
# ============================================================
def get_rut_from_token(
    authorization: str | None = Header(default=None)
) -> str:
    """
    Extrae y valida el RUT desde el header Authorization: Bearer <token>.
    Usar como dependencia en otros routers.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token requerido")
    token = authorization.removeprefix("Bearer ").strip()
    return _decode_token(token)


# ============================================================
# SCHEMAS
# ============================================================
class GenerarCodigoRequest(BaseModel):
    rut:       str
    admin_key: str
    nota:      str = ""   # opcional — ej: "enviado por Fonasa batch abril 2026"


class ValidarCodigoRequest(BaseModel):
    rut:    str
    codigo: str


# ============================================================
# ENDPOINTS
# ============================================================

@router.post("/generar")
def generar_codigo(payload: GenerarCodigoRequest):
    """
    Admin genera un código de acceso para un RUT.
    Puede llamarse en batch para envíos masivos de Fonasa.
    """
    if payload.admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Clave de admin inválida")

    rut = _normalize_rut(payload.rut)
    if not _valid_rut(rut):
        raise HTTPException(status_code=400, detail="RUT inválido")

    codes = _load_codes()

    # Si ya tiene código activo y no usado → devolver el mismo
    existing = codes.get(rut)
    if existing and not existing.get("used"):
        return {
            "ok":     True,
            "rut":    rut,
            "codigo": existing["codigo"],
            "nuevo":  False,
        }

    code = _generate_code()
    codes[rut] = {
        "codigo":     code,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "used":       False,
        "used_at":    None,
        "nota":       payload.nota,
    }
    _save_codes(codes)

    return {
        "ok":     True,
        "rut":    rut,
        "codigo": code,
        "nuevo":  True,
    }


@router.post("/validar")
def validar_codigo(payload: ValidarCodigoRequest):
    """
    Paciente valida RUT + código.
    Si es correcto → devuelve token JWT de sesión.
    El código queda marcado como usado pero el token dura 365 días
    (paciente puede volver a completar escalas sin nuevo código).
    """
    rut = _normalize_rut(payload.rut)
    if not _valid_rut(rut):
        raise HTTPException(status_code=400, detail="RUT inválido")

    codes = _load_codes()
    entry = codes.get(rut)

    if not entry:
        raise HTTPException(status_code=404, detail="RUT no registrado. Contacte a su centro médico.")

    if entry["codigo"].upper() != payload.codigo.strip().upper():
        raise HTTPException(status_code=401, detail="Código incorrecto")

    # Marcar como usado si es primera vez
    if not entry.get("used"):
        entry["used"]    = True
        entry["used_at"] = datetime.now(timezone.utc).isoformat()
        codes[rut]       = entry
        _save_codes(codes)

    token = _create_token(rut)

    return {
        "ok":    True,
        "rut":   rut,
        "token": token,
    }


@router.get("/verificar")
def verificar_token(
    authorization: str | None = Header(default=None)
):
    """
    Verifica que el token sea válido.
    El frontend puede llamar esto al montar la app para saber si
    el paciente ya tiene sesión activa.
    """
    rut = get_rut_from_token(authorization)
    return {"ok": True, "rut": rut}


@router.post("/generar-batch")
def generar_batch(
    payload: list[GenerarCodigoRequest],
):
    """
    Genera códigos para múltiples RUTs en una sola llamada.
    Útil para envíos masivos de Fonasa.
    """
    if not payload:
        raise HTTPException(status_code=400, detail="Lista vacía")

    # Validar admin_key en el primer elemento
    if payload[0].admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Clave de admin inválida")

    codes   = _load_codes()
    results = []

    for item in payload:
        rut = _normalize_rut(item.rut)
        if not _valid_rut(rut):
            results.append({"rut": rut, "ok": False, "error": "RUT inválido"})
            continue

        existing = codes.get(rut)
        if existing and not existing.get("used"):
            results.append({"rut": rut, "ok": True, "codigo": existing["codigo"], "nuevo": False})
            continue

        code = _generate_code()
        codes[rut] = {
            "codigo":     code,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "used":       False,
            "used_at":    None,
            "nota":       item.nota,
        }
        results.append({"rut": rut, "ok": True, "codigo": code, "nuevo": True})

    _save_codes(codes)
    return {"ok": True, "total": len(results), "results": results}
