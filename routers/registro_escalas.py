# routers/registro_escalas.py
#
# Escalas clínicas para seguimiento de prótesis.
# Adaptadas para ser respondidas por el paciente (no el médico).
#
# Escalas incluidas:
#   - Harris Hip Score (HHS) — cadera
#   - Oxford Knee Score (OKS) — rodilla
#   - WOMAC — cadera y rodilla
#
# Temporalidad: preop | 3m | 6m | 1a | 2a
# Cada respuesta se guarda en:
#   /data/registro_protesis/patients/{rut}/scales/{cirugia_id}_{periodo}.json

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routers.registro_auth import get_rut_from_token

router = APIRouter(prefix="/api/registro/escalas", tags=["registro-escalas"])

DATA_PATH    = Path(os.getenv("DATA_PATH", "/data"))
PATIENTS_DIR = DATA_PATH / "registro_protesis" / "patients"

PERIODOS = ["preop", "3m", "6m", "1a", "2a"]

# ============================================================
# DEFINICIÓN DE ESCALAS
# Cada pregunta tiene texto adaptado al paciente y opciones.
# score_map mapea la respuesta a puntaje numérico.
# ============================================================

ESCALAS: Dict[str, Any] = {

    # ──────────────────────────────────────────────────────
    # HARRIS HIP SCORE — adaptado para paciente
    # Aplica a: cadera total, cadera parcial
    # Puntaje: 0-100 (mayor = mejor)
    # ──────────────────────────────────────────────────────
    "harris_hip": {
        "nombre":      "Harris Hip Score",
        "descripcion": "Cuestionario sobre su cadera operada. No hay respuestas correctas o incorrectas — responda según cómo se siente hoy.",
        "aplica_a":    ["Cadera total", "Cadera parcial (hemiartroplastía)"],
        "preguntas": [
            {
                "id":    "dolor",
                "texto": "¿Cuánto dolor siente en su cadera operada?",
                "tipo":  "opcion",
                "opciones": [
                    {"texto": "Sin dolor",                                        "valor": 44},
                    {"texto": "Dolor leve, ocasional, no limita actividades",     "valor": 40},
                    {"texto": "Dolor leve, no necesita analgésicos",              "valor": 30},
                    {"texto": "Dolor moderado, tolerable, con algunos analgésicos","valor": 20},
                    {"texto": "Dolor intenso, limita mucho mis actividades",      "valor": 10},
                    {"texto": "Dolor muy intenso, incapacitante",                 "valor": 0},
                ],
            },
            {
                "id":    "distancia_marcha",
                "texto": "¿Cuánto puede caminar sin detenerse por el dolor?",
                "tipo":  "opcion",
                "opciones": [
                    {"texto": "Sin limitación",                    "valor": 11},
                    {"texto": "Más de 1 km (unas 15 cuadras)",     "valor": 8},
                    {"texto": "Entre 500 m y 1 km (5-15 cuadras)", "valor": 5},
                    {"texto": "Solo en casa",                      "valor": 2},
                    {"texto": "No puedo caminar o solo con andador","valor": 0},
                ],
            },
            {
                "id":    "ayuda_marcha",
                "texto": "¿Usa algún apoyo para caminar?",
                "tipo":  "opcion",
                "opciones": [
                    {"texto": "No necesito ningún apoyo",                          "valor": 11},
                    {"texto": "Un bastón para distancias largas",                  "valor": 7},
                    {"texto": "Un bastón la mayor parte del tiempo",               "valor": 5},
                    {"texto": "Una muleta",                                        "valor": 3},
                    {"texto": "Dos bastones o dos muletas",                        "valor": 2},
                    {"texto": "No puedo caminar ni con apoyo",                     "valor": 0},
                ],
            },
            {
                "id":    "escaleras",
                "texto": "¿Cómo sube escaleras?",
                "tipo":  "opcion",
                "opciones": [
                    {"texto": "Normal, sin apoyarme en el pasamanos", "valor": 4},
                    {"texto": "Apoyándome en el pasamanos",           "valor": 2},
                    {"texto": "Con dificultad, de cualquier manera",  "valor": 1},
                    {"texto": "No puedo subir escaleras",             "valor": 0},
                ],
            },
            {
                "id":    "calzado",
                "texto": "¿Puede ponerse los zapatos y calcetines?",
                "tipo":  "opcion",
                "opciones": [
                    {"texto": "Sí, sin dificultad",              "valor": 4},
                    {"texto": "Con algo de dificultad",          "valor": 2},
                    {"texto": "No puedo hacerlo solo",           "valor": 0},
                ],
            },
            {
                "id":    "sentado",
                "texto": "¿Puede sentarse en una silla por más de una hora?",
                "tipo":  "opcion",
                "opciones": [
                    {"texto": "Sí, en cualquier silla",          "valor": 5},
                    {"texto": "Solo en sillas altas",            "valor": 3},
                    {"texto": "No puedo sentarme cómodamente",   "valor": 0},
                ],
            },
            {
                "id":    "transporte",
                "texto": "¿Puede entrar y salir de un auto o transporte público?",
                "tipo":  "opcion",
                "opciones": [
                    {"texto": "Sí, sin dificultad", "valor": 1},
                    {"texto": "No puedo",           "valor": 0},
                ],
            },
            {
                "id":    "cojera",
                "texto": "¿Cojea al caminar?",
                "tipo":  "opcion",
                "opciones": [
                    {"texto": "No cojeo",              "valor": 11},
                    {"texto": "Levemente",             "valor": 8},
                    {"texto": "Moderadamente",         "valor": 5},
                    {"texto": "Cojera severa",         "valor": 0},
                ],
            },
        ],
        "score_max": 100,
        "interpretacion": [
            {"min": 90, "max": 100, "texto": "Excelente"},
            {"min": 80, "max": 89,  "texto": "Bueno"},
            {"min": 70, "max": 79,  "texto": "Regular"},
            {"min": 0,  "max": 69,  "texto": "Malo"},
        ],
    },

    # ──────────────────────────────────────────────────────
    # OXFORD KNEE SCORE — adaptado para paciente
    # Aplica a: rodilla total, unicompartimental
    # 12 preguntas, cada una 0-4, total 0-48 (mayor = mejor)
    # ──────────────────────────────────────────────────────
    "oxford_knee": {
        "nombre":      "Oxford Knee Score",
        "descripcion": "Cuestionario sobre su rodilla operada durante las últimas 4 semanas.",
        "aplica_a":    ["Rodilla total", "Rodilla unicompartimental"],
        "preguntas": [
            {
                "id":    "dolor_general",
                "texto": "¿Cómo describiría el dolor habitual de su rodilla?",
                "tipo":  "opcion",
                "opciones": [
                    {"texto": "Sin dolor",             "valor": 4},
                    {"texto": "Muy leve",              "valor": 3},
                    {"texto": "Leve",                  "valor": 2},
                    {"texto": "Moderado",              "valor": 1},
                    {"texto": "Intenso",               "valor": 0},
                ],
            },
            {
                "id":    "higiene",
                "texto": "¿Tiene dificultad para lavarse y secarse?",
                "tipo":  "opcion",
                "opciones": [
                    {"texto": "Ninguna",                    "valor": 4},
                    {"texto": "Muy poca",                   "valor": 3},
                    {"texto": "Moderada",                   "valor": 2},
                    {"texto": "Mucha",                      "valor": 1},
                    {"texto": "Incapaz de hacerlo",         "valor": 0},
                ],
            },
            {
                "id":    "transporte",
                "texto": "¿Tiene dificultad para entrar/salir de un auto?",
                "tipo":  "opcion",
                "opciones": [
                    {"texto": "Ninguna",           "valor": 4},
                    {"texto": "Muy poca",          "valor": 3},
                    {"texto": "Moderada",          "valor": 2},
                    {"texto": "Mucha",             "valor": 1},
                    {"texto": "Incapaz",           "valor": 0},
                ],
            },
            {
                "id":    "distancia_marcha",
                "texto": "¿Cuánto puede caminar antes de que el dolor sea intenso?",
                "tipo":  "opcion",
                "opciones": [
                    {"texto": "Sin dolor al caminar",         "valor": 4},
                    {"texto": "Más de 30 minutos",            "valor": 3},
                    {"texto": "Entre 10 y 30 minutos",        "valor": 2},
                    {"texto": "Solo unos minutos",            "valor": 1},
                    {"texto": "No puedo caminar",             "valor": 0},
                ],
            },
            {
                "id":    "sentado_levantarse",
                "texto": "¿Tiene dolor al levantarse de una silla?",
                "tipo":  "opcion",
                "opciones": [
                    {"texto": "Sin dolor",         "valor": 4},
                    {"texto": "Muy leve",          "valor": 3},
                    {"texto": "Leve",              "valor": 2},
                    {"texto": "Moderado",          "valor": 1},
                    {"texto": "Intenso",           "valor": 0},
                ],
            },
            {
                "id":    "cojera",
                "texto": "¿Cojea al caminar?",
                "tipo":  "opcion",
                "opciones": [
                    {"texto": "Nunca o raramente",          "valor": 4},
                    {"texto": "A veces o solo al inicio",   "valor": 3},
                    {"texto": "A menudo, no solo al inicio","valor": 2},
                    {"texto": "La mayoría del tiempo",      "valor": 1},
                    {"texto": "Todo el tiempo",             "valor": 0},
                ],
            },
            {
                "id":    "arrodillarse",
                "texto": "¿Puede arrodillarse y levantarse?",
                "tipo":  "opcion",
                "opciones": [
                    {"texto": "Sí, sin dificultad",         "valor": 4},
                    {"texto": "Con poca dificultad",        "valor": 3},
                    {"texto": "Con moderada dificultad",    "valor": 2},
                    {"texto": "Con mucha dificultad",       "valor": 1},
                    {"texto": "No puedo",                   "valor": 0},
                ],
            },
            {
                "id":    "dolor_noche",
                "texto": "¿Le ha molestado la rodilla por las noches?",
                "tipo":  "opcion",
                "opciones": [
                    {"texto": "Ninguna noche",              "valor": 4},
                    {"texto": "Solo 1 o 2 noches",          "valor": 3},
                    {"texto": "Algunas noches",             "valor": 2},
                    {"texto": "La mayoría de las noches",   "valor": 1},
                    {"texto": "Todas las noches",           "valor": 0},
                ],
            },
            {
                "id":    "trabajo_doméstico",
                "texto": "¿Qué tan limitado está para hacer actividades domésticas?",
                "tipo":  "opcion",
                "opciones": [
                    {"texto": "Sin limitación",             "valor": 4},
                    {"texto": "Poco limitado",              "valor": 3},
                    {"texto": "Moderadamente limitado",     "valor": 2},
                    {"texto": "Muy limitado",               "valor": 1},
                    {"texto": "Incapaz de hacerlas",        "valor": 0},
                ],
            },
            {
                "id":    "confianza",
                "texto": "¿Siente que su rodilla puede fallar o ceder?",
                "tipo":  "opcion",
                "opciones": [
                    {"texto": "Nunca",                      "valor": 4},
                    {"texto": "Raramente",                  "valor": 3},
                    {"texto": "A veces",                    "valor": 2},
                    {"texto": "A menudo",                   "valor": 1},
                    {"texto": "Constantemente",             "valor": 0},
                ],
            },
            {
                "id":    "compras",
                "texto": "¿Puede ir de compras solo?",
                "tipo":  "opcion",
                "opciones": [
                    {"texto": "Sí, sin dificultad",         "valor": 4},
                    {"texto": "Con poca dificultad",        "valor": 3},
                    {"texto": "Con moderada dificultad",    "valor": 2},
                    {"texto": "Con mucha dificultad",       "valor": 1},
                    {"texto": "No puedo",                   "valor": 0},
                ],
            },
            {
                "id":    "escaleras",
                "texto": "¿Puede subir un tramo de escaleras?",
                "tipo":  "opcion",
                "opciones": [
                    {"texto": "Sí, sin dificultad",         "valor": 4},
                    {"texto": "Con poca dificultad",        "valor": 3},
                    {"texto": "Con moderada dificultad",    "valor": 2},
                    {"texto": "Con mucha dificultad",       "valor": 1},
                    {"texto": "No puedo",                   "valor": 0},
                ],
            },
        ],
        "score_max": 48,
        "interpretacion": [
            {"min": 41, "max": 48, "texto": "Excelente — mínimo o ningún problema"},
            {"min": 34, "max": 40, "texto": "Bueno — problemas menores"},
            {"min": 27, "max": 33, "texto": "Regular — problemas moderados"},
            {"min": 20, "max": 26, "texto": "Malo — problemas severos"},
            {"min": 0,  "max": 19, "texto": "Muy malo — problemas muy severos"},
        ],
    },

    # ──────────────────────────────────────────────────────
    # WOMAC — versión simplificada para paciente
    # Aplica a: cadera y rodilla
    # 24 preguntas, escala 0-4, mayor = peor
    # Normalizamos a 0-100 (mayor = mejor) para consistencia
    # ──────────────────────────────────────────────────────
    "womac": {
        "nombre":      "WOMAC",
        "descripcion": "Cuestionario sobre dolor, rigidez y función de su articulación operada en las últimas 48 horas.",
        "aplica_a":    ["Cadera total", "Cadera parcial (hemiartroplastía)", "Rodilla total", "Rodilla unicompartimental"],
        "secciones": [
            {
                "id":     "dolor",
                "titulo": "Dolor",
                "intro":  "¿Cuánto dolor siente al realizar estas actividades?",
                "preguntas": [
                    {"id": "dolor_caminar",   "texto": "Al caminar en terreno plano"},
                    {"id": "dolor_escaleras", "texto": "Al subir o bajar escaleras"},
                    {"id": "dolor_noche",     "texto": "De noche, mientras duerme"},
                    {"id": "dolor_reposo",    "texto": "Estando sentado o acostado"},
                    {"id": "dolor_pie",       "texto": "Al estar de pie"},
                ],
            },
            {
                "id":     "rigidez",
                "titulo": "Rigidez",
                "intro":  "¿Cuánta rigidez siente?",
                "preguntas": [
                    {"id": "rigidez_manana", "texto": "Al despertar en la mañana"},
                    {"id": "rigidez_tarde",  "texto": "Después de estar sentado o descansando durante el día"},
                ],
            },
            {
                "id":     "funcion",
                "titulo": "Función física",
                "intro":  "¿Cuánta dificultad tiene para realizar estas actividades?",
                "preguntas": [
                    {"id": "func_escaleras",    "texto": "Bajar escaleras"},
                    {"id": "func_subir",        "texto": "Subir escaleras"},
                    {"id": "func_levantarse",   "texto": "Levantarse de la silla"},
                    {"id": "func_pararse",      "texto": "Estar de pie"},
                    {"id": "func_inclinarse",   "texto": "Agacharse o inclinarse"},
                    {"id": "func_caminar",      "texto": "Caminar en terreno plano"},
                    {"id": "func_auto",         "texto": "Entrar o salir del auto"},
                    {"id": "func_compras",      "texto": "Ir de compras"},
                    {"id": "func_calcetines",   "texto": "Ponerse calcetines"},
                    {"id": "func_cama",         "texto": "Levantarse de la cama"},
                    {"id": "func_sacarse",      "texto": "Sacarse los calcetines"},
                    {"id": "func_bano",         "texto": "Bañarse"},
                    {"id": "func_sentarse",     "texto": "Sentarse"},
                    {"id": "func_sanitario",    "texto": "Usar el baño"},
                    {"id": "func_tareas",       "texto": "Hacer tareas domésticas pesadas"},
                    {"id": "func_livianas",     "texto": "Hacer tareas domésticas livianas"},
                ],
            },
        ],
        "opciones_comunes": [
            {"texto": "Ninguno/a",    "valor": 0},
            {"texto": "Poco/a",       "valor": 1},
            {"texto": "Moderado/a",   "valor": 2},
            {"texto": "Mucho/a",      "valor": 3},
            {"texto": "Muchísimo/a",  "valor": 4},
        ],
        "score_max": 96,   # 24 preguntas × 4 máx
        "interpretacion": [
            {"min": 0,  "max": 20,  "texto": "Función muy buena"},
            {"min": 21, "max": 40,  "texto": "Función buena"},
            {"min": 41, "max": 60,  "texto": "Función moderada"},
            {"min": 61, "max": 80,  "texto": "Función limitada"},
            {"min": 81, "max": 96,  "texto": "Función muy limitada"},
        ],
    },
}


