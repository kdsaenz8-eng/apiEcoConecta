"""
Modelo de Auditoría de Tratamiento de Datos Personales y Eventos Operativos (app/models/audit_log.py).
Garantiza la trazabilidad exigida por la Ley 1581 de 2012 y el seguimiento para el PGIRS municipal.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditLog(Base):
    """Registro inmutable de auditoría legal (Habeas Data) y eventos críticos de negocio."""
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        index=True,
        comment="Tipo de evento (ej. HABEAS_DATA_ACCEPTANCE, PICKUP_CLAIMED, PICKUP_COMPLETED)",
    )
    policy_version: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        comment="Versión de la Política de Privacidad aceptada o vigente",
    )
    details: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Metadatos del evento auditable",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

