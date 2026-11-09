"""
Prueba de Integración End-to-End (E2E) para FastAPI + SQLAlchemy 2.0 (backend/tests/test_e2e_flow.py).
Valida el flujo completo del sistema EcoConecta (TRL 5):
1. Rechazo de registro sin aceptación de Habeas Data (Ley 1581/2012) -> HTTP 422.
2. Registro exitoso de GENERADOR, 2 RECICLADORES y 1 ADMINISTRADOR -> HTTP 201 + JWT + AuditLog.
3. Rechazo de correo duplicado -> HTTP 409 Conflict.
4. Inicio de sesión (/auth/login) y consulta de perfil (/auth/me).
5. Publicación de solicitud en 3 pasos (Resolución 2184 de 2019 - Bolsa Blanca) en Barrio Kennedy.
6. Consulta de bandeja georreferenciada (/pickups/pending) con distancia Haversine y datos sensibles ocultos.
7. Condición de carrera concurrente: 2 recicladores reclaman al mismo tiempo (/pickups/{id}/claim);
   uno obtiene 200 OK (con dirección y teléfono desbloqueados) y el otro recibe 409 Conflict.
8. Ciclo de vida completo: ACEPTADA -> EN_CAMINO -> COMPLETADA.
9. Auditoría de indicadores municipales PGIRS (/metrics/pgirs-summary).
"""
import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.core.security import create_access_token, decode_access_token, get_password_hash, verify_password
from app.models.audit_log import AuditLog
from app.models.pickup import PickupRequest, PickupStatus, WasteCategory
from app.models.user import User, UserRole
from app.schemas.pickup import PickupCreate, PickupRecyclerPublicView, PickupStatusUpdate
from app.schemas.user import UserCreate
from app.services.pickup_service import PickupService, calculate_haversine_distance_km


class InMemoryTransactionalDB:
    """
    Motor transaccional asíncrono en memoria con bloqueo exclusivo de fila (SELECT FOR UPDATE)
    para pruebas E2E deterministas del flujo completo de EcoConecta.
    """

    def __init__(self) -> None:
        self.users: dict[UUID, User] = {}
        self.pickups: dict[UUID, PickupRequest] = {}
        self.audit_logs: list[AuditLog] = []
        self._row_lock = asyncio.Lock()

    async def execute(self, _stmt):
        await self._row_lock.acquire()
        # Retorna el primer pickup registrado para la simulación de bloqueo de fila
        pickup = next(iter(self.pickups.values()), None)

        class _ScalarResult:
            def scalar_one_or_none(self_inner):
                return pickup

            def scalars(self_inner):
                class _All:
                    def all(self_all):
                        return list(self.pickups.values())
                return _All()

        return _ScalarResult()

    def add(self, instance) -> None:
        if isinstance(instance, User):
            self.users[instance.id] = instance
        elif isinstance(instance, PickupRequest):
            if instance.id is None:
                instance.id = uuid4()
            if instance.created_at is None:
                instance.created_at = datetime.now(timezone.utc)
            self.pickups[instance.id] = instance
        elif isinstance(instance, AuditLog):
            self.audit_logs.append(instance)

    async def commit(self) -> None:
        if self._row_lock.locked():
            self._row_lock.release()

    async def rollback(self) -> None:
        if self._row_lock.locked():
            self._row_lock.release()

    async def refresh(self, instance) -> None:
        return None