# ============================================================
# HELPERS
# ============================================================
def _scales_dir(rut: str) -> Path:
    p = PATIENTS_DIR / rut / "scales"
    p.mkdir(parents=True, exist_ok=True)
    return p

def _surgery_path(rut: str, cirugia_id: str) -> Path:
    return PATIENTS_DIR / rut / "surgeries" / f"{cirugia_id}.json"

def _scale_path(rut: str, cirugia_id: str, periodo: str) -> Path:
    return _scales_dir(rut) / f"{cirugia_id}_{periodo}.json"

def _get_surgery(rut: str, cirugia_id: str) -> dict:
    path = _surgery_path(rut, cirugia_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Cirugía no encontrada")
    return json.loads(path.read_text(encoding="utf-8"))

def _escalas_para_tipo(tipo_protesis: str) -> list[str]:
    """Retorna las escalas aplicables según el tipo de prótesis."""
    resultado = []
    for key, escala in ESCALAS.items():
        aplica = escala.get("aplica_a", [])
        if tipo_protesis in aplica:
            resultado.append(key)
    return resultado

def _calcular_score(escala_key: str, respuestas: dict) -> dict:
    """Calcula el puntaje total y la interpretación."""
    escala = ESCALAS[escala_key]
    total  = 0

    if escala_key == "womac":
        for seccion in escala["secciones"]:
            for preg in seccion["preguntas"]:
                total += int(respuestas.get(preg["id"], 0))
    else:
        for preg in escala["preguntas"]:
            total += int(respuestas.get(preg["id"], 0))

    # Buscar interpretación
    interpretacion = ""
    for rango in escala.get("interpretacion", []):
        if rango["min"] <= total <= rango["max"]:
            interpretacion = rango["texto"]
            break

    return {
        "score":          total,
        "score_max":      escala["score_max"],
        "interpretacion": interpretacion,
    }


# ============================================================
# SCHEMAS
# ============================================================
class EscalaPayload(BaseModel):
    escala:     str            # "harris_hip" | "oxford_knee" | "womac"
    respuestas: Dict[str, Any]


# ============================================================
# ENDPOINTS
# ============================================================

@router.get("/catalogo")
def get_catalogo_escalas():
    """Retorna las definiciones completas de todas las escalas."""
    return ESCALAS


@router.get("/disponibles/{cirugia_id}")
def escalas_disponibles(
    cirugia_id: str,
    rut:        str = Depends(get_rut_from_token),
):
    """Retorna las escalas aplicables a una cirugía específica."""
    cirugia = _get_surgery(rut, cirugia_id)
    tipo    = cirugia.get("tipo_protesis", "")
    keys    = _escalas_para_tipo(tipo)
    return {
        "cirugia_id":    cirugia_id,
        "tipo_protesis": tipo,
        "escalas":       [
            {
                "key":         k,
                "nombre":      ESCALAS[k]["nombre"],
                "descripcion": ESCALAS[k].get("descripcion", ""),
            }
            for k in keys
        ],
    }


@router.post("/{cirugia_id}/{periodo}")
def guardar_escala(
    cirugia_id: str,
    periodo:    str,
    payload:    EscalaPayload,
    rut:        str = Depends(get_rut_from_token),
):
    """
    Guarda las respuestas de una escala para una cirugía+periodo.
    Calcula el score y marca la escala como completada.
    """
    # Validar período
    if periodo not in PERIODOS:
        raise HTTPException(
            status_code=400,
            detail=f"Período inválido. Debe ser uno de: {', '.join(PERIODOS)}"
        )

    # Validar escala
    if payload.escala not in ESCALAS:
        raise HTTPException(
            status_code=400,
            detail=f"Escala desconocida: {payload.escala}"
        )

    # Validar que la cirugía exista
    cirugia = _get_surgery(rut, cirugia_id)

    # Calcular score
    resultado = _calcular_score(payload.escala, payload.respuestas)

    # Guardar archivo de respuestas
    now  = datetime.now(timezone.utc).isoformat()
    data = {
        "rut":            rut,
        "cirugia_id":     cirugia_id,
        "periodo":        periodo,
        "escala":         payload.escala,
        "escala_nombre":  ESCALAS[payload.escala]["nombre"],
        "respuestas":     payload.respuestas,
        "score":          resultado["score"],
        "score_max":      resultado["score_max"],
        "interpretacion": resultado["interpretacion"],
        "completada_at":  now,
    }

    scale_path = _scale_path(rut, cirugia_id, periodo)
    # Si ya existía una escala previa para este periodo, la sobrescribimos
    # (esto permite "reabrir" y volver a contestar)
    existing = []
    if scale_path.exists():
        try:
            prev = json.loads(scale_path.read_text(encoding="utf-8"))
            if isinstance(prev, dict) and "escalas" in prev:
                existing = prev["escalas"]
        except Exception:
            pass

    # Eliminar escala previa del mismo tipo (si existía) y agregar la nueva
    existing = [e for e in existing if e.get("escala") != payload.escala]
    existing.append(data)

    final_doc = {
        "rut":          rut,
        "cirugia_id":   cirugia_id,
        "periodo":      periodo,
        "escalas":      existing,
        "updated_at":   now,
    }

    try:
        scale_path.write_text(
            json.dumps(final_doc, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error guardando escala: {e}")

    # Marcar la escala como completada en el archivo de cirugía
    surgery_path = _surgery_path(rut, cirugia_id)
    cirugia.setdefault("escalas_programadas", {}).setdefault(periodo, {})
    cirugia["escalas_programadas"][periodo]["completada"]    = True
    cirugia["escalas_programadas"][periodo]["completada_at"] = now
    cirugia["updated_at"] = now

    try:
        surgery_path.write_text(
            json.dumps(cirugia, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error actualizando cirugía: {e}")

    return {
        "ok":             True,
        "score":          resultado["score"],
        "score_max":      resultado["score_max"],
        "interpretacion": resultado["interpretacion"],
        "escala_nombre":  ESCALAS[payload.escala]["nombre"],
        "periodo":        periodo,
    }


@router.get("/{cirugia_id}")
def listar_escalas_cirugia(
    cirugia_id: str,
    rut:        str = Depends(get_rut_from_token),
):
    """
    Lista todas las escalas completadas para una cirugía.
    Útil para la vista detalle / historial.
    """
    # Validar que la cirugía exista
    _get_surgery(rut, cirugia_id)

    scales_dir = _scales_dir(rut)
    resultado  = {}

    for f in sorted(scales_dir.glob(f"{cirugia_id}_*.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
            periodo = doc.get("periodo", f.stem.split("_")[-1])
            resultado[periodo] = doc
        except Exception:
            continue

    return {
        "cirugia_id": cirugia_id,
        "escalas":    resultado,
    }


@router.get("/{cirugia_id}/{periodo}")
def get_escala_periodo(
    cirugia_id: str,
    periodo:    str,
    rut:        str = Depends(get_rut_from_token),
):
    """Retorna la escala completada para un período específico."""
    if periodo not in PERIODOS:
        raise HTTPException(status_code=400, detail="Período inválido")

    # Validar ownership
    _get_surgery(rut, cirugia_id)

    scale_path = _scale_path(rut, cirugia_id, periodo)
    if not scale_path.exists():
        raise HTTPException(status_code=404, detail="Escala no completada en este período")

    return json.loads(scale_path.read_text(encoding="utf-8"))
