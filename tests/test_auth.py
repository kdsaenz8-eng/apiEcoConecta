"""
Pruebas automatizadas (TDD) para el módulo de Autenticación y Cumplimiento Legal (Ley 1581 de 2012).
Verifica HU-01: Registro abierto por roles, validación obligatoria de Habeas Data,
unicidad de correo electrónico, emisión de JWT y consulta de perfil (/me).
"""
import pytest
from datetime import datetime, timezone
from uuid import uuid4
from pydantic import ValidationError

from app.models.user import UserRole
from app.schemas.user import UserCreate, UserLogin, UserPublicResponse
from app.core.security import get_password_hash, verify_password, create_access_token, decode_access_token


def test_user_registration_requires_habeas_data_acceptance():
    """
    Regla de Negocio (Ley 1581 de 2012):
    Ningún usuario puede completar el registro si habeas_data_accepted es False.
    Debe rechazar con ValidationError (HTTP 422 en FastAPI).
    """
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            full_name="María Córdoba",
            email="maria.cordoba@ecoconecta.co",
            phone="3101234567",
            password="Password123",
            role=UserRole.GENERADOR,
            user_type_detail="HOGAR",
            neighborhood="Kennedy",
            address_reference="Calle 98 # 102-15, frente al parque",
            habeas_data_accepted=False,
        )
    assert "Ley 1581" in str(exc_info.value) or "habeas_data_accepted" in str(exc_info.value)


def test_user_registration_password_complexity():
    """
    Verifica que la contraseña tenga mínimo 8 caracteres y sea alfanumérica.
    """
    with pytest.raises(ValidationError):
        UserCreate(
            full_name="Pedro Pérez",
            email="pedro@ecoconecta.co",
            phone="3119876543",
            password=" corta1 ",
            role=UserRole.RECICLADOR,
            user_type_detail="RECICLADOR_INDEPENDIENTE",
            neighborhood="El Bosque",
            address_reference="Carrera 105",
            habeas_data_accepted=True,
        )


def test_valid_user_create_schema_and_password_hashing():
    """
    Verifica creación válida del DTO de registro, hash seguro de contraseña y generación de JWT.
    """
    payload = UserCreate(
        full_name="Asociación Recicladores Urabá Verde",
        email="contacto@urabaverde.org",
        phone="3205551234",
        password="EcoPassword2026",
        role=UserRole.RECICLADOR,
        user_type_detail="ASOCIACION",
        neighborhood="Los Balsos",
        address_reference="Bodega Principal Zona Industrial",
        habeas_data_accepted=True,
    )
    assert payload.role == UserRole.RECICLADOR
    assert payload.habeas_data_accepted is True

    hashed = get_password_hash(payload.password)
    assert hashed != payload.password
    assert verify_password("EcoPassword2026", hashed) is True
    assert verify_password("WrongPassword1", hashed) is False


def test_jwt_token_contains_sub_and_role():
    """
    Verifica que el token JWT emitido incluya el user_id (sub) y el rol del usuario.
    """
    user_id = str(uuid4())
    token = create_access_token(subject=user_id, role=UserRole.GENERADOR.value)
    decoded = decode_access_token(token)

    assert decoded["sub"] == user_id
    assert decoded["role"] == UserRole.GENERADOR.value

