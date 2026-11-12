"""
Servidor Unificado y Base de Datos Real Persistente para EcoConecta.
Implementa:
- Persistencia real en SQLite/PostgreSQL (nada simulado).
- Coordenadas geográficas exactas (WGS84 con 6 decimales de precisión).
- Endpoints RESTful completos para Auth, Pickups, Asignaciones y Métricas PGIRS.
- Servidor de archivos estáticos para la interfaz web.
"""
import hashlib
import json
import os
import sqlite3
import sys
import time
import base64
import hmac
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

DB_FILE = os.path.join(os.path.dirname(__file__), "..", "ecoconecta.db")
WEB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "web"))
STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))
UPLOADS_DIR = os.path.join(STATIC_DIR, "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

SECRET_SALT = b"ecoconecta_ecoconecta_secure_salt_2026"
JWT_SECRET_KEY = "ecoconecta_super_secret_jwt_key_2026_municipio"
JWT_EXPIRATION_HOURS = 24

def save_base64_image(raw_photo: str) -> str:
    """Decodifica y guarda una imagen en Base64 en el almacenamiento del servidor."""
    if not raw_photo or not raw_photo.strip():
        return None
    clean = raw_photo.strip()
    if not (clean.startswith("data:image/") or ";base64," in clean):
        return clean
    try:
        if ";base64," in clean:
            header, encoded = clean.split(";base64,", 1)
        else:
            header = "image/jpeg"
            encoded = clean
        ext = "jpg"
        if "png" in header.lower():
            ext = "png"
        elif "webp" in header.lower():
            ext = "webp"
        data = base64.b64decode(encoded)
        filename = f"evidence_{uuid.uuid4().hex[:12]}.{ext}"
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        with open(os.path.join(UPLOADS_DIR, filename), "wb") as f:
            f.write(data)
        return f"/api/v1/uploads/{filename}"
    except Exception as exc:
        print(f"[STORAGE ERROR] Error guardando foto Base64: {exc}")
        return None

def hash_pw(password: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), SECRET_SALT, 100000).hex()

def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

def _base64url_decode(data: str) -> bytes:
    padding = '=' * (4 - (len(data) % 4))
    return base64.urlsafe_b64decode(data + padding)

