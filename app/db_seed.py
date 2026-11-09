"""
Script de Sembrado de Datos Iniciales (Seed Data) para EcoConecta (TRL 5).
Puebla la base de datos PostgreSQL con actores representativos del municipio del municipio,
solicitudes georreferenciadas (Resolución 2184 de 2019) y registros de auditoría legal (Ley 1581 de 2012).
"""
import asyncio
from datetime import datetime, timezone
import uuid

from sqlalchemy import select
from app.core.database import AsyncSessionLocal, Base, engine
from app.core.security import get_password_hash
from app.models.user import User, UserRole, UserTypeDetail
from app.models.pickup import PickupRequest, PickupStatus, WasteCategory
from app.models.audit_log import AuditLog


async def seed_database():
    print("🌱 Iniciando sembrado de datos para EcoConecta (TRL 5)...")

    # Asegurar tablas existentes
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        # Verificar si ya existen usuarios
        existing = await session.execute(select(User))
        if existing.scalars().first() is not None:
            print("ℹ️ La base de datos ya contiene registros. Omitiendo sembrado duplicado.")
            return

        now = datetime.now(timezone.utc)

        # 1. GENERADORES (Hogares y Comercios del municipio)
        gen1 = User(
            id=uuid.uuid4(),
            full_name="María Fernanda Córdoba",
            email="maria.cordoba@ecoconecta.co",
            phone="3104567890",
            hashed_password=get_password_hash("EcoPassword2026"),
            role=UserRole.GENERADOR,
            user_type_detail=UserTypeDetail.HOGAR.value,
            neighborhood="Kennedy",
            address_reference="Calle 98 # 102-15, Casa de rejas verdes",
            habeas_data_accepted=True,
            habeas_data_timestamp=now,
            is_active=True,
            created_at=now,
        )

        gen2 = User(
            id=uuid.uuid4(),
            full_name="Supermercado El Ahorro Municipio",
            email="supermercado.ahorro@ecoconecta.co",
            phone="3209876543",
            hashed_password=get_password_hash("AhorroMunicipio2026"),
            role=UserRole.GENERADOR,
            user_type_detail=UserTypeDetail.COMERCIO.value,
            neighborhood="Centro",
            address_reference="Carrera 103 # 94-20, Entrada de cargue",
            habeas_data_accepted=True,
            habeas_data_timestamp=now,
            is_active=True,
            created_at=now,
        )

        gen3 = User(
            id=uuid.uuid4(),
            full_name="Panadería La Sultana",
            email="sultana@ecoconecta.co",
            phone="3125554433",
            hashed_password=get_password_hash("Sultana2026"),
            role=UserRole.GENERADOR,
            user_type_detail=UserTypeDetail.COMERCIO.value,
            neighborhood="Los Balsos",
            address_reference="Calle 95 # 105-12, frente al parque",
            habeas_data_accepted=True,
            habeas_data_timestamp=now,
            is_active=True,
            created_at=now,
        )

        # 2. RECICLADORES DE OFICIO (Independientes y Asociaciones)
        rec1 = User(
            id=uuid.uuid4(),
            full_name="Carlos Andrés Mena",
            email="carlos.mena@recicladoresuraba.org",
            phone="3112223344",
            hashed_password=get_password_hash("ReciclaUraba2026"),
            role=UserRole.RECICLADOR,
            user_type_detail=UserTypeDetail.RECICLADOR_INDEPENDIENTE.value,
            neighborhood="El Bosque",
            address_reference="Carrera 104 # 95-20",
            habeas_data_accepted=True,
            habeas_data_timestamp=now,
            is_active=True,
            created_at=now,
        )

        rec2 = User(
            id=uuid.uuid4(),
            full_name="Asociación Recuperadores Urabá Verde",
            email="contacto@urabaverde.org",
            phone="3205556677",
            hashed_password=get_password_hash("AsociaUraba2026"),
            role=UserRole.RECICLADOR,
            user_type_detail=UserTypeDetail.ASOCIACION.value,
            neighborhood="Los Balsos",
            address_reference="Zona Industrial Bodega 2",
            habeas_data_accepted=True,
            habeas_data_timestamp=now,
            is_active=True,
            created_at=now,
        )

        # 3. ADMINISTRADOR MUNICIPAL PGIRS
        admin = User(
            id=uuid.uuid4(),
            full_name="Coordinador PGIRS Municipio",
            email="pgirs@alcaldia.gov.co",
            phone="3001239999",
            hashed_password=get_password_hash("AdminPgirs2026"),
            role=UserRole.ADMINISTRADOR,
            user_type_detail=UserTypeDetail.INSTITUCIONAL.value,
            neighborhood="Centro",
            address_reference="Alcaldía Municipal del municipio",
            habeas_data_accepted=True,
            habeas_data_timestamp=now,
            is_active=True,
            created_at=now,
        )

        session.add_all([gen1, gen2, gen3, rec1, rec2, admin])
        await session.flush()

        # 4. SOLICITUDES DE RECOLECCIÓN
        pickup1 = PickupRequest(
            id=uuid.uuid4(),
            generator_id=gen1.id,
            recycler_id=rec1.id,
            status=PickupStatus.ACEPTADA,
            waste_categories=[WasteCategory.PLASTICO.value, WasteCategory.PAPEL_CARTON.value],
            estimated_volume="1 a 2 bolsas medianas",
            latitude=7.6669,
            longitude=-76.6811,
            address_text=gen1.address_reference,
            photo_url="https://storage.ecoconecta.co/evidencias/bolsa_blanca_kennedy.jpg",
            notes="Tocar timbre o llamar al llegar",
            created_at=now,
            accepted_at=now,
        )

        pickup2 = PickupRequest(
            id=uuid.uuid4(),
            generator_id=gen2.id,
            recycler_id=rec1.id,
            status=PickupStatus.EN_CAMINO,
            waste_categories=[WasteCategory.PAPEL_CARTON.value, WasteCategory.METAL.value],
            estimated_volume="Más de 2 bultos comerciales",
            latitude=7.6710,
            longitude=-76.6830,
            address_text=gen2.address_reference,
            notes="Entrega por la zona de parqueaderos de cargue",
            created_at=now,
            accepted_at=now,
        )

        pickup3 = PickupRequest(
            id=uuid.uuid4(),
            generator_id=gen3.id,
            recycler_id=None,
            status=PickupStatus.PENDIENTE,
            waste_categories=[WasteCategory.VIDRIO.value],
            estimated_volume="1 bulto o costal",
            latitude=7.6745,
            longitude=-76.6780,
            address_text=gen3.address_reference,
            notes="Botellas de vidrio limpias y clasificadas",
            created_at=now,
        )

        session.add_all([pickup1, pickup2, pickup3])

        # 5. REGISTROS DE AUDITORÍA LEGAL (LEY 1581 DE 2012)
        audit_records = [
            AuditLog(
                user_id=gen1.id,
                event_type="HABEAS_DATA_ACCEPTANCE",
                policy_version="v1.0-2026-LEY1581",
                details=f"Consentimiento informado aceptado por {gen1.email} (Hogar, Barrio Kennedy).",
                created_at=now,
            ),
            AuditLog(
                user_id=gen2.id,
                event_type="HABEAS_DATA_ACCEPTANCE",
                policy_version="v1.0-2026-LEY1581",
                details=f"Consentimiento informado aceptado por {gen2.email} (Comercio, Sector Centro).",
                created_at=now,
            ),
            AuditLog(
                user_id=rec1.id,
                event_type="HABEAS_DATA_ACCEPTANCE",
                policy_version="v1.0-2026-LEY1581",
                details=f"Consentimiento informado aceptado por {rec1.email} (Reciclador de Oficio).",
                created_at=now,
            ),
            AuditLog(
                user_id=rec1.id,
                event_type="PICKUP_CLAIMED_ATOMIC",
                policy_version="v1.0-2026-LEY1581",
                details=f"Solicitud {pickup1.id} bloqueada y adjudicada a {rec1.full_name}.",
                created_at=now,
            ),
        ]
        session.add_all(audit_records)

        await session.commit()
        print("✅ Base de datos poblada exitosamente con actores, solicitudes y auditorías del municipio.")


if __name__ == "__main__":
    asyncio.run(seed_database())

