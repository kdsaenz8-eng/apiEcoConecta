"""
Servicio de Aplicación y Dominio para Gestión de Solicitudes de Recolección (app/services/pickup_service.py).
Implementa el bloqueo pesimista atómico (SELECT FOR UPDATE), la máquina de estados transaccional
y el cálculo geoespacial de distancia (fórmula de Haversine) para Antioquia.
"""
import math
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pickup import PickupRequest, PickupStatus
from app.models.user import User, UserRole
from app.schemas.pickup import (
    PickupCreate,
    PickupRecyclerPublicView,
    PickupStatusUpdate,
)


def calculate_haversine_distance_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Calcula la distancia ortodrómica en kilómetros entre dos puntos geográficos WGS84
    utilizando la fórmula de Haversine.
    """
    earth_radius_km = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(d_lat / 2.0) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return earth_radius_km * c


async def claim_pickup(
    db: AsyncSession,
    pickup_id: UUID,
    recycler_id: UUID,
) -> PickupRequest:
    """
    Aceptación atómica de recolecciones con control de concurrencia pesimista.
    Utiliza SELECT ... FOR UPDATE para bloquear la fila durante la transacción,
    impidiendo que dos recicladores reclamen simultáneamente el mismo material (HU-04).
    """
    stmt = (
        select(PickupRequest)
        .where(PickupRequest.id == pickup_id)
        .with_for_update()
    )
    result = await db.execute(stmt)
    pickup = result.scalar_one_or_none()

    if not pickup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitud no encontrada.",
        )
    if pickup.status != PickupStatus.PENDIENTE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La solicitud ya ha sido tomada por otro reciclador.",
        )

    pickup.recycler_id = recycler_id
    pickup.status = PickupStatus.ACEPTADA
    pickup.accepted_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(pickup)
    return pickup


class PickupService:
    """
    Caso de Uso / Servicio de Dominio que orquesta la creación, consulta georreferenciada,
    reclamo atómico y transición de estados de las solicitudes de reciclaje.
    """

    @staticmethod
    async def create_pickup_request(
        db: AsyncSession,
        generator: User,
        payload: PickupCreate,
    ) -> PickupRequest:
        """Crea una nueva solicitud de recolección en estado PENDIENTE (HU-02)."""
        if generator.role not in {UserRole.GENERADOR, UserRole.ADMINISTRADOR}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo los usuarios con rol GENERADOR pueden publicar solicitudes de recolección.",
            )

        new_pickup = PickupRequest(
            generator_id=generator.id,
            status=PickupStatus.PENDIENTE,
            waste_categories=[cat.value for cat in payload.waste_categories],
            estimated_volume=payload.estimated_volume,
            latitude=payload.latitude,
            longitude=payload.longitude,
            address_text=payload.address_text,
            photo_url=payload.photo_url,
            notes=payload.notes,
        )
        db.add(new_pickup)
        await db.commit()
        await db.refresh(new_pickup)
        return new_pickup

    @staticmethod
    async def claim_pickup(
        db: AsyncSession,
        pickup_id: UUID,
        recycler_id: UUID,
    ) -> PickupRequest:
        """Delega al bloqueador atómico SELECT FOR UPDATE."""
        return await claim_pickup(db=db, pickup_id=pickup_id, recycler_id=recycler_id)

    @staticmethod
    async def list_available_and_assigned_pickups(
        db: AsyncSession,
        recycler: User,
        recycler_lat: Optional[float] = None,
        recycler_lon: Optional[float] = None,
        max_radius_km: Optional[float] = None,
    ) -> List[PickupRecyclerPublicView]:
        """
        Retorna las solicitudes PENDIENTES en el municipio (con dirección y teléfono protegidos
        según Ley 1581/2012) más las solicitudes ya aceptadas por el reciclador actual
        (con datos de contacto desbloqueados), ordenadas por cercanía geográfica.
        """
        stmt = (
            select(PickupRequest)
            .where(
                (PickupRequest.status == PickupStatus.PENDIENTE)
                | (PickupRequest.recycler_id == recycler.id)
            )
            .order_by(PickupRequest.created_at.desc())
        )
        result = await db.execute(stmt)
        pickups = result.scalars().all()

        views: List[PickupRecyclerPublicView] = []
        for item in pickups:
            dist_km: Optional[float] = None
            if recycler_lat is not None and recycler_lon is not None:
                dist_km = calculate_haversine_distance_km(
                    recycler_lat, recycler_lon, item.latitude, item.longitude
                )
                if max_radius_km is not None and dist_km > max_radius_km:
                    continue

            generator_neighborhood = (
                item.generator.neighborhood if item.generator else "Zona Urbana"
            )
            generator_phone = item.generator.phone if item.generator else ""

            views.append(
                PickupRecyclerPublicView.from_domain(
                    pickup=item,
                    generator_neighborhood=generator_neighborhood,
                    generator_phone=generator_phone,
                    current_recycler_id=recycler.id,
                    distance_km=dist_km,
                )
            )

        if recycler_lat is not None and recycler_lon is not None:
            views.sort(key=lambda v: v.distance_km if v.distance_km is not None else 9999.0)

        return views

    @staticmethod
    async def update_pickup_status(
        db: AsyncSession,
        pickup_id: UUID,
        current_user: User,
        payload: PickupStatusUpdate,
    ) -> PickupRequest:
        """
        Gestiona el ciclo de vida transaccional:
        PENDIENTE -> ACEPTADA -> EN_CAMINO -> COMPLETADA (o CANCELADA).
        """
        stmt = (
            select(PickupRequest)
            .where(PickupRequest.id == pickup_id)
            .with_for_update()
        )
        result = await db.execute(stmt)
        pickup = result.scalar_one_or_none()

        if not pickup:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Solicitud de recolección no encontrada.",
            )

        # Verificación de permisos según rol y propiedad
        is_owner_generator = pickup.generator_id == current_user.id
        is_assigned_recycler = pickup.recycler_id == current_user.id
        is_admin = current_user.role == UserRole.ADMINISTRADOR

        if not (is_owner_generator or is_assigned_recycler or is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permisos para modificar el estado de esta solicitud.",
            )

        if not pickup.can_transition_to(payload.status):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Transición de estado inválida: no se puede pasar de "
                    f"{pickup.status.value} a {payload.status.value}."
                ),
            )

        pickup.status = payload.status
        if payload.notes:
            pickup.notes = payload.notes

        if payload.status == PickupStatus.COMPLETADA:
            pickup.completed_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(pickup)
        return pickup

