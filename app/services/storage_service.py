"""
Servicio de Almacenamiento y Persistencia de Archivos y Reglas de Visibilidad por Rol (app/services/storage_service.py).
Maneja la recepción, decodificación y guardado en disco de evidencias fotográficas reales
y la aplicación estricta de políticas de acceso por rol (Generador, Reciclador y Administrador).
"""
import base64
import logging
import os
import uuid
from typing import Any, Dict, Optional
from uuid import UUID

from app.models.user import UserRole

logger = logging.getLogger(__name__)

# Directorio físico donde se almacenan las fotos de residuos
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOADS_DIR = os.path.join(STATIC_DIR, "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)


class StorageService:
    @staticmethod
    def save_base64_image(raw_photo: Optional[str]) -> Optional[str]:
        """
        Decodifica y guarda una imagen en Base64 en el sistema de archivos del servidor.
        Si la entrada es una URL remota existente, la conserva sin alterarla.
        Retorna la ruta relativa segura '/api/v1/uploads/{filename}' lista para guardarse en BD.
        """
        if not raw_photo or not raw_photo.strip():
            return None

        clean_photo = raw_photo.strip()

        # Si ya es una URL HTTP/HTTPS o una ruta local servida
        if not (clean_photo.startswith("data:image/") or ";base64," in clean_photo):
            return clean_photo

        try:
            if ";base64," in clean_photo:
                header, encoded_data = clean_photo.split(";base64,", 1)
            else:
                header = "image/jpeg"
                encoded_data = clean_photo

            # Determinar extensión del archivo
            ext = "jpg"
            if "png" in header.lower():
                ext = "png"
            elif "webp" in header.lower():
                ext = "webp"
            elif "gif" in header.lower():
                ext = "gif"

            # Decodificar bytes binarios
            binary_data = base64.b64decode(encoded_data)
            unique_name = f"evidence_{uuid.uuid4().hex[:12]}.{ext}"

            os.makedirs(UPLOADS_DIR, exist_ok=True)
            destination_path = os.path.join(UPLOADS_DIR, unique_name)

            with open(destination_path, "wb") as f:
                f.write(binary_data)

            logger.info("Foto real guardada exitosamente en disco: %s (%d bytes)", destination_path, len(binary_data))
            return f"/api/v1/uploads/{unique_name}"
        except Exception as exc:
            logger.error("Error al procesar y guardar la imagen Base64: %s", exc)
            return None

    @staticmethod
    def get_pickups_filter_for_role(role: Any, user_id: Any) -> Optional[Dict[str, Any]]:
        """
        Aplica la regla de dominio solicitada:
        - GENERADOR: Solo visualiza las solicitudes creadas por él.
        - RECICLADOR: Solo visualiza las solicitudes que se le asignaron.
        - ADMINISTRADOR: Visualiza todas las solicitudes del sistema sin filtro.
        """
        role_str = role.value if hasattr(role, "value") else str(role)

        if role_str == UserRole.GENERADOR.value or role_str == "GENERADOR":
            return {"field": "generator_id", "value": user_id}
        elif role_str == UserRole.RECICLADOR.value or role_str == "RECICLADOR":
            return {"field": "recycler_id", "value": user_id}
        elif role_str == UserRole.ADMINISTRADOR.value or role_str == "ADMINISTRADOR":
            return None
        return {"field": "generator_id", "value": user_id}