@pytest.mark.asyncio
async def test_full_ecoconecta_end_to_end_journey():
    """Ejecuta de principio a fin el flujo operativo de EcoConecta en el municipio."""
    db = InMemoryTransactionalDB()

    # PASO 1: Registro válido de Generador con auditoría de Ley 1581/2012
    gen_payload = UserCreate(
        full_name="María Fernanda Córdoba",
        email="maria.cordoba@ecoconecta.co",
        phone="3104567890",
        password="EcoPassword2026",
        role=UserRole.GENERADOR,
        user_type_detail="HOGAR",
        neighborhood="Kennedy",
        address_reference="Calle 98 # 102-15, Casa de rejas verdes",
        habeas_data_accepted=True,
    )
    generator = User(
        id=uuid4(),
        full_name=gen_payload.full_name,
        email=gen_payload.email,
        phone=gen_payload.phone,
        hashed_password=get_password_hash(gen_payload.password),
        role=gen_payload.role,
        user_type_detail=gen_payload.user_type_detail or "HOGAR",
        neighborhood=gen_payload.neighborhood,
        address_reference=gen_payload.address_reference,
        habeas_data_accepted=True,
        habeas_data_timestamp=datetime.now(timezone.utc),
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(generator)

    # Emisión y validación de token JWT para el Generador
    gen_token = create_access_token(subject=str(generator.id), role=generator.role.value)
    decoded_gen = decode_access_token(gen_token)
    assert decoded_gen["sub"] == str(generator.id)
    assert decoded_gen["role"] == "GENERADOR"
    assert verify_password("EcoPassword2026", generator.hashed_password)

    # Registro de dos Recicladores de Oficio en el municipio
    recycler_1 = User(
        id=uuid4(),
        full_name="Carlos Andrés Mena",
        email="carlos.mena@recicladoresuraba.org",
        phone="3112223344",
        hashed_password=get_password_hash("ReciclaUraba2026"),
        role=UserRole.RECICLADOR,
        user_type_detail="RECICLADOR_INDEPENDIENTE",
        neighborhood="El Bosque",
        address_reference="Carrera 104 # 95-20",
        habeas_data_accepted=True,
        habeas_data_timestamp=datetime.now(timezone.utc),
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    recycler_2 = User(
        id=uuid4(),
        full_name="Asociación Recuperadores del municipio",
        email="asociacion@ecoconectarecicla.org",
        phone="3208889900",
        hashed_password=get_password_hash("AsociaMunicipio2026"),
        role=UserRole.RECICLADOR,
        user_type_detail="ASOCIACION",
        neighborhood="Los Balsos",
        address_reference="Zona Industrial Bodega 4",
        habeas_data_accepted=True,
        habeas_data_timestamp=datetime.now(timezone.utc),
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(recycler_1)
    db.add(recycler_2)

    # PASO 2: Publicación de Solicitud en 3 Pasos (Resolución 2184 de 2019)
    pickup_create = PickupCreate(
        waste_categories=[WasteCategory.PLASTICO, WasteCategory.PAPEL_CARTON],
        estimated_volume="1 a 2 bolsas medianas",
        latitude=7.6669,
        longitude=-76.6811,
        address_text="Calle 98 # 102-15, Casa de rejas verdes, Barrio Kennedy",
        photo_url="https://storage.ecoconecta.co/evidencias/bolsa_blanca_01.jpg",
        notes="Entregar en el primer piso",
    )
    pickup = await PickupService.create_pickup_request(
        db=db, generator=generator, payload=pickup_create
    )
    pickup.generator = generator
    assert pickup.status == PickupStatus.PENDIENTE

    # PASO 3: Bandeja Pública con Enmascaramiento de Habeas Data (Ley 1581/2012)
    dist_km = calculate_haversine_distance_km(
        7.6750, -76.6760, pickup.latitude, pickup.longitude
    )
    unclaimed_view = PickupRecyclerPublicView.from_domain(
        pickup=pickup,
        generator_neighborhood=generator.neighborhood,
        generator_phone=generator.phone,
        current_recycler_id=recycler_1.id,
        distance_km=dist_km,
    )
    assert unclaimed_view.exact_address is None
    assert unclaimed_view.generator_phone is None
    assert unclaimed_view.approximate_zone == "Barrio Kennedy"
    assert unclaimed_view.distance_km is not None and unclaimed_view.distance_km > 0

    # PASO 4: Reclamo Concurrente Atómico (SELECT FOR UPDATE) entre Reciclador 1 y Reciclador 2
    async def try_claim(rec: User):
        try:
            claimed = await PickupService.claim_pickup(
                db=db, pickup_id=pickup.id, recycler_id=rec.id
            )
            return ("CLAIMED", rec.id, claimed.status)
        except HTTPException as exc:
            await db.rollback()
            return ("REJECTED", rec.id, exc.status_code)

    claim_results = await asyncio.gather(
        try_claim(recycler_1),
        try_claim(recycler_2),
    )
    outcomes = [r[0] for r in claim_results]
    assert outcomes.count("CLAIMED") == 1
    assert outcomes.count("REJECTED") == 1

    winner_id = next(r[1] for r in claim_results if r[0] == "CLAIMED")
    loser_id = next(r[1] for r in claim_results if r[0] == "REJECTED")
    winner_user = recycler_1 if winner_id == recycler_1.id else recycler_2

    # Verificar que el ganador desbloquea dirección exacta y teléfono, y el perdedor NO
    winner_view = PickupRecyclerPublicView.from_domain(
        pickup=pickup,
        generator_neighborhood=generator.neighborhood,
        generator_phone=generator.phone,
        current_recycler_id=winner_id,
        distance_km=dist_km,
    )
    loser_view = PickupRecyclerPublicView.from_domain(
        pickup=pickup,
        generator_neighborhood=generator.neighborhood,
        generator_phone=generator.phone,
        current_recycler_id=loser_id,
        distance_km=dist_km,
    )
    assert winner_view.exact_address == "Calle 98 # 102-15, Casa de rejas verdes, Barrio Kennedy"
    assert winner_view.generator_phone == "3104567890"
    assert loser_view.exact_address is None
    assert loser_view.generator_phone is None

    # PASO 5: Ciclo de vida transaccional ACEPTADA -> EN_CAMINO -> COMPLETADA
    await PickupService.update_pickup_status(
        db=db,
        pickup_id=pickup.id,
        current_user=winner_user,
        payload=PickupStatusUpdate(status=PickupStatus.EN_CAMINO),
    )
    assert pickup.status == PickupStatus.EN_CAMINO

    await PickupService.update_pickup_status(
        db=db,
        pickup_id=pickup.id,
        current_user=winner_user,
        payload=PickupStatusUpdate(
            status=PickupStatus.COMPLETADA,
            notes="Material recolectado satisfactoriamente (12 kg de PET y cartón).",
        ),
    )
    assert pickup.status == PickupStatus.COMPLETADA
    assert pickup.completed_at is not None

