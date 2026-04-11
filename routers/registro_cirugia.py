# routers/registro_cirugia.py
#
# Registro de cirugía e implante de prótesis.
# El paciente registra su propia cirugía usando su token JWT.
#
# Estructura en disco:
#   /data/registro_protesis/patients/{rut}/
#       surgeries/{id}.json   ← datos de la cirugía
#       implants/{id}.json    ← datos del implante

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routers.registro_auth import get_rut_from_token

router = APIRouter(prefix="/api/registro/cirugia", tags=["registro-cirugia"])

# ============================================================
# CONFIG
# ============================================================
DATA_PATH    = Path(os.getenv("DATA_PATH", "/data"))
PATIENTS_DIR = DATA_PATH / "registro_protesis" / "patients"

# ============================================================
# CATÁLOGOS
# ============================================================
TIPOS_PROTESIS = [
    "Cadera total",
    "Cadera parcial (hemiartroplastía)",
    "Rodilla total",
    "Rodilla unicompartimental",
    "Hombro total",
    "Hombro reverso",
    "Tobillo total",
    "Codo total",
    "Otra",
]

LADOS = ["Derecho", "Izquierdo", "Bilateral"]

ABORDAJES_CADERA = [
    "Posterior",
    "Lateral directo",
    "Anterolateral (Hardinge)",
    "Anterior directo (DAA)",
    "SuperPATH",
    "Otro",
]

FIJACIONES = [
    "Cementada",
    "No cementada",
    "Híbrida (vástago cementado, cúpula no cementada)",
    "Híbrida inversa",
]

INDICACIONES = [
    "Artrosis primaria",
    "Artrosis secundaria",
    "Fractura",
    "Necrosis avascular",
    "Displasia",
    "Artritis reumatoide",
    "Falla de prótesis previa (revisión)",
    "Otra",
]

PREVISIONES = ["Fonasa A", "Fonasa B", "Fonasa C", "Fonasa D", "Isapre", "Particular", "Otra"]

# ============================================================
# HELPERS
# ============================================================
def _patient_dir(rut: str) -> Path:
    return PATIENTS_DIR / rut

def _surgeries_dir(rut: str) -> Path:
    return _patient_dir(rut) / "surgeries"

def _implants_dir(rut: str) -> Path:
    return _patient_dir(rut) / "implants"

def _ensure_dirs(rut: str) -> None:
    for d in [_surgeries_dir(rut), _implants_dir(rut)]:
        d.mkdir(parents=True, exist_ok=True)

def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(status_code=500, detail="Error leyendo archivo")

def _write_json(path: Path, data: dict) -> None:
    try:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        raise HTTPException(status_code=500, detail="Error guardando archivo")

def _list_surgeries(rut: str) -> list:
    d = _surgeries_dir(rut)
    if not d.exists():
        return []
    result = []
    for f in sorted(d.glob("*.json")):
        try:
            result.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return result

# ============================================================
# SCHEMAS
# ============================================================
class CirugiaPayload(BaseModel):
    # Datos de la cirugía
    fecha_cirugia:    str              # YYYY-MM-DD
    tipo_protesis:    str
    lado:             str
    indicacion:       str
    abordaje:         Optional[str] = ""

    # Implante
    marca_implante:   Optional[str] = ""
    modelo_implante:  Optional[str] = ""
    fijacion:         Optional[str] = ""
    numero_serie:     Optional[str] = ""

    # Cirujano
    nombre_cirujano:  str
    rut_cirujano:     Optional[str] = ""
    especialidad_cirujano: Optional[str] = "Traumatología"

    # Clínica / hospital
    nombre_clinica:   str
    ciudad_clinica:   str
    region_clinica:   Optional[str] = ""
    prevision:        Optional[str] = ""

    # Extra
    notas:            Optional[str] = ""


class CirugiaUpdatePayload(BaseModel):
    fecha_cirugia:    Optional[str] = None
    tipo_protesis:    Optional[str] = None
    lado:             Optional[str] = None
    indicacion:       Optional[str] = None
    abordaje:         Optional[str] = None
    marca_implante:   Optional[str] = None
    modelo_implante:  Optional[str] = None
    fijacion:         Optional[str] = None
    numero_serie:     Optional[str] = None
    nombre_cirujano:  Optional[str] = None
    rut_cirujano:     Optional[str] = None
    nombre_clinica:   Optional[str] = None
    ciudad_clinica:   Optional[str] = None
    region_clinica:   Optional[str] = None
    prevision:        Optional[str] = None
    notas:            Optional[str] = None


# ============================================================
# ENDPOINTS
# ============================================================

