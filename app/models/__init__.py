"""Exportación centralizada de modelos SQLAlchemy para Alembic y la aplicación."""
from app.models.user import User, UserRole, UserTypeDetail
from app.models.pickup import PickupRequest, PickupStatus, WasteCategory
from app.models.audit_log import AuditLog

__all__ = [
    "User",
    "UserRole",
    "UserTypeDetail",
    "PickupRequest",
    "PickupStatus",
    "WasteCategory",
    "AuditLog",
]

