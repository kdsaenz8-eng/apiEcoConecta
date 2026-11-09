"""
Schemas Pydantic v2 para el módulo de Usuarios y Autenticación (app/schemas/user.py).
Implementa validaciones de dominio, contraseña alfanumérica y verificación obligatoria
de la Ley 1581 de 2012 (Habeas Data Colombia).
"""
import re
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import UserRole, UserTypeDetail


class UserCreate(BaseModel):
    """Payload de entrada para registro público abierto en el municipio (HU-01)."""

    full_name: str = Field(
        ...,
        min_length=3,
        max_length=120,
        description="Nombre completo o razón social del usuario",
        examples=["María Fernanda Córdoba"],
    )
    email: EmailStr = Field(
        ...,
        description="Correo electrónico único del usuario",
        examples=["maria.cordoba@ecoconecta.co"],
    )
    phone: str = Field(
        ...,
        min_length=7,
        max_length=20,
        description="Número de teléfono celular o fijo de contacto",
        examples=["3104567890"],
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Contraseña de mínimo 8 caracteres con letras y números",
        examples=["EcoMunicipio2026"],
    )
    role: UserRole = Field(
        ...,
        description="Rol principal: GENERADOR, RECICLADOR o ADMINISTRADOR",
    )
    user_type_detail: Optional[str] = Field(
        default=UserTypeDetail.HOGAR.value,
        max_length=50,
        description="Subtipo: HOGAR, COMERCIO, RECICLADOR_INDEPENDIENTE, ASOCIACION",
    )
    neighborhood: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Barrio de residencia o actividad en el municipio",
        examples=["Kennedy", "El Bosque", "Los Balsos", "Brisas del Río"],
    )
    address_reference: str = Field(
        ...,
        min_length=5,
        max_length=255,
        description="Dirección o punto de referencia para recolección",
        examples=["Calle 98 # 102-15, casa de rejas verdes"],
    )
    habeas_data_accepted: bool = Field(
        ...,
        description="Consentimiento expreso de tratamiento de datos personales (Ley 1581 de 2012)",
    )

    @field_validator("password")
    @classmethod
    def validate_alphanumeric_password(cls, value: str) -> str:
        """Garantiza que la contraseña tenga al menos 8 caracteres, una letra y un número."""
        cleaned = value.strip()
        if len(cleaned) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres efectivos.")
        if not re.search(r"[A-Za-z]", cleaned) or not re.search(r"\d", cleaned):
            raise ValueError(
                "La contraseña debe ser alfanumérica (contener al menos una letra y un número)."
            )
        return cleaned

    @field_validator("habeas_data_accepted")
    @classmethod
    def validate_habeas_data_consent(cls, value: bool) -> bool:
        """
        Regla de Negocio 2 (Cumplimiento Legal Ley 1581 de 2012):
        Rechaza con HTTP 422 Unprocessable Entity si el usuario no acepta la política.
        """
        if value is not True:
            raise ValueError(
                "Es obligatorio aceptar la Política de Privacidad y Tratamiento de Datos "
                "Personales conforme a la Ley 1581 de 2012 para registrarse en EcoConecta."
            )
        return value


class UserLogin(BaseModel):
    """Credenciales de acceso para inicio de sesión."""

    email: EmailStr = Field(..., description="Correo electrónico registrado")
    password: str = Field(..., min_length=1, description="Contraseña en texto plano")


class UserPublicResponse(BaseModel):
    """Respuesta pública de perfil de usuario sin exponer el hash de contraseña."""

    id: UUID
    full_name: str
    email: EmailStr
    phone: str
    role: UserRole
    user_type_detail: str
    neighborhood: str
    address_reference: str
    habeas_data_accepted: bool
    habeas_data_timestamp: datetime
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    """Respuesta estándar OAuth2 con token JWT y metadatos del usuario autenticado."""

    access_token: str = Field(..., description="Token JWT firmado")
    token_type: str = Field(default="bearer", description="Esquema de autenticación")
    role: UserRole = Field(..., description="Rol del usuario para redirección en Frontend")
    user: UserPublicResponse = Field(..., description="Datos del perfil del usuario")