@router.get("/catalogo")
def get_catalogo():
    """Devuelve los catálogos para poblar los selects del frontend."""
    return {
        "tipos_protesis":      TIPOS_PROTESIS,
        "lados":               LADOS,
        "abordajes_cadera":    ABORDAJES_CADERA,
        "fijaciones":          FIJACIONES,
        "indicaciones":        INDICACIONES,
        "previsiones":         PREVISIONES,
    }


@router.get("")
def listar_cirugias(rut: str = Depends(get_rut_from_token)):
    """Lista todas las cirugías registradas del paciente."""
    return _list_surgeries(rut)


@router.post("")
def crear_cirugia(
    payload: CirugiaPayload,
    rut: str = Depends(get_rut_from_token)
):
    """Paciente registra una nueva cirugía."""
    _ensure_dirs(rut)

    cirugia_id = str(uuid.uuid4())[:8]
    now        = datetime.now(timezone.utc).isoformat()

    data = {
        "id":               cirugia_id,
        "rut":              rut,
        "fecha_cirugia":    payload.fecha_cirugia,
        "tipo_protesis":    payload.tipo_protesis,
        "lado":             payload.lado,
        "indicacion":       payload.indicacion,
        "abordaje":         payload.abordaje or "",

        "implante": {
            "marca":        payload.marca_implante or "",
            "modelo":       payload.modelo_implante or "",
            "fijacion":     payload.fijacion or "",
            "numero_serie": payload.numero_serie or "",
        },

        "cirujano": {
            "nombre":       payload.nombre_cirujano,
            "rut":          payload.rut_cirujano or "",
            "especialidad": payload.especialidad_cirujano or "Traumatología",
        },

        "clinica": {
            "nombre":  payload.nombre_clinica,
            "ciudad":  payload.ciudad_clinica,
            "region":  payload.region_clinica or "",
        },

        "prevision":    payload.prevision or "",
        "notas":        payload.notas or "",
        "created_at":   now,
        "updated_at":   now,

        # Seguimiento de escalas — se actualizan automáticamente
        "escalas_programadas": {
            "preop":   {"programada": True,  "completada": False, "fecha_envio": None},
            "3m":      {"programada": True,  "completada": False, "fecha_envio": None},
            "6m":      {"programada": True,  "completada": False, "fecha_envio": None},
            "1a":      {"programada": True,  "completada": False, "fecha_envio": None},
            "2a":      {"programada": True,  "completada": False, "fecha_envio": None},
        }
    }

    path = _surgeries_dir(rut) / f"{cirugia_id}.json"
    _write_json(path, data)

    return {"ok": True, "id": cirugia_id, "data": data}


@router.get("/{cirugia_id}")
def get_cirugia(
    cirugia_id: str,
    rut: str = Depends(get_rut_from_token)
):
    """Obtiene una cirugía específica del paciente."""
    path = _surgeries_dir(rut) / f"{cirugia_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Cirugía no encontrada")
    return _read_json(path)


@router.put("/{cirugia_id}")
def actualizar_cirugia(
    cirugia_id: str,
    payload:    CirugiaUpdatePayload,
    rut:        str = Depends(get_rut_from_token)
):
    """Paciente edita datos de su cirugía."""
    path = _surgeries_dir(rut) / f"{cirugia_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Cirugía no encontrada")

    data    = _read_json(path)
    updates = payload.dict(exclude_none=True)
    now     = datetime.now(timezone.utc).isoformat()

    # Campos planos
    for field in ["fecha_cirugia", "tipo_protesis", "lado", "indicacion",
                  "abordaje", "prevision", "notas"]:
        if field in updates:
            data[field] = updates[field]

    # Implante
    for field in ["marca_implante", "modelo_implante", "fijacion", "numero_serie"]:
        key = field.replace("_implante", "").replace("numero_serie", "numero_serie")
        if field in updates:
            mapped = field.replace("_implante", "")
            if field == "numero_serie":
                data["implante"]["numero_serie"] = updates[field]
            else:
                data["implante"][mapped] = updates[field]

    # Cirujano
    if "nombre_cirujano" in updates:
        data["cirujano"]["nombre"] = updates["nombre_cirujano"]
    if "rut_cirujano" in updates:
        data["cirujano"]["rut"] = updates["rut_cirujano"]

    # Clínica
    if "nombre_clinica" in updates:
        data["clinica"]["nombre"] = updates["nombre_clinica"]
    if "ciudad_clinica" in updates:
        data["clinica"]["ciudad"] = updates["ciudad_clinica"]
    if "region_clinica" in updates:
        data["clinica"]["region"] = updates["region_clinica"]

    data["updated_at"] = now
    _write_json(path, data)

    return {"ok": True, "data": data}
