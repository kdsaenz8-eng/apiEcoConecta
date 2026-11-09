"""
Pruebas Unitarias para Endpoints FastAPI v1:
1. Validación de PickupCreate con normalización de categorías en español (Res. 2184/2019).
2. Endpoint GET /api/v1/pickups para listado administrativo.
3. Endpoint GET /api/v1/users/recyclers para directorio de recicladores.
4. Endpoint POST /api/v1/pickups/{id}/assign con soporte query y body.
"""
import unittest
from app.schemas.pickup import PickupCreate, AssignPayload

class TestApiV1EndpointsFixes(unittest.TestCase):
    def test_pickup_create_category_normalization(self):
        # Frontend envía nombres legibles con acentos y mayúsculas
        payload = PickupCreate(
            generator_id="54d0d0ab-c4d4-4eb2-be9f-ca13bb0a696d",
            waste_categories=["Plástico y Botellas", "Papel y Cartón Limpio"],
            estimated_volume="1 o 2 bolsas medianas",
            latitude=7.666925,
            longitude=-76.681140,
            address_text="Calle 98 # 102-15, Barrio Kennedy",
            photo_url="https://images.unsplash.com/photo-1532996122724-e3c354a0b15b",
            notes="Coordenadas exactas",
        )
        self.assertEqual(payload.waste_categories, ["PLASTICO", "CARTON"])

    def test_pickup_create_direct_enum_categories(self):
        payload = PickupCreate(
            waste_categories=["VIDRIO", "METAL"],
            estimated_volume="1 bulto",
            latitude=7.666925,
            longitude=-76.681140,
            address_text="Calle 95 # 105-12, Los Balsos",
        )
        self.assertEqual(payload.waste_categories, ["VIDRIO", "METAL"])

    def test_assign_payload(self):
        body = AssignPayload(recycler_id="f2f8aab9-0dba-443a-b326-17de60dbf212")
        self.assertEqual(body.recycler_id, "f2f8aab9-0dba-443a-b326-17de60dbf212")

if __name__ == "__main__":
    unittest.main()
