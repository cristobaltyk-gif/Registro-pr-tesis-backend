# modules/registro_scheduler.py
#
# Scheduler diario para el registro nacional de prótesis.
# Corre a las 09:00 hora Chile.
#
# Lógica:
#   1. Recorre todos los pacientes en /data/registro_protesis/patients/
#   2. Para cada cirugía calcula los hitos (3m, 6m, 1a, 2a)
#   3. Si hoy es el día del hito y aún no se envió → envía email
#   4. Marca el envío en la cirugía para no enviar dos veces

from __future__ import annotations

import json
import os
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CHILE_TZ     = ZoneInfo("America/Santiago")
DATA_PATH    = Path(os.getenv("DATA_PATH", "/data"))
PATIENTS_DIR = DATA_PATH / "registro_protesis" / "patients"
FRONTEND_URL = os.getenv("REGISTRO_FRONTEND_URL", "https://registro.icarticular.cl")

# Días desde la cirugía para cada hito
HITOS = {
    "3m":  90,
    "6m":  180,
    "1a":  365,
    "2a":  730,
}

# Tolerancia — enviar si estamos dentro de ±2 días del hito
# (por si el scheduler no corrió exactamente ese día)
TOLERANCIA_DIAS = 2


# ============================================================
# HELPERS
# ============================================================

def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_json(path: Path, data: dict) -> None:
    try:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception as e:
        print(f"⚠️ Error guardando {path}: {e}")


def _get_all_patients() -> list[Path]:
    """Retorna lista de directorios de pacientes."""
    if not PATIENTS_DIR.exists():
        return []
    return [d for d in PATIENTS_DIR.iterdir() if d.is_dir()]


def _get_surgeries(patient_dir: Path) -> list[dict]:
    surgeries_dir = patient_dir / "surgeries"
    if not surgeries_dir.exists():
        return []
    result = []
    for f in sorted(surgeries_dir.glob("*.json")):
        data = _load_json(f)
        if data:
            data["_path"] = str(f)
            result.append(data)
    return result


def _get_admin(patient_dir: Path) -> dict:
    return _load_json(patient_dir / "admin.json")


def _dias_desde_cirugia(fecha_cirugia_str: str, hoy: date) -> int | None:
    try:
        fecha = date.fromisoformat(fecha_cirugia_str)
        return (hoy - fecha).days
    except Exception:
        return None


def _debe_enviar(cirugia: dict, periodo: str, dias_transcurridos: int) -> bool:
    """
    Retorna True si hay que enviar el email del período.
    Condiciones:
    - El período está programado
    - No se ha enviado aún
    - Estamos dentro del rango de días del hito (±TOLERANCIA_DIAS)
    """
    ep = cirugia.get("escalas_programadas", {}).get(periodo, {})
    if not ep.get("programada", True):
        return False
    if ep.get("email_enviado"):
        return False

    dias_hito = HITOS[periodo]
    return abs(dias_transcurridos - dias_hito) <= TOLERANCIA_DIAS


# ============================================================
# EMAIL
# ============================================================

