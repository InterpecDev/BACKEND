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
from app.routers.dictaminador_chapters import router as dictaminador_chapters_router
from app.routers.admin_chapter_versions import router as admin_chapter_versions_router
from app.routers.admin_dictamen_documento import router as admin_dictamen_documento_router

import app.models

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
allow_origins=[
    "http://localhost:5173", 
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://192.168.1.152:5174",  
    "http://192.168.1.76:8080",    
    "http://192.168.1.152:5173",  
],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ CARPETAS
os.makedirs("storage/convocatorias", exist_ok=True)

# ✅ ESTÁTICOS
app.mount("/api/storage", StaticFiles(directory="storage"), name="storage")
app.mount("/api/api/storage", StaticFiles(directory="storage"), name="storage_alias")

# ✅ ROUTERS
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
app.include_router(dictaminador_chapters_router, prefix="/api")
app.include_router(admin_chapter_versions_router, prefix="/api")
app.include_router(admin_dictamen_documento_router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}