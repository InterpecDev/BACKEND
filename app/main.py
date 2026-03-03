import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routers.auth import router as auth_router
from app.routers.dashboard import router as dashboard_router
from app.routers.convocatorias import router as convocatorias_router
from app.routers.admin_users import router as admin_users_router
from app.routers.autor import router as autor_router
from app.routers import account
from app.routers.admin_books import router as admin_books_router
from app.routers.admin_chapters import router as admin_chapters_router
from app.routers.admin_dictamenes import router as admin_dictamenes_router
from app.routers.editorial_chapters import router as editorial_chapters_router
from app.routers.editorial_actions import router as editorial_actions_router

# ✅ ESTE es el que debe quedar para /api/dictaminador/chapters/*
from app.routers.dictaminador_chapters import router as dictaminador_chapters_router

from app.routers.admin_chapter_versions import router as admin_chapter_versions_router
from app.routers.admin_dictamen_documento import router as admin_dictamen_documento_router
from app.routers.admin_templates import router as admin_templates_router

import app.models  # asegura que se registren modelos

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",

        # ✅ Nota: idealmente deben ir sin /login, pero no te rompo tus dominios
        "https://frontend-6whf.vercel.app",
        "https://frontend-luz1727s-projects.vercel.app",
        "https://frontend-6whf-git-main-luz1727s-projects.vercel.app",
        "https://frontend-6whf-bnpneq3m6-luz1727s-projects.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ CARPETAS
os.makedirs("storage/convocatorias", exist_ok=True)
os.makedirs("storage/chapters", exist_ok=True)
os.makedirs("storage/dictamenes", exist_ok=True)

# ✅ ESTÁTICOS (solo uno es suficiente)
app.mount("/api/storage", StaticFiles(directory="storage"), name="storage")

# ✅ ROUTERS (todos con /api)
app.include_router(auth_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(convocatorias_router, prefix="/api")
app.include_router(admin_users_router, prefix="/api")
app.include_router(autor_router, prefix="/api")
app.include_router(account.router, prefix="/api")
app.include_router(admin_books_router, prefix="/api")
app.include_router(admin_chapters_router, prefix="/api")
app.include_router(admin_dictamenes_router, prefix="/api")
app.include_router(editorial_chapters_router, prefix="/api")
app.include_router(editorial_actions_router, prefix="/api")

# ✅ Dictaminador chapters (incluye /download-latest y /view-latest)
app.include_router(dictaminador_chapters_router, prefix="/api")

app.include_router(admin_chapter_versions_router, prefix="/api")
app.include_router(admin_dictamen_documento_router, prefix="/api")
app.include_router(admin_templates_router, prefix="/api")

# ❌ QUITADO: esto estaba duplicando rutas y causando tus 404/choques
# from app.routers import dictaminador
# app.include_router(dictaminador.router, prefix="/api")

@app.get("/api/health")
def health():
    return {"status": "ok"}