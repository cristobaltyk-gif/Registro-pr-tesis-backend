"""
main.py — Backend Registro Nacional de Prótesis
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

# ============================================================
# INICIALIZACIÓN DE DIRECTORIOS
# ============================================================

def _resolve_data_path() -> Path:
    """
    Intenta usar /data (disco Render).
    Fallback a ./data local si no hay permisos.
    """
    candidate = Path(os.getenv("DATA_PATH", "/data"))
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        # Verificar escritura
        test = candidate / ".write_test"
        test.touch()
        test.unlink()
        return candidate
    except PermissionError:
        fallback = Path("./data")
        fallback.mkdir(parents=True, exist_ok=True)
        print(f"⚠️  /data sin permisos → usando {fallback.resolve()}")
        return fallback

DATA_PATH = _resolve_data_path()
os.environ["DATA_PATH"] = str(DATA_PATH)

def init_dirs():
    dirs = [
        DATA_PATH / "registro_protesis" / "patients",
        DATA_PATH / "registro_protesis",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    print(f"✅ Directorios inicializados en {DATA_PATH}")

init_dirs()

# ============================================================
# SCHEDULER
# ============================================================
from modules.registro_scheduler import start_registro_scheduler
start_registro_scheduler()

# ============================================================
# ROUTERS
# ============================================================
from routers.registro_admin   import router as admin_router
from routers.registro_auth    import router as auth_router
from routers.registro_cirugia import router as cirugia_router
from routers.registro_escalas import router as escalas_router

# ============================================================
# APP
# ============================================================
app = FastAPI(
    title="Registro Nacional de Prótesis — ICA",
    version="1.0",
)

# ============================================================
# CORS
# ============================================================
FRONTEND_URLS   = os.getenv("FRONTEND_URLS", "https://registro.icarticular.cl")
allowed_origins = [u.strip() for u in FRONTEND_URLS.split(",") if u.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# REGISTRAR ROUTERS
# ============================================================
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(cirugia_router)
app.include_router(escalas_router)

# ============================================================
# HEALTHCHECK
# ============================================================
@app.get("/")
def root():
    return {
        "status":  "ok",
        "service": "Registro Nacional de Prótesis",
        "version": "1.0",
        "data_path": str(DATA_PATH),
    }
    
