"""
Endpoints de Gestión de Usuarios y Consulta Institucional (app/api/v1/endpoints/users.py).
Permite listar recicladores registrados para asignación operativa y consultas de directorio.
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import get_current_active_user
from app.core.database import get_db
from app.models.user import User, UserRole

router = APIRouter(prefix="/users", tags=["Usuarios"])


class RecyclerPublicDTO(BaseModel):
    id: str
    nombre: str
    name: str
    full_name: str
    sector: str
    neighborhood: str
    user_type_detail: Optional[str] = None


@router.get(
    "/recyclers",
    response_model=List[RecyclerPublicDTO],
    summary="Listar recicladores registrados en el municipio",
)
async def list_recyclers_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[RecyclerPublicDTO]:
    """Retorna la lista de recicladores activos para despacho y asignación en paneles."""
    stmt = select(User).where(User.role == UserRole.RECICLADOR)
    result = await db.execute(stmt)
    users = result.scalars().all()

    return [
        RecyclerPublicDTO(
            id=str(u.id),
            nombre=u.full_name,
            name=u.full_name,
            full_name=u.full_name,
            sector=f"Barrio {u.neighborhood}",
            neighborhood=u.neighborhood,
            user_type_detail=str(u.user_type_detail) if u.user_type_detail else "RECICLADOR_INDEPENDIENTE",
        )
        for u in users
    ]
