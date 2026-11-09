"""
Endpoints de Registro Abierto, Autenticación OAuth2/JWT y Perfil de Usuario (app/api/v1/endpoints/auth.py).
Implementa la HU-01 con auditoría legal de aceptación de la Ley 1581 de 2012 (Habeas Data Colombia).
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)
from app.models.audit_log import AuditLog
from app.models.user import User, UserTypeDetail
from app.schemas.user import (
    TokenResponse,
    UserCreate,
    UserLogin,
    UserPublicResponse,
)

router = APIRouter(prefix="/auth", tags=["Autenticación y Registro Abierto"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")


async def get_current_active_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependencia de seguridad que valida el token JWT Bearer y retorna la entidad User activa.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales o el token ha expirado.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        subject: str | None = payload.get("sub")
        if subject is None:
            raise credentials_exception
        user_uuid = UUID(subject)
    except (JWTError, ValueError) as exc:
        raise credentials_exception from exc

    stmt = select(User).where(User.id == user_uuid)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta del usuario se encuentra inactiva.",
        )
    return user


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registro público de Generadores y Recicladores en el municipio",
)
async def register_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Registra un nuevo usuario (`GENERADOR` o `RECICLADOR`), audita la aceptación explícita
    de la Política de Tratamiento de Datos Personales (Ley 1581 de 2012) y emite un JWT inmediato.
    """
    if not payload.habeas_data_accepted:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Debe aceptar expresamente la Política de Tratamiento de Datos Personales (Ley 1581/2012).",
        )

    # Verificar unicidad del correo electrónico (HTTP 409 Conflict si ya existe)
    normalized_email = payload.email.lower().strip()
    existing_stmt = select(User).where(User.email == normalized_email)
    existing_result = await db.execute(existing_stmt)
    if existing_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El correo electrónico suministrado ya se encuentra registrado en EcoConecta.",
        )

    acceptance_time = datetime.now(timezone.utc)
    new_user = User(
        full_name=payload.full_name.strip(),
        email=normalized_email,
        phone=payload.phone.strip(),
        hashed_password=get_password_hash(payload.password),
        role=payload.role,
        user_type_detail=payload.user_type_detail or UserTypeDetail.HOGAR.value,
        neighborhood=payload.neighborhood.strip(),
        address_reference=payload.address_reference.strip(),
        habeas_data_accepted=True,
        habeas_data_timestamp=acceptance_time,
        is_active=True,
    )
    db.add(new_user)
    await db.flush()

    # Registro de auditoría legal (Ley 1581 de 2012)
    audit_entry = AuditLog(
        user_id=new_user.id,
        event_type="HABEAS_DATA_ACCEPTANCE",
        policy_version=settings.PRIVACY_POLICY_VERSION,
        details=(
            f"Consentimiento informado aceptado por {new_user.email} con rol {new_user.role.value} "
            f"en el barrio {new_user.neighborhood} (Municipio)."
        ),
        created_at=acceptance_time,
    )
    db.add(audit_entry)
    await db.commit()
    await db.refresh(new_user)

    access_token = create_access_token(
        subject=str(new_user.id),
        role=new_user.role.value,
    )
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        role=new_user.role,
        user=UserPublicResponse.model_validate(new_user),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Autenticación mediante credenciales y emisión de JWT con rol",
)
async def login_user(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Autentica al usuario mediante correo y contraseña, verifica que la cuenta esté activa
    y retorna el token JWT cuyo payload incluye `sub` (user_id) y `role`.
    """
    normalized_email = credentials.email.lower().strip()
    stmt = select(User).where(User.email == normalized_email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo electrónico o contraseña incorrectos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Su cuenta ha sido desactivada. Contacte al administrador del PGIRS.",
        )

    access_token = create_access_token(
        subject=str(user.id),
        role=user.role.value,
    )
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        role=user.role,
        user=UserPublicResponse.model_validate(user),
    )


@router.get(
    "/me",
    response_model=UserPublicResponse,
    summary="Obtener el perfil del usuario actualmente autenticado",
)
async def read_current_user_profile(
    current_user: User = Depends(get_current_active_user),
) -> UserPublicResponse:
    """Retorna la información pública y el rol del usuario autenticado."""
    return UserPublicResponse.model_validate(current_user)

