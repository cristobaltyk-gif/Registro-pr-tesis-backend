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
]

LADOS = ["Derecho", "Izquierdo"]

ABORDAJES_CADERA = [
    "Posterior",
    "Lateral directo",
    "Anterolateral (Hardinge)",
    "Anterior directo (DAA)",
    "SuperPATH",
    "Otro",
]

FIJACIONES_CADERA = [
    "No cementada",
    "Cementada",
    "Híbrida (vástago cementado, cotilo no cementado)",
    "Híbrida inversa (cotilo cementado, vástago no cementado)",
]

ALINEACIONES_RODILLA = [
    "Mechanical Alignment",
    "Kinematic Alignment",
    "Inverse Kinematic Alignment",
    "Restricted Alignment",
    "Functional Positioning",
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

PREVISIONES = ["Fonasa", "Isapre", "Particular", "Otra"]

MARCAS = {
    "cadera": [
        {"id": "stryker", "label": "Stryker",        "cotilo": "Trident",   "vastago": "Accolade II"},
        {"id": "depuy",   "label": "DePuy Synthes",  "cotilo": "Pinnacle",  "vastago": "Corail"},
        {"id": "zimmer",  "label": "Zimmer Biomet",  "cotilo": "G7",        "vastago": "Taperloc"},
        {"id": "smith",   "label": "Smith & Nephew", "cotilo": "R3",        "vastago": "Anthology"},
    ],
    "rodilla": [
        {"id": "stryker", "label": "Stryker",        "modelo": "Triathlon"},
        {"id": "depuy",   "label": "DePuy Synthes",  "modelo": "Attune"},
        {"id": "zimmer",  "label": "Zimmer Biomet",  "modelo": "Persona"},
        {"id": "smith",   "label": "Smith & Nephew", "modelo": "Genesis II"},
    ],
}

ROBOTICA = ["Sin robótica", "Mako (Stryker)", "ROSA (Zimmer Biomet)"]

# ============================================================
# HELPERS
# ============================================================
def _surgeries_dir(rut: str) -> Path:
    return PATIENTS_DIR / rut / "surgeries"

def _ensure_dirs(rut: str) -> None:
    _surgeries_dir(rut).mkdir(parents=True, exist_ok=True)

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
    fecha_cirugia:    str
    tipo_protesis:    str
    lado:             str
    indicacion:       str

    # Lugar
    nombre_clinica:   str
    ciudad_clinica:   str
    region_clinica:   Optional[str] = ""

    # Cirujano
    nombre_cirujano:  str
    rut_cirujano:     Optional[str] = ""

    # Implante común
    marca_implante:   Optional[str] = ""
    fijacion:         Optional[str] = ""   # cadera
    alineacion:       Optional[str] = ""   # rodilla
    robotica:         Optional[str] = ""

    # Cadera
    cotilo:           Optional[str] = ""
    vastago:          Optional[str] = ""
    abordaje:         Optional[str] = ""

    # Rodilla
    modelo_implante:  Optional[str] = ""

    # Extra
    prevision:        Optional[str] = ""
    notas:            Optional[str] = ""


class CirugiaUpdatePayload(BaseModel):
    fecha_cirugia:    Optional[str] = None
    tipo_protesis:    Optional[str] = None
    lado:             Optional[str] = None
    indicacion:       Optional[str] = None
    nombre_clinica:   Optional[str] = None
    ciudad_clinica:   Optional[str] = None
    region_clinica:   Optional[str] = None
    nombre_cirujano:  Optional[str] = None
    marca_implante:   Optional[str] = None
    fijacion:         Optional[str] = None
    alineacion:       Optional[str] = None
    robotica:         Optional[str] = None
    cotilo:           Optional[str] = None
    vastago:          Optional[str] = None
    modelo_implante:  Optional[str] = None
    prevision:        Optional[str] = None
    notas:            Optional[str] = None

# ============================================================
# ENDPOINTS
# ============================================================

@router.get("/catalogo")
def get_catalogo():
    return {
        "tipos_protesis":      TIPOS_PROTESIS,
        "lados":               LADOS,
        "abordajes_cadera":    ABORDAJES_CADERA,
        "fijaciones_cadera":   FIJACIONES_CADERA,
        "alineaciones_rodilla": ALINEACIONES_RODILLA,
        "indicaciones":        INDICACIONES,
        "previsiones":         PREVISIONES,
        "marcas":              MARCAS,
        "robotica":            ROBOTICA,
    }


@router.get("")
def listar_cirugias(rut: str = Depends(get_rut_from_token)):
    return _list_surgeries(rut)


@router.post("")
def crear_cirugia(
    payload: CirugiaPayload,
    rut:     str = Depends(get_rut_from_token)
):
    _ensure_dirs(rut)
    cirugia_id = str(uuid.uuid4())[:8]
    now        = datetime.now(timezone.utc).isoformat()
    es_cadera  = "cadera" in payload.tipo_protesis.lower()

    data = {
        "id":            cirugia_id,
        "rut":           rut,
        "fecha_cirugia": payload.fecha_cirugia,
        "tipo_protesis": payload.tipo_protesis,
        "lado":          payload.lado,
        "indicacion":    payload.indicacion,

        "clinica": {
            "nombre": payload.nombre_clinica,
            "ciudad": payload.ciudad_clinica,
            "region": payload.region_clinica or "",
        },

        "cirujano": {
            "nombre": payload.nombre_cirujano,
            "rut":    payload.rut_cirujano or "",
        },

        "implante": {
            "marca":    payload.marca_implante or "",
            "robotica": payload.robotica or "",
            # cadera
            "cotilo":    payload.cotilo   or "",
            "vastago":   payload.vastago  or "",
            "fijacion":  payload.fijacion or "",
            "abordaje":  payload.abordaje or "",
            # rodilla
            "modelo":    payload.modelo_implante or "",
            "alineacion": payload.alineacion or "",
        },

        "prevision":  payload.prevision or "",
        "notas":      payload.notas or "",
        "created_at": now,
        "updated_at": now,

        "escalas_programadas": {
            "preop": {"programada": True, "completada": False, "fecha_envio": None},
            "3m":    {"programada": True, "completada": False, "fecha_envio": None},
            "6m":    {"programada": True, "completada": False, "fecha_envio": None},
            "1a":    {"programada": True, "completada": False, "fecha_envio": None},
            "2a":    {"programada": True, "completada": False, "fecha_envio": None},
        }
    }

    path = _surgeries_dir(rut) / f"{cirugia_id}.json"
    _write_json(path, data)
    return {"ok": True, "id": cirugia_id, "data": data}


@router.get("/{cirugia_id}")
def get_cirugia(
    cirugia_id: str,
    rut:        str = Depends(get_rut_from_token)
):
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
    path = _surgeries_dir(rut) / f"{cirugia_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Cirugía no encontrada")

    data    = _read_json(path)
    updates = payload.dict(exclude_none=True)
    now     = datetime.now(timezone.utc).isoformat()

    for field in ["fecha_cirugia", "tipo_protesis", "lado", "indicacion", "prevision", "notas"]:
        if field in updates:
            data[field] = updates[field]

    if "nombre_clinica"  in updates: data["clinica"]["nombre"]  = updates["nombre_clinica"]
    if "ciudad_clinica"  in updates: data["clinica"]["ciudad"]  = updates["ciudad_clinica"]
    if "region_clinica"  in updates: data["clinica"]["region"]  = updates["region_clinica"]
    if "nombre_cirujano" in updates: data["cirujano"]["nombre"] = updates["nombre_cirujano"]

    implante_fields = ["marca_implante", "fijacion", "alineacion", "robotica", "cotilo", "vastago", "modelo_implante", "abordaje"]
    implante_keys   = {"marca_implante": "marca", "modelo_implante": "modelo"}
    for field in implante_fields:
        if field in updates:
            key = implante_keys.get(field, field)
            data["implante"][key] = updates[field]

    data["updated_at"] = now
    _write_json(path, data)
    return {"ok": True, "data": data}
    
