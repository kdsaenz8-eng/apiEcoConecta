"""
Punto de entrada principal de la aplicación Backend FastAPI - EcoConecta (TRL 5).
Inicializa middlewares CORS, creación de esquema en entorno de desarrollo y rutas API v1.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import Base, engine
from app.services.storage_service import STATIC_DIR


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Inicializa las tablas en el arranque si aún no existen en el entorno TRL 5."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "API RESTful asíncrona para la coordinación de recolección de residuos aprovechables "
        "en el municipio, Antioquia (Cumplimiento Ley 1581 de 2012 y Resolución 2184 de 2019)."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health", tags=["Infraestructura"])
async def health_check() -> dict:
    """Endpoint de verificación de salud para contenedores Docker y plataformas Cloud."""
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "trl_level": "TRL 5",
        "municipality": "Antioquia",
    }

