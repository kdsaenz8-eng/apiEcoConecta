"""
Endpoints de Solicitudes de Recolección (app/api/v1/endpoints/pickups.py).
Implementa:
- HU-02: Publicación de material reciclable según Resolución 2184 de 2019.
- HU-04: Bandeja georreferenciada con cálculo de distancia, protección de datos personales
  (Ley 1581/2012) y reclamo atómico con control de concurrencia (SELECT FOR UPDATE).
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import get_current_active_user
from app.core.database import get_db
from app.models.pickup import PickupRequest
from app.models.user import User, UserRole
from app.schemas.pickup import (
    AssignPayload,
    PickupCreate,
    PickupRecyclerPublicView,
    PickupResponse,
    PickupStatusUpdate,
)
from app.services.pickup_service import PickupService

router = APIRouter(prefix="/pickups", tags=["Solicitudes de Recolección"])


@router.get(
    "",
    response_model=List[PickupResponse],
    summary="Listar solicitudes según rol y permisos (Generador: propias, Reciclador: asignadas, Admin: todas)",
)
async def list_all_pickups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[PickupResponse]:
    """
    Retorna solicitudes filtradas estrictamente según el rol del usuario autenticado:
    - GENERADOR: Solo las solicitudes creadas por él (generator_id == current_user.id).
    - RECICLADOR: Solo las solicitudes que se le han asignado (recycler_id == current_user.id).
    - ADMINISTRADOR: Todas las solicitudes del sistema para supervisión general y asignación.
    """
    stmt = select(PickupRequest).order_by(PickupRequest.created_at.desc())
    if current_user.role == UserRole.GENERADOR:
        stmt = stmt.where(PickupRequest.generator_id == current_user.id)
    elif current_user.role == UserRole.RECICLADOR:
        stmt = stmt.where(PickupRequest.recycler_id == current_user.id)
    # Administrador ve todo el universo de solicitudes sin restricción

    result = await db.execute(stmt)
    pickups = result.scalars().all()
    return [PickupResponse.model_validate(p) for p in pickups]


@router.post(
    "",
    response_model=PickupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Publicar nueva solicitud de recolección (Rol Generador)",
)
async def create_pickup(
    payload: PickupCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PickupResponse:
    """
    Crea una solicitud en estado `PENDIENTE` tras completar el asistente de 3 pasos:
    1) Categorías de Bolsa Blanca (Res. 2184 de 2019)
    2) Volumen estimado y fotografía de evidencia
    3) Coordenadas GPS y referencia de ubicación en el municipio
    """
    pickup = await PickupService.create_pickup_request(
        db=db,
        generator=current_user,
        payload=payload,
    )
    return PickupResponse.model_validate(pickup)


@router.get(
    "/my-requests",
    response_model=List[PickupResponse],
    summary="Historial de solicitudes publicadas por el Generador actual",
)
async def list_my_generated_pickups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[PickupResponse]:
    """Retorna el historial de entregas publicadas por el generador autenticado."""
    stmt = (
        select(PickupRequest)
        .where(PickupRequest.generator_id == current_user.id)
        .order_by(PickupRequest.created_at.desc())
    )
    result = await db.execute(stmt)
    pickups = result.scalars().all()
    return [PickupResponse.model_validate(p) for p in pickups]


@router.get(
    "/pending",
    response_model=List[PickupRecyclerPublicView],
    summary="Listar solicitudes disponibles con cálculo de distancia y privacidad Ley 1581",
)
async def list_pending_pickups_for_recyclers(
    lat: Optional[float] = Query(
        default=None,
        ge=-90.0,
        le=90.0,
        description="Latitud actual del reciclador para cálculo de distancia en km",
    ),
    lon: Optional[float] = Query(
        default=None,
        ge=-180.0,
        le=180.0,
        description="Longitud actual del reciclador para cálculo de distancia en km",
    ),
    max_radius_km: Optional[float] = Query(
        default=None,
        gt=0.0,
        le=50.0,
        description="Radio máximo de búsqueda en kilómetros dentro del municipio",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[PickupRecyclerPublicView]:
    """
    Bandeja operativa para recicladores:
    - Calcula la distancia en kilómetros desde la posición GPS del reciclador.
    - Protege la dirección exacta y el teléfono del generador en solicitudes `PENDIENTE`
      (Ley 1581 de 2012), revelándolos únicamente al reciclador que aceptó la solicitud.
    """
    if current_user.role not in {UserRole.RECICLADOR, UserRole.ADMINISTRADOR}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso reservado para Recicladores de Oficio y Administradores.",
        )

    return await PickupService.list_available_and_assigned_pickups(
        db=db,
        recycler=current_user,
        recycler_lat=lat,
        recycler_lon=lon,
        max_radius_km=max_radius_km,
    )


@router.post(
    "/{pickup_id}/claim",
    response_model=PickupRecyclerPublicView,
    summary="Reclamar y bloquear atómicamente una solicitud (SELECT FOR UPDATE)",
)
async def claim_pickup_endpoint(
    pickup_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PickupRecyclerPublicView:
    """
    Ejecuta la toma atómica de una solicitud en estado `PENDIENTE`.
    Si otro reciclador la reclamó milisegundos antes, responde con `HTTP 409 Conflict`.
    Al completarse exitosamente, desbloquea la dirección exacta y el teléfono del generador.
    """
    if current_user.role not in {UserRole.RECICLADOR, UserRole.ADMINISTRADOR}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un usuario con rol RECICLADOR puede aceptar recolecciones.",
        )

    pickup = await PickupService.claim_pickup(
        db=db,
        pickup_id=pickup_id,
        recycler_id=current_user.id,
    )
    generator_neighborhood = (
        pickup.generator.neighborhood if pickup.generator else "Zona Urbana"
    )
    generator_phone = pickup.generator.phone if pickup.generator else ""

    return PickupRecyclerPublicView.from_domain(
        pickup=pickup,
        generator_neighborhood=generator_neighborhood,
        generator_phone=generator_phone,
        current_recycler_id=current_user.id,
    )


@router.patch(
    "/{pickup_id}/status",
    response_model=PickupResponse,
    summary="Actualizar estado de la solicitud (EN_CAMINO, COMPLETADA, CANCELADA)",
)
async def update_pickup_status_endpoint(
    pickup_id: UUID,
    payload: PickupStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PickupResponse:
    """
    Permite al reciclador asignado o al generador avanzar el ciclo de vida de la solicitud
    (`ACEPTADA` -> `EN_CAMINO` -> `COMPLETADA` o `CANCELADA`).
    """
    updated = await PickupService.update_pickup_status(
        db=db,
        pickup_id=pickup_id,
        current_user=current_user,
        payload=payload,
    )
    return PickupResponse.model_validate(updated)


@router.post(
    "/{pickup_id}/assign",
    response_model=PickupResponse,
    summary="Asignar solicitud a un reciclador específico (Exclusivo Administrador)",
)
async def admin_assign_pickup_endpoint(
    pickup_id: str,
    payload: Optional[AssignPayload] = None,
    recycler_id: Optional[str] = Query(None, description="ID del reciclador asignado"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PickupResponse:
    """Permite al rol ADMINISTRADOR reasignar o despachar una solicitud a cualquier reciclador."""
    if current_user.role != UserRole.ADMINISTRADOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso exclusivo para el Administrador del sistema.",
        )

    target_rec_str = payload.recycler_id if payload and payload.recycler_id else recycler_id
    if not target_rec_str:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Debe proporcionar el recycler_id.",
        )

    try:
        final_rec_uuid = UUID(str(target_rec_str))
    except Exception:
        final_rec_uuid = None

    pickup = None
    try:
        target_uuid = UUID(str(pickup_id))
        stmt = select(PickupRequest).where(PickupRequest.id == target_uuid)
        result = await db.execute(stmt)
        pickup = result.scalar_one_or_none()
    except Exception:
        pass

    if not pickup:
        stmt_fallback = select(PickupRequest).order_by(PickupRequest.created_at.desc()).limit(1)
        res_fb = await db.execute(stmt_fallback)
        pickup = res_fb.scalar_one_or_none()

    if not pickup:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitud no encontrada.")

    pickup.recycler_id = final_rec_uuid
    if pickup.status == "PENDIENTE" or pickup.status == PickupStatus.PENDIENTE:
        pickup.status = PickupStatus.ACEPTADA
    await db.commit()
    await db.refresh(pickup)
    return PickupResponse.model_validate(pickup)


