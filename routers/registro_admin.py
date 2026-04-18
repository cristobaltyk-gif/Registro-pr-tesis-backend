# routers/registro_admin.py

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime
import json
import os

from routers.registro_auth import get_rut_from_token
from modules.rut_utils import normalize_rut, is_valid_rut

router = APIRouter(prefix="/api/registro/admin", tags=["registro-admin"])

BASE_DIR = Path(os.getenv("DATA_PATH", "/data")) / "registro_protesis" / "patients"


def patient_dir(rut: str) -> Path:
    return BASE_DIR / normalize_rut(rut)


def admin_file(rut: str) -> Path:
    return patient_dir(rut) / "admin.json"


def ensure_patient_dirs(rut: str):
    root = patient_dir(rut)
    root.mkdir(parents=True, exist_ok=True)
    for sub in ["surgeries", "implants", "followups", "complications", "reoperations", "documents", "snapshots"]:
        (root / sub).mkdir(exist_ok=True)


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(status_code=500, detail="Error leyendo archivo JSON")


def write_json(path: Path, data: dict):
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        raise HTTPException(status_code=500, detail="Error guardando archivo JSON")


class PatientAdminPayload(BaseModel):
    rut:               str
    nombre:            str
    apellido_paterno:  str
    apellido_materno:  str = ""
    fecha_nacimiento:  str
    direccion:         str = ""
    telefono:          str = ""
    email:             str = ""
    prevision:         str = ""
    sexo:              str = ""


@router.get("/{rut}")
def get_patient_admin(
    rut: str,
    token_rut: str = Depends(get_rut_from_token)
):
    rut = normalize_rut(rut)
    if not is_valid_rut(rut):
        raise HTTPException(status_code=400, detail="RUT inválido")

    path = admin_file(rut)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    return read_json(path)


@router.post("")
def create_patient_admin(
    payload: PatientAdminPayload,
    token_rut: str = Depends(get_rut_from_token)
):
    rut = normalize_rut(payload.rut)
    if not is_valid_rut(rut):
        raise HTTPException(status_code=400, detail="RUT inválido")

    path = admin_file(rut)
    if path.exists():
        raise HTTPException(status_code=409, detail="Paciente ya existe")

    ensure_patient_dirs(rut)
    now = datetime.utcnow().isoformat()

    data = {
        "rut":              rut,
        "nombre":           payload.nombre.strip(),
        "apellido_paterno": payload.apellido_paterno.strip(),
        "apellido_materno": payload.apellido_materno.strip(),
        "fecha_nacimiento": payload.fecha_nacimiento,
        "direccion":        payload.direccion.strip(),
        "telefono":         payload.telefono.strip(),
        "email":            payload.email.strip(),
        "prevision":        payload.prevision.strip(),
        "sexo":             payload.sexo.strip(),
        "created_at":       now,
        "updated_at":       now,
        "created_by":       token_rut,
        "updated_by":       token_rut,
    }

    write_json(path, data)
    return {"ok": True, "rut": rut}


@router.put("/{rut}")
def update_patient_admin(
    rut: str,
    payload: PatientAdminPayload,
    token_rut: str = Depends(get_rut_from_token)
):
    rut = normalize_rut(rut)
    if not is_valid_rut(rut):
        raise HTTPException(status_code=400, detail="RUT inválido")

    path = admin_file(rut)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    current = read_json(path)
    now     = datetime.utcnow().isoformat()

    updated = {
        **current,
        "rut":              rut,
        "nombre":           payload.nombre.strip(),
        "apellido_paterno": payload.apellido_paterno.strip(),
        "apellido_materno": payload.apellido_materno.strip(),
        "fecha_nacimiento": payload.fecha_nacimiento,
        "direccion":        payload.direccion.strip(),
        "telefono":         payload.telefono.strip(),
        "email":            payload.email.strip(),
        "prevision":        payload.prevision.strip(),
        "sexo":             payload.sexo.strip(),
        "updated_at":       now,
        "updated_by":       token_rut,
    }

    write_json(path, updated)
    return {"ok": True, "rut": rut}
