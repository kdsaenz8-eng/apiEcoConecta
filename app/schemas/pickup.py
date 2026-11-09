"""
Schemas Pydantic v2 para Solicitudes de Recolección (app/schemas/pickup.py).
Implementa validaciones para publicación en 3 pasos (Resolución 2184 de 2019)
y enmascaramiento de datos sensibles de ubicación/teléfono según Ley 1581 de 2012.
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.pickup import PickupRequest, PickupStatus, WasteCategory


class PickupCreate(BaseModel):
    """
    DTO para creación de solicitud en 3 pasos por parte del GENERADOR (HU-02):
    Paso 1: Categorías (Res. 2184/2019)
    Paso 2: Volumen estimado y fotografía de evidencia
    Paso 3: Coordenadas GPS y dirección/referencia
    """

    waste_categories: List[WasteCategory] = Field(
        ...,
        min_length=1,
        description="Materiales reciclables seleccionados (Bolsa Blanca - Res. 2184/2019)",
        examples=[[WasteCategory.PLASTICO, WasteCategory.PAPEL_CARTON]],
    )
    estimated_volume: str = Field(
        ...,
        min_length=3,
        max_length=120,
        description="Estimación sencilla del volumen (ej. '1 a 2 bolsas medianas', '1 bulto')",
        examples=["1 a 2 bolsas medianas"],
    )
    latitude: float = Field(
        ...,
        ge=-90.0,
        le=90.0,
        description="Latitud GPS del punto de recolección",
        examples=[7.6669],
    )
    longitude: float = Field(
        ...,
        ge=-180.0,
        le=180.0,
        description="Longitud GPS del punto de recolección",
        examples=[-76.6811],
    )
    address_text: str = Field(
        ...,
        min_length=5,
        max_length=255,
        description="Dirección exacta y referencia (protegida hasta aceptación del reciclador)",
        examples=["Calle 96 # 104-22, Barrio Kennedy"],
    )
    photo_url: Optional[str] = Field(
        default=None,
        max_length=500,
        description="URL de la foto de evidencia subida al almacenamiento Cloud",
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Notas opcionales para el reciclador (ej. 'Timbrar en el segundo piso')",
    )

    @field_validator("waste_categories")
    @classmethod
    def ensure_unique_categories(cls, categories: List[WasteCategory]) -> List[WasteCategory]:
        """Elimina duplicados preservando el orden de selección."""
        seen = []
        for cat in categories:
            if cat not in seen:
                seen.append(cat)
        return seen


class PickupStatusUpdate(BaseModel):
    """Payload para avanzar el estado de una solicitud (ACEPTADA -> EN_CAMINO -> COMPLETADA / CANCELADA)."""

    status: PickupStatus = Field(
        ...,
        description="Nuevo estado solicitado para la recolección",
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Observación opcional al actualizar el estado",
    )


class PickupResponse(BaseModel):
    """Respuesta completa de una solicitud para su creador o el reciclador asignado."""

    id: UUID
    generator_id: UUID
    recycler_id: Optional[UUID] = None
    status: PickupStatus
    waste_categories: List[str]
    estimated_volume: str
    latitude: float
    longitude: float
    address_text: str
    photo_url: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    accepted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PickupRecyclerPublicView(BaseModel):
    """
    Vista con Protección de Privacidad por Diseño (Ley 1581 de 2012) para la bandeja de recicladores.
    Si la solicitud está PENDIENTE (o no pertenece al reciclador consultante), oculta la dirección exacta
    y el teléfono del generador, mostrando únicamente el barrio/zona aproximada y la distancia en km.
    """

    id: UUID
    status: PickupStatus
    waste_categories: List[str]
    estimated_volume: str
    latitude: float
    longitude: float
    approximate_zone: str = Field(
        ...,
        description="Zona o barrio general en el municipio (visible públicamente)",
    )
    distance_km: Optional[float] = Field(
        default=None,
        description="Distancia calculada desde la ubicación del reciclador en kilómetros",
    )
    exact_address: Optional[str] = Field(
        default=None,
        description="Dirección exacta (SOLO revelada tras reclamo atómico por el reciclador asignado)",
    )
    generator_phone: Optional[str] = Field(
        default=None,
        description="Teléfono del generador (SOLO revelado al reciclador que aceptó la solicitud)",
    )
    photo_url: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    accepted_at: Optional[datetime] = None

    @classmethod
    def from_domain(
        cls,
        pickup: PickupRequest,
        generator_neighborhood: str,
        generator_phone: str,
        current_recycler_id: Optional[UUID],
        distance_km: Optional[float] = None,
    ) -> "PickupRecyclerPublicView":
        """
        Fábrica de Dominio que aplica la regla de confidencialidad de Habeas Data:
        Solo desbloquea dirección y teléfono si el reciclador actual es quien bloqueó la solicitud.
        """
        is_assigned_to_current_recycler = (
            pickup.recycler_id is not None
            and current_recycler_id is not None
            and pickup.recycler_id == current_recycler_id
            and pickup.status in {PickupStatus.ACEPTADA, PickupStatus.EN_CAMINO, PickupStatus.COMPLETADA}
        )

        return cls(
            id=pickup.id,
            status=pickup.status,
            waste_categories=list(pickup.waste_categories),
            estimated_volume=pickup.estimated_volume,
            latitude=pickup.latitude,
            longitude=pickup.longitude,
            approximate_zone=f"Barrio {generator_neighborhood}",
            distance_km=round(distance_km, 2) if distance_km is not None else None,
            exact_address=pickup.address_text if is_assigned_to_current_recycler else None,
            generator_phone=generator_phone if is_assigned_to_current_recycler else None,
            photo_url=pickup.photo_url,
            notes=pickup.notes if is_assigned_to_current_recycler else None,
            created_at=pickup.created_at,
            accepted_at=pickup.accepted_at,
        )

