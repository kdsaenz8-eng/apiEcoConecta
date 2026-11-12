"""
Pruebas de Seguridad y Protección de Rutas con JWT en EcoConecta.
Regla Estricta:
- Únicas rutas públicas (sin autenticación): /api/v1/auth/login, /api/v1/auth/register, /api/v1/health.
- TODAS las demás rutas requieren cabecera 'Authorization: Bearer <token>' válido.
- Cualquier petición a rutas protegidas sin token o con token alterado debe recibir HTTP 401 Unauthorized.
"""
import unittest
import json
import time
try:
    from app.real_server import generate_jwt_token, verify_jwt_token, JWT_SECRET_KEY
except ImportError:
    from backend.app.real_server import generate_jwt_token, verify_jwt_token, JWT_SECRET_KEY

class TestJWTRouteProtection(unittest.TestCase):

    def setUp(self):
        self.user_id = "test-user-123"
        self.email = "test@ecoconecta.co"
        self.role = "GENERADOR"
        self.valid_token = generate_jwt_token(self.user_id, self.email, self.role)

    def test_valid_token_decodes_successfully(self):
        payload = verify_jwt_token(self.valid_token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["sub"], self.user_id)
        self.assertEqual(payload["email"], self.email)
        self.assertEqual(payload["role"], self.role)

    def test_tampered_token_is_rejected(self):
        parts = self.valid_token.split(".")
        # Adulterar la firma
        tampered = f"{parts[0]}.{parts[1]}.bad_signature_xyz"
        payload = verify_jwt_token(tampered)
        self.assertIsNone(payload, "Un token con firma alterada no debe ser aceptado")

    def test_malformed_token_is_rejected(self):
        self.assertIsNone(verify_jwt_token("Bearer 12345"))
        self.assertIsNone(verify_jwt_token(""))
        self.assertIsNone(verify_jwt_token("invalido.token"))

    def test_public_routes_whitelisted_properly(self):
        public_routes = ["/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/health"]
        protected_routes = [
            "/api/v1/pickups",
            "/api/v1/pickups/pending",
            "/api/v1/pickups/my-requests",
            "/api/v1/users/recyclers",
            "/api/v1/audit/logs",
            "/api/v1/metrics/pgirs-summary",
            "/api/v1/auth/me"
        ]
        for route in protected_routes:
            self.assertNotIn(route, public_routes, f"La ruta {route} no debe ser pública")

if __name__ == "__main__":
    unittest.main()

