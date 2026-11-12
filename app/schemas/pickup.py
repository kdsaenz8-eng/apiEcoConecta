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
    generator_id: Optional[str] = None
    waste_categories: List[str] = Field(
        ...,
        min_length=1,
        description="Materiales reciclables seleccionados (Bolsa Blanca - Res. 2184/2019)",
        examples=[["PLASTICO", "CARTON"]],
    )
    estimated_volume: str = Field(
        ...,
        min_length=1,
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
        min_length=2,
        max_length=255,
        description="Dirección exacta y referencia (protegida hasta aceptación del reciclador)",
        examples=["Calle 96 # 104-22, Barrio Kennedy"],
    )
    photo_url: Optional[str] = Field(
        default=None,
        max_length=10_000_000,
        description="URL remota o Data URI Base64 de la foto de evidencia tomada por el usuario",
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Notas opcionales para el reciclador (ej. 'Timbrar en el segundo piso')",
    )

    @field_validator("waste_categories", mode="before")
    @classmethod
    def normalize_and_deduplicate_categories(cls, v) -> List[str]:
        """Normaliza nombres legibles en español hacia códigos normativos estándar."""
        if not v:
            return ["PLASTICO"]
        mapping = {
            "plást": "PLASTICO",
            "plast": "PLASTICO",
            "botella": "PLASTICO",
            "cartón": "CARTON",
            "carton": "CARTON",
            "papel": "CARTON",
            "vidrio": "VIDRIO",
            "envase": "VIDRIO",
            "metal": "METAL",
            "lata": "METAL",
        }
        normalized: List[str] = []
        for item in v:
            val_str = item.value if hasattr(item, "value") else str(item)
            s = val_str.strip().lower()
            matched = False
            for k, target in mapping.items():
                if k in s:
                    if target not in normalized:
                        normalized.append(target)
                    matched = True
                    break
            if not matched:
                cand = val_str.upper()
                if cand in {"PLASTICO", "CARTON", "VIDRIO", "METAL"}:
                    if cand not in normalized:
                        normalized.append(cand)
                else:
                    if "PLASTICO" not in normalized:
                        normalized.append("PLASTICO")
        return normalized or ["PLASTICO"]


class AssignPayload(BaseModel):
    """Payload para asignación de solicitud a reciclador por el Administrador."""
    recycler_id: Optional[str] = None
    status: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


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

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v) -> PickupStatus:
        """Normaliza variantes comunes enviadas desde clientes móviles o web ('En_Ruta', 'En camino', etc.)."""
        if isinstance(v, PickupStatus):
            return v
        if not v:
            return PickupStatus.PENDIENTE
        v_str = str(v).strip().upper().replace(" ", "_")
        if v_str in {"EN_RUTA", "RUTA", "EN_CAMINO", "CAMINO", "EN-CAMINO", "EN-RUTA"}:
            return PickupStatus.EN_CAMINO
        if v_str in {"COMPLETADA", "COMPLETADO", "FINALIZADA", "FINALIZADO"}:
            return PickupStatus.COMPLETADA
        if v_str in {"ACEPTADA", "ACEPTADO", "ASIGNADA", "ASIGNADO"}:
            return PickupStatus.ACEPTADA
        if v_str in {"CANCELADA", "CANCELADO"}:
            return PickupStatus.CANCELADA
        if v_str in {"PENDIENTE", "PENDING"}:
            return PickupStatus.PENDIENTE
        try:
            return PickupStatus(v_str)
        except ValueError:
            return PickupStatus(v)


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

    # Campos enriquecidos para despliegue directo en paneles sin consultas N+1
    generator_name: Optional[str] = None
    generator_phone: Optional[str] = None
    neighborhood: Optional[str] = None
    recycler_name: Optional[str] = None

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
    address_text: Optional[str] = Field(
        default=None,
        description="Alias de exact_address para compatibilidad",
    )
    generator_phone: Optional[str] = Field(
        default=None,
        description="Teléfono del generador (SOLO revelado al reciclador que aceptó la solicitud)",
    )
    generator_name: Optional[str] = Field(
        default=None,
        description="Nombre del generador (visible si está asignada)",
    )
    recycler_id: Optional[UUID] = Field(
        default=None,
        description="ID del reciclador asignado",
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
            address_text=pickup.address_text if is_assigned_to_current_recycler else None,
            generator_phone=generator_phone if is_assigned_to_current_recycler else None,
            generator_name=pickup.generator_name if is_assigned_to_current_recycler else None,
            recycler_id=pickup.recycler_id,
            photo_url=pickup.photo_url,
            notes=pickup.notes if is_assigned_to_current_recycler else None,
            created_at=pickup.created_at,
            accepted_at=pickup.accepted_at,
        )