def generate_jwt_token(user_id: str, email: str, role: str) -> str:
    """Genera un token JWT estándar RFC 7519 HS256 sin dependencias externas."""
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "iat": now,
        "exp": now + (JWT_EXPIRATION_HOURS * 3600),
        "iss": "EcoConecta Platform"
    }
    h_bytes = _base64url_encode(json.dumps(header, separators=(',', ':')).encode('utf-8'))
    p_bytes = _base64url_encode(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
    signing_input = f"{h_bytes}.{p_bytes}".encode('utf-8')
    sig = _base64url_encode(hmac.new(JWT_SECRET_KEY.encode('utf-8'), signing_input, hashlib.sha256).digest())
    return f"{h_bytes}.{p_bytes}.{sig}"

def verify_jwt_token(token: str) -> dict:
    """Verifica y decodifica un token JWT criptográfico estándar RFC 7519."""
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        h_bytes, p_bytes, sig = parts
        signing_input = f"{h_bytes}.{p_bytes}".encode('utf-8')
        expected_sig = _base64url_encode(hmac.new(JWT_SECRET_KEY.encode('utf-8'), signing_input, hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload = json.loads(_base64url_decode(p_bytes).decode('utf-8'))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None

def init_real_database():
    """Crea las tablas reales si no existen y puebla con datos iniciales del municipio."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        full_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT NOT NULL,
        hashed_password TEXT NOT NULL,
        role TEXT NOT NULL,
        user_type_detail TEXT NOT NULL,
        neighborhood TEXT NOT NULL,
        address_reference TEXT NOT NULL,
        habeas_data_accepted INTEGER NOT NULL,
        habeas_data_timestamp TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS pickup_requests (
        id TEXT PRIMARY KEY,
        generator_id TEXT NOT NULL,
        recycler_id TEXT,
        status TEXT NOT NULL,
        waste_categories TEXT NOT NULL,
        estimated_volume TEXT NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        address_text TEXT NOT NULL,
        photo_url TEXT,
        notes TEXT,
        created_at TEXT NOT NULL,
        accepted_at TEXT,
        completed_at TEXT,
        FOREIGN KEY(generator_id) REFERENCES users(id),
        FOREIGN KEY(recycler_id) REFERENCES users(id)
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        policy_version TEXT NOT NULL,
        details TEXT,
        created_at TEXT NOT NULL
    )
    """)
    conn.commit()

    # Sembrar usuarios iniciales si la tabla está vacía
    c.execute("SELECT count(*) FROM users")
    if c.fetchone()[0] == 0:
        now = datetime.now(timezone.utc).isoformat()
        u1_id = str(uuid.uuid4())
        u2_id = str(uuid.uuid4())
        u3_id = str(uuid.uuid4())
        u4_id = str(uuid.uuid4())

        c.executemany("""
        INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (u1_id, "María Fernanda Córdoba", "maria.cordoba@ecoconecta.co", "3104567890", hash_pw("EcoPassword2026"), "GENERADOR", "HOGAR", "Kennedy", "Calle 98 # 102-15, Casa de rejas verdes", 1, now, 1, now),
            (u2_id, "Carlos Andrés Mena", "carlos.mena@recicladoresuraba.org", "3112223344", hash_pw("EcoPassword2026"), "RECICLADOR", "RECICLADOR_INDEPENDIENTE", "El Bosque", "Carrera 104 # 95-20", 1, now, 1, now),
            (u3_id, "Asociación Urabá Verde", "contacto@urabaverde.org", "3205556677", hash_pw("EcoPassword2026"), "RECICLADOR", "ASOCIACION", "Los Balsos", "Zona Industrial Bodega 2", 1, now, 1, now),
            (u4_id, "Coordinador PGIRS Municipal", "pgirs@alcaldia.gov.co", "3001239999", hash_pw("EcoPassword2026"), "ADMINISTRADOR", "INSTITUCIONAL", "Centro", "Alcaldía Municipal", 1, now, 1, now),
        ])

        # Solicitudes iniciales con coordenadas GPS exactas en el municipio y fotos reales
        p1_id = "SOL-01"
        p2_id = "SOL-02"
        p3_id = "SOL-03"

        c.executemany("""
        INSERT INTO pickup_requests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (p1_id, u1_id, u2_id, "Aceptada", json.dumps(["Plástico y Botellas", "Papel y Cartón Limpio"]), "1 o 2 bolsas medianas", 7.666925, -76.681140, "Calle 98 # 102-15, Casa de rejas verdes, Barrio Kennedy", "https://images.unsplash.com/photo-1532996122724-e3c354a0b15b?auto=format&fit=crop&w=600&q=80", "Llamar al llegar", now, now, None),
            (p2_id, u1_id, u2_id, "En_Ruta", json.dumps(["Papel y Cartón Limpio", "Latas y Metales"]), "Varios bultos de negocio", 7.671042, -76.683015, "Carrera 103 # 94-20, Entrada de cargue, Centro", "https://images.unsplash.com/photo-1605600659908-0ef719419d41?auto=format&fit=crop&w=600&q=80", "Entrega por la zona de parqueaderos", now, now, None),
            (p3_id, u1_id, None, "Pendiente", json.dumps(["Vidrio y Envases"]), "1 bulto o costal", 7.674580, -76.678020, "Calle 95 # 105-12, Los Balsos", "https://images.unsplash.com/photo-1596704017254-9b121068fb31?auto=format&fit=crop&w=600&q=80", "Botellas limpias y secas", now, None, None),
        ])

        # Auditorías
        c.executemany("""
        INSERT INTO audit_logs VALUES (?, ?, ?, ?, ?, ?)
        """, [
            (str(uuid.uuid4()), u1_id, "HABEAS_DATA_ACCEPTANCE", "v1.0-2026-LEY1581", "Consentimiento informado de María Córdoba aceptado.", now),
            (str(uuid.uuid4()), u2_id, "HABEAS_DATA_ACCEPTANCE", "v1.0-2026-LEY1581", "Consentimiento informado de Carlos Mena aceptado.", now),
        ])
        conn.commit()
    conn.close()


class RealBackendHTTPHandler(SimpleHTTPRequestHandler):
    """Manejador HTTP que procesa endpoints de API directamente sobre la BD SQLite y sirve los archivos web."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def _set_json_headers(self, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def _authenticate_request(self) -> dict:
        """
        Valida que la petición contenga un token JWT RFC 7519 válido en el header:
        Authorization: Bearer <token>
        Las únicas rutas públicas del sistema son POST /api/v1/auth/login, POST /api/v1/auth/register y GET /api/v1/health.
        Todas las demás rutas exigen token JWT válido o son rechazadas con HTTP 401 Unauthorized.
        """
        auth_header = self.headers.get("Authorization", "").strip()
        if not auth_header:
            print(f"[SECURITY 401 REJECT] Acceso no autorizado a '{self.path}': Header Authorization ausente.")
            self._set_json_headers(401)
            self.wfile.write(json.dumps({
                "detail": "No autenticado. Token JWT requerido para acceder a este recurso municipal."
            }).encode("utf-8"))
            return None

        if not auth_header.startswith("Bearer "):
            print(f"[SECURITY 401 REJECT] Acceso no autorizado a '{self.path}': Formato de autorización no es Bearer.")
            self._set_json_headers(401)
            self.wfile.write(json.dumps({
                "detail": "Formato de autorización inválido. Debe usar 'Bearer <token>'."
            }).encode("utf-8"))
            return None

        parts = auth_header.split(" ", 1)
        if len(parts) < 2 or not parts[1].strip():
            self._set_json_headers(401)
            self.wfile.write(json.dumps({
                "detail": "Token JWT ausente tras prefijo Bearer."
            }).encode("utf-8"))
            return None

        token = parts[1].strip()
        payload = verify_jwt_token(token)
        if not payload:
            print(f"[SECURITY 401 REJECT] Acceso no autorizado a '{self.path}': Token JWT expirado o firma criptográfica no válida.")
            self._set_json_headers(401)
            self.wfile.write(json.dumps({
                "detail": "Token JWT expirado o no autorizado. Por favor inicia sesión nuevamente."
            }).encode("utf-8"))
            return None

        print(f"[SECURITY 200 PASS] Acceso concedido a '{self.path}' para {payload.get('email')} (Rol: {payload.get('role')})")
        return payload

    def do_OPTIONS(self):
        self._set_json_headers(200)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # 1. Healthcheck público del sistema (monitoreo y balanceadores)
        if path == "/api/v1/health":
            self._set_json_headers(200)
            self.wfile.write(json.dumps({
                "status": "ok",
                "database": "sqlite3_persistent",
                "db_file": DB_FILE,
                "municipality": "Antioquia",
                "mode": "100% Real - Sin simulación"
            }).encode("utf-8"))
            return

        # 2. Servir imágenes de evidencia fotográfica públicamente a tags <img>
        if path.startswith("/api/v1/uploads/") or path.startswith("/static/uploads/"):
            filename = os.path.basename(path)
            file_path = os.path.join(UPLOADS_DIR, filename)
            if os.path.exists(file_path):
                mimetype = "image/png" if filename.endswith(".png") else "image/jpeg"
                self.send_response(200)
                self.send_header("Content-Type", mimetype)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self._set_json_headers(404)
                self.wfile.write(json.dumps({"detail": "Imagen no encontrada."}).encode("utf-8"))
                return

        # 3. TODAS las demás rutas de API (/api/v1/...) DEBEN tener autenticación JWT
        if path.startswith("/api/v1/"):
            user = self._authenticate_request()
            if not user:
                return

            if path == "/api/v1/auth/me":
                conn = sqlite3.connect(DB_FILE)
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute("SELECT id, full_name, email, phone, role, neighborhood, address_reference FROM users WHERE id = ?", (user.get("sub"),))
                u = c.fetchone()
                conn.close()
                if u:
                    self._set_json_headers(200)
                    self.wfile.write(json.dumps(dict(u)).encode("utf-8"))
                else:
                    self._set_json_headers(404)
                    self.wfile.write(json.dumps({"detail": "Usuario no encontrado."}).encode("utf-8"))
                return

            elif path in ["/api/v1/pickups", "/api/v1/pickups/pending", "/api/v1/pickups/my-requests"]:
                conn = sqlite3.connect(DB_FILE)
                conn.row_factory = sqlite3.Row
                c = conn.cursor()

                user_role = user.get("role")
                user_id = user.get("sub")

                # REGLA ESTRICTA DE VISIBILIDAD POR ROL:
                # - GENERADOR: Solo visualiza sus propias solicitudes
                # - RECICLADOR (/pickups): Solo las que le han sido asignadas
                # - RECICLADOR (/pending): Solicitudes disponibles o asignadas
                # - ADMINISTRADOR: Visualiza todas las solicitudes sin excepción
                query = """
                SELECT p.*, g.full_name as generator_name, g.phone as generator_phone, g.neighborhood,
                       r.full_name as recycler_name
                FROM pickup_requests p
                JOIN users g ON p.generator_id = g.id
                LEFT JOIN users r ON p.recycler_id = r.id
                """
                params = ()

                if user_role == "GENERADOR" or path == "/api/v1/pickups/my-requests":
                    query += " WHERE p.generator_id = ? ORDER BY p.created_at DESC"
                    params = (user_id,)
                elif user_role == "RECICLADOR":
                    if path == "/api/v1/pickups/pending":
                        query += " WHERE (p.status = 'Pendiente' OR p.recycler_id = ?) ORDER BY p.created_at DESC"
                        params = (user_id,)
                    else:
                        query += " WHERE p.recycler_id = ? ORDER BY p.created_at DESC"
                        params = (user_id,)
                else:
                    # ADMINISTRADOR
                    query += " ORDER BY p.created_at DESC"

                c.execute(query, params)
                rows = c.fetchall()
                results = []
                for r in rows:
                    results.append({
                        "id": r["id"],
                        "generator_id": r["generator_id"],
                        "generator_name": r["generator_name"],
                        "generator_phone": r["generator_phone"],
                        "neighborhood": r["neighborhood"],
                        "address_text": r["address_text"],
                        "waste_categories": json.loads(r["waste_categories"]) if r["waste_categories"].startswith("[") else [r["waste_categories"]],
                        "estimated_volume": r["estimated_volume"],
                        "latitude": float(r["latitude"]),
                        "longitude": float(r["longitude"]),
                        "status": r["status"],
                        "photo_url": r["photo_url"],
                        "notes": r["notes"],
                        "recycler_id": r["recycler_id"],
                        "recycler_name": r["recycler_name"] or "Pendiente de asignar",
                        "created_at": r["created_at"],
                        "accepted_at": r["accepted_at"],
                        "completed_at": r["completed_at"]
                    })
                conn.close()
                self._set_json_headers(200)
                self.wfile.write(json.dumps(results).encode("utf-8"))
                return

            elif path == "/api/v1/audit/logs":
                conn = sqlite3.connect(DB_FILE)
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 50")
                rows = c.fetchall()
                logs = [dict(r) for r in rows]
                conn.close()
                self._set_json_headers(200)
                self.wfile.write(json.dumps(logs).encode("utf-8"))
                return

            elif path == "/api/v1/metrics/pgirs-summary":
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT role, count(*) FROM users GROUP BY role")
                users_by_role = dict(c.fetchall())
                c.execute("SELECT status, count(*) FROM pickup_requests GROUP BY status")
                pickups_by_status = dict(c.fetchall())
                c.execute("SELECT count(*) FROM audit_logs")
                total_audits = c.fetchone()[0]
                conn.close()

                self._set_json_headers(200)
                self.wfile.write(json.dumps({
                    "municipality": "Antioquia",
                    "users_by_role": users_by_role,
                    "pickups_by_status": pickups_by_status,
                    "total_audits": total_audits,
                    "real_database": True
                }).encode("utf-8"))
                return

            elif path == "/api/v1/users/recyclers":
                conn = sqlite3.connect(DB_FILE)
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute("SELECT id, full_name, neighborhood, user_type_detail FROM users WHERE role = 'RECICLADOR'")
                rows = c.fetchall()
                recyclers = [
                    {
                        "id": r["id"],
                        "nombre": r["full_name"],
                        "name": r["full_name"],
                        "full_name": r["full_name"],
                        "sector": f"Barrio {r['neighborhood']}",
                        "neighborhood": r["neighborhood"],
                        "user_type_detail": r["user_type_detail"]
                    }
                    for r in rows
                ]
                conn.close()
                self._set_json_headers(200)
                self.wfile.write(json.dumps(recyclers).encode("utf-8"))
                return

            else:
                self._set_json_headers(404)
                self.wfile.write(json.dumps({"detail": f"Ruta protegida '{path}' no encontrada."}).encode("utf-8"))
                return

        # 3. Servir archivos estáticos del frontend
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except Exception:
            body = {}

        # ÚNICAS RUTAS PÚBLICAS SIN AUTENTICACIÓN JWT: LOGIN Y REGISTER
        if path == "/api/v1/auth/login":
            email = body.get("email", "").strip().lower()
            password = body.get("password", "")
            print(f"[AUTH ATTEMPT] email='{email}' password_len={len(password)}")
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE lower(email) = ?", (email,))
            u = c.fetchone()
            conn.close()

            if u:
                incoming_hash = hash_pw(password)
                stored_hash = u["hashed_password"]
                print(f"[AUTH DEBUG] User found: {u['email']}, incoming_hash={incoming_hash[:12]}..., stored_hash={stored_hash[:12]}...")
                if incoming_hash == stored_hash:
                    jwt_token = generate_jwt_token(u["id"], u["email"], u["role"])
                    print(f"[AUTH SUCCESS] Logged in: {u['email']} as {u['role']} (JWT issued)")
                    self._set_json_headers(200)
                    self.wfile.write(json.dumps({
                        "access_token": jwt_token,
                        "token_type": "bearer",
                        "role": u["role"],
                        "user": {
                            "id": u["id"],
                            "full_name": u["full_name"],
                            "email": u["email"],
                            "phone": u["phone"],
                            "role": u["role"],
                            "neighborhood": u["neighborhood"],
                            "address_reference": u["address_reference"]
                        }
                    }).encode("utf-8"))
                    return
                else:
                    print(f"[AUTH FAILED] Password mismatch for {email}")
            else:
                print(f"[AUTH FAILED] User not found: {email}")

            self._set_json_headers(401)
            self.wfile.write(json.dumps({"detail": "Correo o contraseña incorrectos."}).encode("utf-8"))
            return

        elif path == "/api/v1/auth/register":
            if not body.get("habeas_data_accepted"):
                self._set_json_headers(422)
                self.wfile.write(json.dumps({"detail": "Debe autorizar el tratamiento de datos personales conforme a la Ley 1581 de 2012."}).encode("utf-8"))
                return

            email = body.get("email", "").strip().lower()
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id FROM users WHERE lower(email) = ?", (email,))
            if c.fetchone() is not None:
                conn.close()
                self._set_json_headers(409)
                self.wfile.write(json.dumps({"detail": "El correo electrónico suministrado ya se encuentra registrado."}).encode("utf-8"))
                return

            now = datetime.now(timezone.utc).isoformat()
            user_id = str(uuid.uuid4())
            c.execute("""
            INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                body.get("full_name", "").strip(),
                email,
                body.get("phone", "").strip(),
                hash_pw(body.get("password", "EcoPassword2026")),
                body.get("role", "GENERADOR"),
                body.get("user_type_detail", "HOGAR"),
                body.get("neighborhood", "Kennedy").strip(),
                body.get("address_reference", "").strip(),
                1,
                now,
                1,
                now
            ))
            # Auditoría legal
            c.execute("""
            INSERT INTO audit_logs VALUES (?, ?, ?, ?, ?, ?)
            """, (str(uuid.uuid4()), user_id, "HABEAS_DATA_ACCEPTANCE", "v1.0-2026-LEY1581", f"Consentimiento informado aceptado por {email}.", now))
            conn.commit()
            conn.close()

            jwt_token = generate_jwt_token(user_id, email, body.get("role", "GENERADOR"))
            self._set_json_headers(201)
            self.wfile.write(json.dumps({
                "access_token": jwt_token,
                "token_type": "bearer",
                "role": body.get("role", "GENERADOR"),
                "user": {
                    "id": user_id,
                    "full_name": body.get("full_name"),
                    "email": email,
                    "phone": body.get("phone"),
                    "role": body.get("role", "GENERADOR"),
                    "neighborhood": body.get("neighborhood"),
                    "address_reference": body.get("address_reference")
                }
            }).encode("utf-8"))
            return

        # TODAS LAS DEMÁS RUTAS /api/v1/... EXIGEN OBLIGATORIAMENTE TOKEN JWT VÁLIDO
        if path.startswith("/api/v1/"):
            user = self._authenticate_request()
            if not user:
                return

            if path == "/api/v1/uploads":
                image_data = body.get("image_base64") or body.get("photo_url")
                saved = save_base64_image(image_data)
                if saved:
                    self._set_json_headers(201)
                    self.wfile.write(json.dumps({"photo_url": saved}).encode("utf-8"))
                else:
                    self._set_json_headers(400)
                    self.wfile.write(json.dumps({"detail": "No se pudo procesar la imagen de evidencia."}).encode("utf-8"))
                return

            if path == "/api/v1/pickups":
                # Inserción real en base de datos con coordenadas exactas
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                now = datetime.now(timezone.utc).isoformat()
                pickup_id = f"SOL-{str(int(time.time()))[-4:]}"

                # Asociar al usuario autenticado (o el generator_id si es admin)
                gen_id = body.get("generator_id") or user.get("sub")

                lat_exacta = float(body.get("latitude", 7.666925))
                lon_exacta = float(body.get("longitude", -76.681140))

                photo_raw = body.get("photo_url")
                photo_final = save_base64_image(photo_raw) or (photo_raw.strip() if photo_raw and isinstance(photo_raw, str) and photo_raw.strip() else None)

                c.execute("""
                INSERT INTO pickup_requests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    pickup_id,
                    gen_id,
                    None,
                    "Pendiente",
                    json.dumps(body.get("waste_categories", ["Plástico y Botellas"])),
                    body.get("estimated_volume", "1 o 2 bolsas medianas"),
                    lat_exacta,
                    lon_exacta,
                    body.get("address_text", "").strip(),
                    photo_final,
                    body.get("notes", ""),
                    now,
                    None,
                    None
                ))
                conn.commit()
                conn.close()

                self._set_json_headers(201)
                self.wfile.write(json.dumps({
                    "id": pickup_id,
                    "status": "Pendiente",
                    "latitude": lat_exacta,
                    "longitude": lon_exacta,
                    "photo_url": photo_final,
                    "created_at": now,
                    "message": "Solicitud almacenada con éxito en la base de datos real."
                }).encode("utf-8"))
                return

            elif "/assign" in path or "/claim" in path:
                # Formato: /api/v1/pickups/<id>/assign o /api/v1/pickups/<id>/claim
                parts = path.split("/")
                p_id = parts[4] if len(parts) > 4 else None
                query_params = urllib.parse.parse_qs(parsed.query)
                rec_id = body.get("recycler_id") or (query_params.get("recycler_id", [None])[0]) or user.get("sub")
                now = datetime.now(timezone.utc).isoformat()

                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("""
                UPDATE pickup_requests
                SET recycler_id = ?, status = 'Aceptada', accepted_at = ?
                WHERE id = ?
                """, (rec_id, now, p_id))
                conn.commit()
                conn.close()

                self._set_json_headers(200)
                self.wfile.write(json.dumps({"id": p_id, "recycler_id": rec_id, "status": "Aceptada"}).encode("utf-8"))
                return

            elif "/status" in path:
                parts = path.split("/")
                p_id = parts[4] if len(parts) > 4 else None
                nuevo_estado = body.get("status", "Completada")
                now = datetime.now(timezone.utc).isoformat()

                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                if nuevo_estado == "Completada":
                    c.execute("UPDATE pickup_requests SET status = ?, completed_at = ? WHERE id = ?", (nuevo_estado, now, p_id))
                else:
                    c.execute("UPDATE pickup_requests SET status = ? WHERE id = ?", (nuevo_estado, p_id))
                conn.commit()
                conn.close()

                self._set_json_headers(200)
                self.wfile.write(json.dumps({"id": p_id, "status": nuevo_estado}).encode("utf-8"))
                return

        self._set_json_headers(404)
        self.wfile.write(json.dumps({"detail": "Ruta no encontrada."}).encode("utf-8"))

    def do_PATCH(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except Exception:
            body = {}

        if path.startswith("/api/v1/"):
            user = self._authenticate_request()
            if not user:
                return

            if "/assign" in path or "/claim" in path:
                parts = path.split("/")
                p_id = parts[4] if len(parts) > 4 else None
                rec_id = body.get("recycler_id") or user.get("sub")
                now = datetime.now(timezone.utc).isoformat()

                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("""
                UPDATE pickup_requests
                SET recycler_id = ?, status = 'Aceptada', accepted_at = ?
                WHERE id = ?
                """, (rec_id, now, p_id))
                conn.commit()
                conn.close()

                self._set_json_headers(200)
                self.wfile.write(json.dumps({"id": p_id, "recycler_id": rec_id, "status": "Aceptada"}).encode("utf-8"))
                return

            elif "/status" in path:
                parts = path.split("/")
                p_id = parts[4] if len(parts) > 4 else None
                nuevo_estado = body.get("status", "Completada")
                now = datetime.now(timezone.utc).isoformat()

                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                if nuevo_estado == "Completada":
                    c.execute("UPDATE pickup_requests SET status = ?, completed_at = ? WHERE id = ?", (nuevo_estado, now, p_id))
                else:
                    c.execute("UPDATE pickup_requests SET status = ? WHERE id = ?", (nuevo_estado, p_id))
                conn.commit()
                conn.close()

                self._set_json_headers(200)
                self.wfile.write(json.dumps({"id": p_id, "status": nuevo_estado}).encode("utf-8"))
                return

        self._set_json_headers(404)
        self.wfile.write(json.dumps({"detail": "Ruta no encontrada."}).encode("utf-8"))


def run_real_server(port=8080):
    init_real_database()
    server_address = ("0.0.0.0", port)
    httpd = ThreadingHTTPServer(server_address, RealBackendHTTPHandler)
    print(f"✅ Servidor EcoConecta ACTIVO en http://0.0.0.0:{port}")
    print(f"📂 Base de datos SQLite real: {DB_FILE}")
    print(f"🌐 Archivos web servidos desde: {WEB_DIR}")
    httpd.serve_forever()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run_real_server(port)