def _enviar_email_escala(
    email:          str,
    nombre:         str,
    rut:            str,
    periodo:        str,
    tipo_protesis:  str,
    fecha_cirugia:  str,
) -> bool:
    """Envía email al paciente con link para completar la escala."""
    try:
        import resend
        resend.api_key = os.getenv("RESEND_API_KEY", "")
        if not resend.api_key:
            print(f"⚠️ RESEND_API_KEY no configurada")
            return False

        LOGO_URL = "https://lh3.googleusercontent.com/sitesv/APaQ0SSMBWniO2NWVDwGoaCaQjiel3lBKrmNgpaZZY-ZsYzTawYaf-_7Ad-xfeKVyfCqxa7WgzhWPKHtdaCS0jGtFRrcseP-R8KG1LfY2iYuhZeClvWEBljPLh9KANIClyKSsiSJH8_of4LPUOJUl7cWNwB2HKR7RVH_xB_h9BG-8Nr9jnorb-q2gId2=w300"

        PERIODOS_TEXTO = {
            "preop": "antes de su cirugía",
            "3m":    "a los 3 meses de su cirugía",
            "6m":    "a los 6 meses de su cirugía",
            "1a":    "al año de su cirugía",
            "2a":    "a los 2 años de su cirugía",
        }

        texto_periodo = PERIODOS_TEXTO.get(periodo, periodo)
        link          = f"{FRONTEND_URL}?rut={rut}&periodo={periodo}"

        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; background: #fff;">
            <img src="{LOGO_URL}" alt="ICA" style="height: 60px; margin-bottom: 24px;" />
            <h2 style="color: #0f172a;">Es hora de su evaluación de seguimiento</h2>
            <p>Estimado/a <strong>{nombre}</strong>,</p>
            <p>Han llegado los primeros resultados de su proceso de recuperación. Es momento de completar su evaluación <strong>{texto_periodo}</strong>.</p>

            <div style="background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 16px; margin: 20px 0;">
                <p style="margin: 4px 0;"><strong>Prótesis:</strong> {tipo_protesis}</p>
                <p style="margin: 4px 0;"><strong>Fecha de cirugía:</strong> {fecha_cirugia}</p>
                <p style="margin: 4px 0;"><strong>Evaluación:</strong> {texto_periodo.capitalize()}</p>
            </div>

            <p>El cuestionario toma <strong>menos de 5 minutos</strong> y nos ayuda a monitorear su recuperación y mejorar la atención de futuros pacientes.</p>

            <a href="{link}" style="
                display: inline-block;
                background: #0f172a;
                color: white;
                padding: 14px 28px;
                border-radius: 8px;
                text-decoration: none;
                font-weight: bold;
                font-size: 15px;
                margin: 20px 0;
            ">📋 Completar evaluación</a>

            <p style="font-size: 13px; color: #64748b; margin-top: 8px;">
                Si el botón no funciona, copie este enlace: {link}
            </p>

            <p style="color: #64748b; font-size: 12px; margin-top: 24px;">
                Sus respuestas son confidenciales y contribuyen al Registro Nacional de Prótesis.<br/>
                Instituto de Cirugía Articular — Curicó, Chile
            </p>
        </div>
        """

        PERIODOS_ASUNTO = {
            "preop": "Evaluación preoperatoria",
            "3m":    "Evaluación 3 meses post cirugía",
            "6m":    "Evaluación 6 meses post cirugía",
            "1a":    "Evaluación 1 año post cirugía",
            "2a":    "Evaluación 2 años post cirugía",
        }

        resend.Emails.send({
            "from":    "Registro Prótesis ICA <registro@icarticular.cl>",
            "to":      [email],
            "subject": f"ICA Registro — {PERIODOS_ASUNTO.get(periodo, periodo)}",
            "html":    html,
        })
        return True

    except Exception as e:
        print(f"❌ Error enviando email escala {periodo} a {email}: {e}")
        return False


# ============================================================
# PROCESO PRINCIPAL
# ============================================================

def procesar_escalas_pendientes(hoy: date | None = None) -> int:
    """
    Recorre todos los pacientes y envía emails de escalas pendientes.
    Retorna número de emails enviados.
    """
    if hoy is None:
        hoy = datetime.now(CHILE_TZ).date()

    enviados = 0
    pacientes = _get_all_patients()

    print(f"📋 Procesando {len(pacientes)} pacientes para {hoy}…")

    for patient_dir in pacientes:
        admin    = _get_admin(patient_dir)
        email    = admin.get("email", "").strip()
        nombre   = f"{admin.get('nombre','')} {admin.get('apellido_paterno','')}".strip()
        rut      = admin.get("rut", patient_dir.name)

        if not email:
            continue

        surgeries = _get_surgeries(patient_dir)

        for cirugia in surgeries:
            fecha_cirugia = cirugia.get("fecha_cirugia", "")
            if not fecha_cirugia:
                continue

            dias = _dias_desde_cirugia(fecha_cirugia, hoy)
            if dias is None or dias < 0:
                continue

            tipo_protesis = cirugia.get("tipo_protesis", "")
            cirugia_id    = cirugia.get("id", "")
            surgery_path  = Path(cirugia["_path"])

            for periodo in HITOS:
                if not _debe_enviar(cirugia, periodo, dias):
                    continue

                print(f"📧 Enviando escala {periodo} a {rut} ({nombre})…")

                ok = _enviar_email_escala(
                    email=email,
                    nombre=nombre,
                    rut=rut,
                    periodo=periodo,
                    tipo_protesis=tipo_protesis,
                    fecha_cirugia=fecha_cirugia,
                )

                if ok:
                    # Marcar como enviado
                    ep = cirugia.setdefault("escalas_programadas", {}).setdefault(periodo, {})
                    ep["email_enviado"]  = True
                    ep["fecha_envio"]    = hoy.isoformat()
                    # Guardar cambio en disco
                    cirugia_data = _load_json(surgery_path)
                    cirugia_data.setdefault("escalas_programadas", {}).setdefault(periodo, {}).update({
                        "email_enviado": True,
                        "fecha_envio":   hoy.isoformat(),
                    })
                    _save_json(surgery_path, cirugia_data)
                    enviados += 1
                    print(f"✅ Email {periodo} enviado a {rut}")

    print(f"✅ {enviados} emails de escalas enviados para {hoy}")
    return enviados


# ============================================================
# LOOP DEL SCHEDULER
# ============================================================

def _loop():
    print("🕘 Scheduler registro prótesis iniciado")
    ultimo = None

    while True:
        ahora = datetime.now(CHILE_TZ)
        hoy   = ahora.date()

        # Correr a las 09:00
        if ahora.hour == 9 and ahora.minute < 5 and ultimo != hoy:
            print(f"📋 Scheduler registro prótesis — {hoy}")
            try:
                procesar_escalas_pendientes(hoy)
            except Exception as e:
                print(f"❌ Error scheduler registro: {e}")
            ultimo = hoy

        time.sleep(60)


def start_registro_scheduler():
    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    print("🚀 Scheduler registro prótesis iniciado")
