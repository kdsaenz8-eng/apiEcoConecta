"""Migración inicial de esquema EcoConecta (TRL 5): users, pickup_requests y audit_logs.

Revision ID: 001_initial_schema
Revises: None
Create Date: 2026-11-08 14:15:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    user_role_enum = postgresql.ENUM(
        "GENERADOR", "RECICLADOR", "ADMINISTRADOR", name="user_role_enum", create_type=False
    )
    pickup_status_enum = postgresql.ENUM(
        "PENDIENTE",
        "ACEPTADA",
        "EN_CAMINO",
        "COMPLETADA",
        "CANCELADA",
        name="pickup_status_enum",
        create_type=False,
    )
    user_role_enum.create(op.get_bind(), checkfirst=True)
    pickup_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", user_role_enum, nullable=False),
        sa.Column("user_type_detail", sa.String(length=50), nullable=False),
        sa.Column("neighborhood", sa.String(length=100), nullable=False),
        sa.Column("address_reference", sa.String(length=255), nullable=False),
        sa.Column("habeas_data_accepted", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("habeas_data_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"], unique=False)
    op.create_index("ix_users_neighborhood", "users", ["neighborhood"], unique=False)
    op.create_index("ix_users_role_neighborhood", "users", ["role", "neighborhood"], unique=False)

    op.create_table(
        "pickup_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "generator_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recycler_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", pickup_status_enum, nullable=False),
        sa.Column("waste_categories", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("estimated_volume", sa.String(length=120), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("address_text", sa.String(length=255), nullable=False),
        sa.Column("photo_url", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_pickup_requests_generator_id", "pickup_requests", ["generator_id"])
    op.create_index("ix_pickup_requests_recycler_id", "pickup_requests", ["recycler_id"])
    op.create_index("ix_pickup_requests_status", "pickup_requests", ["status"])
    op.create_index("ix_pickup_requests_latitude", "pickup_requests", ["latitude"])
    op.create_index("ix_pickup_requests_longitude", "pickup_requests", ["longitude"])
    op.create_index(
        "ix_pickup_status_coords",
        "pickup_requests",
        ["status", "latitude", "longitude"],
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("policy_version", sa.String(length=40), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_event_type", "audit_logs", ["event_type"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("pickup_requests")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS pickup_status_enum")
    op.execute("DROP TYPE IF EXISTS user_role_enum")

