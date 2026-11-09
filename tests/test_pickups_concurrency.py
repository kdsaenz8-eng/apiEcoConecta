"""
Pruebas automatizadas (TDD) para la máquina de estados, privacidad geográfica (Ley 1581)
y el bloqueo atómico de concurrencia (SELECT FOR UPDATE) en solicitudes de recolección.
Verifica HU-02 y HU-04.
"""
import asyncio
import pytest
from uuid import uuid4
from fastapi import HTTPException

from app.models.pickup import PickupRequest, PickupStatus, WasteCategory
from app.services.pickup_service import PickupService, calculate_haversine_distance_km
from app.schemas.pickup import PickupCreate, PickupRecyclerPublicView


class FakeScalarResult:
    """Simulador de resultado escalar SQLAlchemy para pruebas unitarias de concurrencia."""

    def __init__(self, record):
        self._record = record

    def scalar_one_or_none(self):
        return self._record


class FakeLockingAsyncSession:
    """
    Simulador de AsyncSession con semáforo asíncrono que emula el bloqueo de fila
    SELECT ... FOR UPDATE en PostgreSQL cuando dos recicladores reclaman al mismo tiempo.
    """

    def __init__(self, pickup: PickupRequest):
        self.pickup = pickup
        self._row_lock = asyncio.Lock()

    async def execute(self, stmt):
        # Simula el bloqueo exclusivo de fila en base de datos durante la transacción
        await self._row_lock.acquire()
        return FakeScalarResult(self.pickup)

    async def commit(self):
        if self._row_lock.locked():
            self._row_lock.release()

    async def rollback(self):
        if self._row_lock.locked():
            self._row_lock.release()

    async def refresh(self, instance):
        return instance


@pytest.mark.asyncio
async def test_concurrent_pickup_claim_allows_only_one_recycler():
    """
    Regla de Negocio 4 (Control de Concurrencia Crítico):
    Dos recicladores no pueden aceptar la misma solicitud simultáneamente.
    El primer reclamo exitoso cambia el estado a ACEPTADA; el segundo recibe HTTP 409 Conflict.
    """
    pickup_id = uuid4()
    generator_id = uuid4()
    recycler_1_id = uuid4()
    recycler_2_id = uuid4()

    pickup = PickupRequest(
        id=pickup_id,
        generator_id=generator_id,
        status=PickupStatus.PENDIENTE,
        waste_categories=[WasteCategory.PLASTICO.value, WasteCategory.CARTON.value],
        estimated_volume="1 a 2 bolsas medianas",
        latitude=7.6669,
        longitude=-76.6811,
        address_text="Calle 96 # 104-22, Barrio Kennedy",
    )

    session = FakeLockingAsyncSession(pickup)

    async def attempt_claim(recycler_id):
        try:
            result = await PickupService.claim_pickup(
                db=session, pickup_id=pickup_id, recycler_id=recycler_id
            )
            return ("SUCCESS", result.recycler_id)
        except HTTPException as exc:
            await session.rollback()
            return ("ERROR", exc.status_code)

    results = await asyncio.gather(
        attempt_claim(recycler_1_id),
        attempt_claim(recycler_2_id),
    )

    statuses = [r[0] for r in results]
    assert statuses.count("SUCCESS") == 1
    assert statuses.count("ERROR") == 1

    error_codes = [r[1] for r in results if r[0] == "ERROR"]
    assert error_codes == [409]
    assert pickup.status == PickupStatus.ACEPTADA
    assert pickup.accepted_at is not None


def test_privacy_masking_for_unclaimed_pickup():
    """
    Regla de Negocio 2 (Habeas Data Colombia):
    En el mapa/lista pública para recicladores, la dirección exacta y el teléfono del generador
    permanecen protegidos hasta que un reciclador formalmente acepte y bloquee la recolección.
    """
    pickup = PickupRequest(
        id=uuid4(),
        generator_id=uuid4(),
        status=PickupStatus.PENDIENTE,
        waste_categories=[WasteCategory.VIDRIO.value, WasteCategory.METAL.value],
        estimated_volume="1 bulto grande",
        latitude=7.6685,
        longitude=-76.6825,
        address_text="Carrera 101 # 95-10 Apto 201 (Dato Sensible)",
    )

    public_view = PickupRecyclerPublicView.from_domain(
        pickup=pickup,
        generator_neighborhood="El Bosque",
        generator_phone="3109998877",
        current_recycler_id=uuid4(),
        distance_km=0.45,
    )

    assert public_view.exact_address is None
    assert public_view.generator_phone is None
    assert "El Bosque" in public_view.approximate_zone


def test_haversine_distance_calculation_ecoconecta():
    """
    Verifica el cálculo geoespacial entre dos coordenadas dentro del casco urbano del municipio.
    """
    # Parque Principal del municipio -> Barrio El Bosque (~1.2 km)
    dist = calculate_haversine_distance_km(7.6669, -76.6811, 7.6750, -76.6760)
    assert 0.5 < dist < 2.5

