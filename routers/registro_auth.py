# routers/registro_auth.py

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

DATA_PATH   = Path(os.getenv("DATA_PATH", "/data"))
CODES_FILE  = DATA_PATH / "registro_protesis" / "access_codes.json"
JWT_SECRET  = os.getenv("REGISTRO_JWT_SECRET", "cambiar_en_produccion_registro_ica")
JWT_ALGO    = "HS256"
JWT_EXPIRE_DAYS = 365
CODE_LENGTH = 8

ADMIN_KEY   = os.getenv("REGISTRO_ADMIN_KEY", "admin_registro_ica")


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
    CODES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


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
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sesión expirada")
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido")


def get_rut_from_token(
    authorization: str | None = Header(default=None)
) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token requerido")
    token = authorization.removeprefix("Bearer ").strip()
    return _decode_token(token)


# ============================================================
# SCHEMAS
# ============================================================
class IngresarRequest(BaseModel):
    rut: str


class GenerarCodigoRequest(BaseModel):
    rut:       str
    admin_key: str
    nota:      str = ""


class ValidarCodigoRequest(BaseModel):
    rut:    str
    codigo: str


# ============================================================
# ENDPOINTS
# ============================================================

@router.post("/ingresar")
def ingresar(payload: IngresarRequest):
    """
    Paciente ingresa solo con su RUT — sin código.
    Genera token JWT directamente.
    Primera etapa: acceso abierto para registro inicial.
    """
    rut = _normalize_rut(payload.rut)
    if not _valid_rut(rut):
        raise HTTPException(status_code=400, detail="RUT inválido. Formato esperado: 12345678-9")

    token = _create_token(rut)
    return {"ok": True, "rut": rut, "token": token}


@router.get("/verificar")
def verificar_token(
    authorization: str | None = Header(default=None)
):
    """Verifica que el token sea válido."""
    rut = get_rut_from_token(authorization)
    return {"ok": True, "rut": rut}


@router.post("/generar")
def generar_codigo(payload: GenerarCodigoRequest):
    """Admin genera un código de acceso para un RUT."""
    if payload.admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Clave de admin inválida")

    rut = _normalize_rut(payload.rut)
    if not _valid_rut(rut):
        raise HTTPException(status_code=400, detail="RUT inválido")

    codes    = _load_codes()
    existing = codes.get(rut)
    if existing and not existing.get("used"):
        return {"ok": True, "rut": rut, "codigo": existing["codigo"], "nuevo": False}

    code = _generate_code()
    codes[rut] = {
        "codigo":     code,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "used":       False,
        "used_at":    None,
        "nota":       payload.nota,
    }
    _save_codes(codes)
    return {"ok": True, "rut": rut, "codigo": code, "nuevo": True}


@router.post("/validar")
def validar_codigo(payload: ValidarCodigoRequest):
    """Paciente valida RUT + código → devuelve token JWT."""
    rut = _normalize_rut(payload.rut)
    if not _valid_rut(rut):
        raise HTTPException(status_code=400, detail="RUT inválido")

    codes = _load_codes()
    entry = codes.get(rut)

    if not entry:
        raise HTTPException(status_code=404, detail="RUT no registrado.")
    if entry["codigo"].upper() != payload.codigo.strip().upper():
        raise HTTPException(status_code=401, detail="Código incorrecto")

    if not entry.get("used"):
        entry["used"]    = True
        entry["used_at"] = datetime.now(timezone.utc).isoformat()
        codes[rut]       = entry
        _save_codes(codes)

    token = _create_token(rut)
    return {"ok": True, "rut": rut, "token": token}


@router.post("/generar-batch")
def generar_batch(payload: list[GenerarCodigoRequest]):
    """Genera códigos para múltiples RUTs — para envíos masivos de Fonasa."""
    if not payload:
        raise HTTPException(status_code=400, detail="Lista vacía")
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
    
