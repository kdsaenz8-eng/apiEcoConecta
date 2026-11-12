"""
Pruebas Unitarias TDD para:
1. Servicio de Almacenamiento y Persistencia Real de Imágenes (StorageService).
2. Validación de esquemas con fotos de evidencia en Base64 sin error 422.
3. Lógica de visibilidad y permisos según rol (Generador, Reciclador y Administrador).
"""
import base64
import os
import unittest
from uuid import uuid4

from app.models.user import UserRole
from app.schemas.pickup import PickupCreate
from app.services.storage_service import StorageService, UPLOADS_DIR


class TestStorageAndRoleAccess(unittest.TestCase):
    def setUp(self):
        os.makedirs(UPLOADS_DIR, exist_ok=True)

    def test_save_base64_image_creates_file_and_returns_url(self):
        # Pixel PNG 1x1 válido en Base64
        dummy_png_base64 = (
            "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )
        saved_url = StorageService.save_base64_image(dummy_png_base64)
        self.assertIsNotNone(saved_url)
        self.assertTrue(saved_url.startswith("/api/v1/uploads/"))
        self.assertTrue(saved_url.endswith(".png"))

        # Verificar que el archivo realmente existe en el disco del backend
        filename = os.path.basename(saved_url)
        full_path = os.path.join(UPLOADS_DIR, filename)
        self.assertTrue(os.path.exists(full_path))
        self.assertGreater(os.path.getsize(full_path), 0)

        # Limpieza
        if os.path.exists(full_path):
            os.remove(full_path)

    def test_save_base64_image_preserves_regular_urls(self):
        remote_url = "https://storage.ecoconecta.co/evidencias/reciclaje_bolsa_blanca.jpg"
        self.assertEqual(StorageService.save_base64_image(remote_url), remote_url)

    def test_save_base64_image_handles_none_and_empty(self):
        self.assertIsNone(StorageService.save_base64_image(None))
        self.assertIsNone(StorageService.save_base64_image(""))
        self.assertIsNone(StorageService.save_base64_image("   "))

    def test_pickup_create_accepts_large_base64_photo(self):
        # Simular imagen capturada desde cámara móvil (> 20.000 caracteres)
        large_base64 = "data:image/jpeg;base64," + ("B" * 25000)
        payload = PickupCreate(
            generator_id=str(uuid4()),
            waste_categories=["PLASTICO"],
            estimated_volume="1 o 2 bolsas medianas",
            latitude=7.666925,
            longitude=-76.681140,
            address_text="Calle 98 # 102-15, Barrio Kennedy",
            photo_url=large_base64,
        )
        self.assertEqual(payload.photo_url, large_base64)

    def test_role_filtering_conditions(self):
        # Verifica la lógica de asignación y filtrado por rol
        generator_id = uuid4()
        recycler_id = uuid4()

        # Generador solo ve sus propios registros
        gen_filter = StorageService.get_pickups_filter_for_role(
            role=UserRole.GENERADOR,
            user_id=generator_id,
        )
        self.assertEqual(gen_filter["field"], "generator_id")
        self.assertEqual(gen_filter["value"], generator_id)

        # Reciclador solo ve los registros asignados a él
        rec_filter = StorageService.get_pickups_filter_for_role(
            role=UserRole.RECICLADOR,
            user_id=recycler_id,
        )
        self.assertEqual(rec_filter["field"], "recycler_id")
        self.assertEqual(rec_filter["value"], recycler_id)

        # Administrador ve todo (sin filtro)
        admin_filter = StorageService.get_pickups_filter_for_role(
            role=UserRole.ADMINISTRADOR,
            user_id=uuid4(),
        )
        self.assertIsNone(admin_filter)


if __name__ == "__main__":
    unittest.main()
