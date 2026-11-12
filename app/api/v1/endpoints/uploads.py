"""
Endpoints para Almacenamiento y Recuperación de Evidencias Fotográficas (app/api/v1/endpoints/uploads.py).
Permite:
- GET /uploads/{filename}: Servir imágenes guardadas con Content-Type correspondiente.
- POST /uploads: Subir archivos de imagen o recibir Base64 y guardarlos persistentemente.
"""
import os
import uuid
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.services.storage_service import UPLOADS_DIR, StorageService

router = APIRouter(prefix="/uploads", tags=["Archivos y Evidencias"])


class Base64UploadRequest(BaseModel):
    image_base64: str


@router.get("/{filename}", summary="Obtener imagen de evidencia")
async def get_uploaded_image(filename: str):
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(UPLOADS_DIR, safe_filename)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Imagen de evidencia no encontrada en el servidor.",
        )
    mimetype = "image/png" if safe_filename.endswith(".png") else "image/jpeg"
    return FileResponse(file_path, media_type=mimetype)


@router.post("", summary="Subir imagen de evidencia fotográfica")
async def upload_image_file(file: UploadFile = File(...)):
    filename = file.filename or "evidence.jpg"
    ext = filename.split(".")[-1].lower() if "." in filename else "jpg"
    unique_name = f"evidence_{uuid.uuid4().hex[:12]}.{ext}"
    dest_path = os.path.join(UPLOADS_DIR, unique_name)

    content = await file.read()
    with open(dest_path, "wb") as f:
        f.write(content)

    return {"photo_url": f"/api/v1/uploads/{unique_name}"}


@router.post("/base64", summary="Guardar imagen Base64 de evidencia")
async def upload_base64_image(payload: Base64UploadRequest):
    saved_url = StorageService.save_base64_image(payload.image_base64)
    if not saved_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo procesar la imagen en Base64.",
        )
    return {"photo_url": saved_url}
