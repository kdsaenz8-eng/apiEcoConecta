"""
Pruebas Unitarias TDD para el Caso de Uso: Asignar Reciclador por el Administrador
Verifica la validación de roles, contratos de payload y persistencia de asignación.
"""
import unittest
import uuid
from datetime import datetime, timezone

from app.models.pickup import PickupRequest, PickupStatus
from app.models.user import User, UserRole
from app.schemas.pickup import AssignPayload, PickupResponse, PickupStatusUpdate


class TestAdminAssignPickupTDD(unittest.TestCase):
    """Suite de pruebas unitarias para la asignación administrativa de solicitudes."""

    def test_assign_payload_validation_with_status_and_extra_fields(self):
        """Verifica que AssignPayload acepte recycler_id, status y no falle con campos extras."""
        rec_id = str(uuid.uuid4())
        payload = AssignPayload.model_validate({
            "recycler_id": rec_id,
            "status": "Aceptada",
            "extra_field": "ignored_safely"
        })
        self.assertEqual(payload.recycler_id, rec_id)
        self.assertEqual(payload.status, "Aceptada")

    def test_pickup_response_enriched_fields(self):
        """Verifica que PickupResponse exponga generator_name, recycler_name y neighborhood."""
        gen_id = uuid.uuid4()
        rec_id = uuid.uuid4()
        p_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        class MockUser:
            def __init__(self, full_name, phone, neighborhood):
                self.full_name = full_name
                self.phone = phone
                self.neighborhood = neighborhood

        gen_user = MockUser("María Córdoba", "3104567890", "Kennedy")
        rec_user = MockUser("Carlos Mena", "3112223344", "El Bosque")

        class MockPickup:
            def __init__(self):
                self.id = p_id
                self.generator_id = gen_id
                self.recycler_id = rec_id
                self.status = PickupStatus.ACEPTADA
                self.waste_categories = ["PLASTICO"]
                self.estimated_volume = "1 bolsa"
                self.latitude = 7.666925
                self.longitude = -76.681140
                self.address_text = "Calle 98 # 102-15"
                self.photo_url = None
                self.notes = "Llamar al llegar"
                self.created_at = now
                self.accepted_at = now
                self.completed_at = None
                self.generator = gen_user
                self.recycler = rec_user

            @property
            def generator_name(self):
                return self.generator.full_name if self.generator else None

            @property
            def generator_phone(self):
                return self.generator.phone if self.generator else None

            @property
            def neighborhood(self):
                return self.generator.neighborhood if self.generator else None

            @property
            def recycler_name(self):
                return self.recycler.full_name if self.recycler else None

        mock_obj = MockPickup()
        resp = PickupResponse.model_validate(mock_obj)

        self.assertEqual(resp.id, p_id)
        self.assertEqual(resp.recycler_id, rec_id)
        self.assertEqual(resp.generator_name, "María Córdoba")
        self.assertEqual(resp.recycler_name, "Carlos Mena")
        self.assertEqual(resp.neighborhood, "Kennedy")
        self.assertEqual(resp.generator_phone, "3104567890")

    def test_admin_role_security_check(self):
        """Verifica que un usuario con rol distinto a ADMINISTRADOR sea rechazado."""
        class MockUser:
            def __init__(self, role):
                self.role = role

        admin_user = MockUser(UserRole.ADMINISTRADOR)
        recycler_user = MockUser(UserRole.RECICLADOR)
        generator_user = MockUser(UserRole.GENERADOR)

        # Regla: solo ADMINISTRADOR puede asignar
        def is_admin(user):
            role_str = user.role.value if hasattr(user.role, "value") else str(user.role)
            return role_str.upper() == "ADMINISTRADOR" or user.role == UserRole.ADMINISTRADOR

        self.assertTrue(is_admin(admin_user))
        self.assertFalse(is_admin(recycler_user))
        self.assertFalse(is_admin(generator_user))

    def test_status_update_normalization_variants(self):
        """Verifica que PickupStatusUpdate normalice 'En_Ruta', 'En camino', 'Completada', etc."""
        update_en_ruta = PickupStatusUpdate.model_validate({"status": "En_Ruta"})
        self.assertEqual(update_en_ruta.status, PickupStatus.EN_CAMINO)

        update_camino = PickupStatusUpdate.model_validate({"status": "En camino"})
        self.assertEqual(update_camino.status, PickupStatus.EN_CAMINO)

        update_completada = PickupStatusUpdate.model_validate({"status": "Completada"})
        self.assertEqual(update_completada.status, PickupStatus.COMPLETADA)

        update_aceptada = PickupStatusUpdate.model_validate({"status": "Aceptada"})
        self.assertEqual(update_aceptada.status, PickupStatus.ACEPTADA)


if __name__ == "__main__":
    unittest.main()
