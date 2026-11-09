"""
Módulo de Seguridad: Hashing criptográfico de contraseñas (Bcrypt / Passlib)
y emisión/verificación de tokens JWT con python-jose.
"""
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_SALT = b"ecoconecta_ecoconecta_secure_salt_2026"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifica si una contraseña en texto plano coincide con su hash almacenado.
    Soporta:
    1. PBKDF2-HMAC-SHA256 (64 hex chars - formato de la base de datos municipal de usuarios).
    2. Bcrypt (Passlib $2b$ / $2a$).
    3. Manejo seguro de excepciones para evitar errores HTTP 500.
    """
    if not plain_password or not hashed_password:
        return False

    # 1. Verificación PBKDF2-HMAC-SHA256 estándar
    if len(hashed_password) == 64 and not hashed_password.startswith("$"):
        try:
            expected = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), SECRET_SALT, 100000).hex()
            if hmac.compare_digest(expected, hashed_password):
                return True
        except Exception:
            pass

    # 2. Verificación Bcrypt vía Passlib con protección contra UnknownHashError
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Genera el hash Bcrypt seguro para una contraseña."""
    return pwd_context.hash(password)


def create_access_token(
    subject: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Genera un token JWT firmado que incluye el identificador del usuario (sub)
    y su rol operativo (GENERADOR, RECICLADOR, ADMINISTRADOR).
    """
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode: Dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decodifica y valida la firma y expiración de un token JWT.
    Lanza JWTError si el token es inválido o ha expirado.
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

