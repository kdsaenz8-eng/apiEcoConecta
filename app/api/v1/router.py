"""Enrutador principal de la versión 1 de la API EcoConecta."""
from fastapi import APIRouter

from app.api.v1.endpoints import auth, metrics, pickups, uploads, users, ws

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(pickups.router)
api_router.include_router(uploads.router)
api_router.include_router(metrics.router)
api_router.include_router(users.router)
api_router.include_router(ws.router)
