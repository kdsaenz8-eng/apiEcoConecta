"""
Modelo de Dominio y Persistencia para Usuarios (app/models/user.py).
Implementa los roles abiertos de EcoConecta (GENERADOR, RECICLADOR, ADMINISTRADOR)
y la trazabilidad legal exigida por la Ley Estatutaria 1581 de 2012 (Habeas Data Colombia).
"""
import enum
import uuid
from datetime import datetime, timezone
from typing import List, TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.pickup import PickupRequest


class UserRole(str, enum.Enum):
    """Roles operativos dentro del ecosistema de reciclaje del municipio."""
    GENERADOR = "GENERADOR"
    RECICLADOR = "RECICLADOR"
    ADMINISTRADOR = "ADMINISTRADOR"


class UserTypeDetail(str, enum.Enum):
    """Sub-clasificación del actor según el modelo operativo municipal."""
    HOGAR = "HOGAR"
    COMERCIO = "COMERCIO"
    RECICLADOR_INDEPENDIENTE = "RECICLADOR_INDEPENDIENTE"
    ASOCIACION = "ASOCIACION"
    INSTITUCIONAL = "INSTITUCIONAL"


class User(Base):
    """
    Entidad Raíz de Agregado para Usuarios de la plataforma EcoConecta.
    Almacena credenciales cifradas, ubicación barrial en el municipio y auditoría de Habeas Data.
    """
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Identificador único universal del usuario",
    )
    full_name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        comment="Nombre completo o razón social del comercio/asociación",
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
        comment="Correo electrónico único para autenticación",
    )
    phone: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Teléfono móvil de contacto operativo (protegido por Ley 1581)",
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Hash Bcrypt de la contraseña del usuario",
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum"),
        nullable=False,
        index=True,
        comment="Rol principal: GENERADOR, RECICLADOR o ADMINISTRADOR",
    )
    user_type_detail: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=UserTypeDetail.HOGAR.value,
        comment="Detalle del perfil: HOGAR, COMERCIO, RECICLADOR_INDEPENDIENTE, ASOCIACION",
    )
    neighborhood: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Barrio o sector del municipio (ej. Kennedy, El Bosque, Los Balsos)",
    )
    address_reference: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Dirección física o punto de referencia en el municipio",
    )
    habeas_data_accepted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Consentimiento explícito de la Política de Tratamiento de Datos (Ley 1581/2012)",
    )
    habeas_data_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Fecha y hora exacta (UTC) de aceptación de Habeas Data",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Indica si la cuenta se encuentra habilitada para operar",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Fecha de creación del registro",
    )

    # Relaciones bidireccionales con solicitudes de recolección
    generated_pickups: Mapped[List["PickupRequest"]] = relationship(
        "PickupRequest",
        back_populates="generator",
        foreign_keys="PickupRequest.generator_id",
        lazy="selectin",
    )
    assigned_pickups: Mapped[List["PickupRequest"]] = relationship(
        "PickupRequest",
        back_populates="recycler",
        foreign_keys="PickupRequest.recycler_id",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_users_role_neighborhood", "role", "neighborhood"),
    )

