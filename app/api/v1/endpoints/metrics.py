"""
Endpoints de Indicadores y Métricas para el PGIRS Municipal (app/api/v1/endpoints/metrics.py).
Permite al rol ADMINISTRADOR auditar el impacto de recolección por barrio y estado en el municipio.
"""
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import get_current_active_user
from app.core.database import get_db
from app.models.pickup import PickupRequest, PickupStatus
from app.models.user import User, UserRole

router = APIRouter(prefix="/metrics", tags=["Métricas PGIRS e Indicadores"])


@router.get(
    "/pgirs-summary",
    summary="Indicadores consolidados de recolección para el PGIRS del municipio",
)
async def get_pgirs_metrics_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, object]:
    """
    Retorna conteos de usuarios registrados por rol y estado de las solicitudes
    de recolección para el tablero de seguimiento municipal.
    """
    if current_user.role != UserRole.ADMINISTRADOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso exclusivo para el rol ADMINISTRADOR del PGIRS.",
        )

    status_counts_stmt = select(
        PickupRequest.status, func.count(PickupRequest.id)
    ).group_by(PickupRequest.status)
    status_result = await db.execute(status_counts_stmt)
    pickups_by_status = {row[0].value: row[1] for row in status_result.all()}

    role_counts_stmt = select(User.role, func.count(User.id)).group_by(User.role)
    role_result = await db.execute(role_counts_stmt)
    users_by_role = {row[0].value: row[1] for row in role_result.all()}

    return {
        "municipality": "Antioquia",
        "regulation": "Resolución 2184 de 2019 & Ley 1581 de 2012",
        "users_by_role": {
            UserRole.GENERADOR.value: users_by_role.get(UserRole.GENERADOR.value, 0),
            UserRole.RECICLADOR.value: users_by_role.get(UserRole.RECICLADOR.value, 0),
            UserRole.ADMINISTRADOR.value: users_by_role.get(UserRole.ADMINISTRADOR.value, 0),
        },
        "pickups_by_status": {
            PickupStatus.PENDIENTE.value: pickups_by_status.get(PickupStatus.PENDIENTE.value, 0),
            PickupStatus.ACEPTADA.value: pickups_by_status.get(PickupStatus.ACEPTADA.value, 0),
            PickupStatus.EN_CAMINO.value: pickups_by_status.get(PickupStatus.EN_CAMINO.value, 0),
            PickupStatus.COMPLETADA.value: pickups_by_status.get(PickupStatus.COMPLETADA.value, 0),
            PickupStatus.CANCELADA.value: pickups_by_status.get(PickupStatus.CANCELADA.value, 0),
        },
    }

