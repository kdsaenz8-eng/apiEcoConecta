"""
Modelo de Dominio y Persistencia para Solicitudes de Recolección (app/models/pickup.py).
Implementa la máquina de estados transaccional y las categorías de la Resolución 2184 de 2019.
"""
import enum
import uuid
from datetime import datetime, timezone
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class PickupStatus(str, enum.Enum):
    """Ciclo de vida transaccional de una solicitud de recolección."""
    PENDIENTE = "PENDIENTE"
    ACEPTADA = "ACEPTADA"
    EN_CAMINO = "EN_CAMINO"
    COMPLETADA = "COMPLETADA"
    CANCELADA = "CANCELADA"


class WasteCategory(str, enum.Enum):
    """
    Categorías normativas de residuos aprovechables (Bolsa Blanca)
    según la Resolución 2184 de 2019 del Ministerio de Ambiente de Colombia.
    """
    PLASTICO = "PLASTICO"
    PAPEL_CARTON = "CARTON"
    VIDRIO = "VIDRIO"
    METAL = "METAL"


# Transiciones válidas de la máquina de estados (Regla de Dominio DDD)
VALID_STATUS_TRANSITIONS = {
    PickupStatus.PENDIENTE: {PickupStatus.ACEPTADA, PickupStatus.CANCELADA},
    PickupStatus.ACEPTADA: {PickupStatus.EN_CAMINO, PickupStatus.COMPLETADA, PickupStatus.CANCELADA},
    PickupStatus.EN_CAMINO: {PickupStatus.COMPLETADA, PickupStatus.CANCELADA},
    PickupStatus.COMPLETADA: set(),
    PickupStatus.CANCELADA: set(),
}


class PickupRequest(Base):
    """
    Entidad Raíz de Agregado que representa una solicitud de recolección de material reciclable.
    Soporta bloqueo pesimista (SELECT FOR UPDATE) para evitar condiciones de carrera entre recicladores.
    """
    __tablename__ = "pickup_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Identificador único de la solicitud de recolección",
    )
    generator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="ID del ciudadano o comercio generador del residuo",
    )
    recycler_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="ID del reciclador de oficio que reclamó atómicamente la solicitud",
    )
    status: Mapped[PickupStatus] = mapped_column(
        Enum(PickupStatus, name="pickup_status_enum"),
        nullable=False,
        default=PickupStatus.PENDIENTE,
        index=True,
        comment="Estado actual en el ciclo de vida: PENDIENTE, ACEPTADA, EN_CAMINO, COMPLETADA, CANCELADA",
    )
    waste_categories: Mapped[List[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        comment='Lista de materiales según Res. 2184/2019 (ej. ["PLASTICO", "CARTON", "VIDRIO"])',
    )
    estimated_volume: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        comment='Volumen estimado del material (ej. "1 a 2 bolsas medianas", "1 bulto")',
    )
    latitude: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        index=True,
        comment="Latitud geográfica WGS84 en el municipio",
    )
    longitude: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        index=True,
        comment="Longitud geográfica WGS84 en el municipio",
    )
    address_text: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Dirección física reportada (protegida hasta estado ACEPTADA según Ley 1581)",
    )
    photo_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="URL de la fotografía de evidencia almacenada en servicio Cloud",
    )
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Observaciones adicionales para la entrega",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Fecha y hora de publicación de la solicitud",
    )
    accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Fecha y hora exacta en que un reciclador bloqueó y aceptó la solicitud",
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Fecha y hora de cierre efectivo de la recolección",
    )

    # Relaciones con el modelo User
    generator: Mapped["User"] = relationship(
        "User",
        back_populates="generated_pickups",
        foreign_keys=[generator_id],
        lazy="selectin",
    )
    recycler: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="assigned_pickups",
        foreign_keys=[recycler_id],
        lazy="selectin",
    )

    __table_args__ = (
        # Índice compuesto espacial y por estado para acelerar búsquedas de bandeja de recicladores
        Index("ix_pickup_status_coords", "status", "latitude", "longitude"),
    )

    def can_transition_to(self, new_status: PickupStatus) -> bool:
        """Verifica en el dominio si la transición de estado solicitada es válida e idempotente."""
        if new_status == self.status:
            return True
        allowed = VALID_STATUS_TRANSITIONS.get(self.status, set())
        return new_status in allowed

    @property
    def generator_name(self) -> Optional[str]:
        """Nombre del generador asociado para enriquecimiento de vistas."""
        return self.generator.full_name if self.generator else None

    @property
    def generator_phone(self) -> Optional[str]:
        """Teléfono de contacto del generador para reciclador asignado o admin."""
        return self.generator.phone if self.generator else None

    @property
    def neighborhood(self) -> Optional[str]:
        """Barrio o comuna del generador."""
        return self.generator.neighborhood if self.generator else None

    @property
    def recycler_name(self) -> Optional[str]:
        """Nombre del reciclador asignado, o None si está pendiente."""
        return self.recycler.full_name if self.recycler else None


