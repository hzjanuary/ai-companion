"""Authenticated, tenant-scoped SPEC-021 control-plane API."""

# FastAPI dependencies are intentionally declared at route boundaries.
# ruff: noqa: B008

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.domain.persistence import AssistantStatus, Platform, PlatformConnectionStatus
from app.infrastructure.database.models import (
    AssistantModel,
    ControlAssistantBindingModel,
    ControlAuditEventModel,
    ControlConnectionBindingModel,
    ControlGroupBindingModel,
    ControlGroupRevisionModel,
    ControlOperatorIdentityModel,
    ControlOperatorMembershipModel,
    ControlTenantModel,
    PlatformConnectionModel,
)
from app.interface.http.dependencies import database_session

Role = Literal["tenant_owner", "tenant_admin", "operator", "auditor", "viewer"]
WRITE_ROLES: set[str] = {"tenant_owner", "tenant_admin", "operator"}
ADMIN_ROLES: set[str] = {"tenant_owner", "tenant_admin"}


class ControlError(BaseModel):
    error_type: str
    message: str
    request_id: str


class TenantInput(BaseModel):
    slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=1, max_length=160)


class MembershipInput(BaseModel):
    issuer: str = Field(min_length=1, max_length=255)
    subject: str = Field(min_length=1, max_length=255)
    role: Role
    display_name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=320)


class AssistantInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class AssistantPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)


class ConnectionInput(BaseModel):
    assistant_id: UUID
    platform: str = Field(min_length=1, max_length=32)
    external_bot_id: str = Field(min_length=1, max_length=255)
    credential_reference: str | None = Field(default=None, max_length=255)


class ConnectionPatch(BaseModel):
    credential_reference: str | None = Field(default=None, max_length=255)
    status: Literal["active", "disabled", "error"] | None = None


class GroupPatch(BaseModel):
    settings: dict[str, Any]
    reason: str | None = Field(default=None, max_length=255)
    expected_revision: int = Field(ge=0)


@dataclass(frozen=True)
class Principal:
    identity: ControlOperatorIdentityModel
    claims: dict[str, Any]


def settings_for(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def request_id_for(request: Request) -> str:
    return cast(str, getattr(request.state, "request_id", "unknown"))


async def principal_for(
    request: Request,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(database_session),
) -> Principal:
    settings = settings_for(request)
    if not settings.control_plane_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        claims = jwt.decode(
            token,
            settings.control_plane_jwt_secret.get_secret_value()
            if settings.control_plane_jwt_secret
            else "",
            algorithms=["HS256"],
            issuer=settings.control_plane_jwt_issuer,
            audience=settings.control_plane_jwt_audience,
            options={"require": ["iss", "sub", "aud", "exp"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Authentication required") from exc
    issuer = cast(str, claims["iss"])
    subject = cast(str, claims["sub"])
    identity = await session.scalar(
        select(ControlOperatorIdentityModel).where(
            ControlOperatorIdentityModel.issuer == issuer,
            ControlOperatorIdentityModel.subject == subject,
        )
    )
    if identity is None:
        identity = ControlOperatorIdentityModel(
            issuer=issuer,
            subject=subject,
            display_name=claims.get("name"),
            email=claims.get("email"),
        )
        session.add(identity)
        await session.flush()
    if identity.disabled_at is not None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return Principal(identity=identity, claims=claims)


async def membership_for(
    session: AsyncSession, principal: Principal, tenant_id: UUID
) -> ControlOperatorMembershipModel:
    membership = await session.scalar(
        select(ControlOperatorMembershipModel).where(
            ControlOperatorMembershipModel.tenant_id == tenant_id,
            ControlOperatorMembershipModel.identity_id == principal.identity.id,
            ControlOperatorMembershipModel.disabled_at.is_(None),
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Not found")
    return membership


async def audit(
    session: AsyncSession,
    request: Request,
    tenant_id: UUID,
    principal: Principal,
    action: str,
    outcome: str,
    resource_type: str,
    resource_id: UUID | None = None,
) -> None:
    session.add(
        ControlAuditEventModel(
            tenant_id=tenant_id,
            actor_identity_id=principal.identity.id,
            action=action,
            outcome=outcome,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            request_id=request_id_for(request),
            metadata_={"schema_version": "spec-021-v1"},
        )
    )


def tenant_body(tenant: ControlTenantModel) -> dict[str, Any]:
    return {
        "id": str(tenant.id),
        "slug": tenant.slug,
        "name": tenant.name,
        "status": tenant.status,
    }


def create_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/control/v1", tags=["control-plane"])

    @router.get("/session")
    async def session_info(
        request: Request, principal: Principal = Depends(principal_for)
    ) -> dict[str, Any]:
        return {
            "authenticated": True,
            "issuer": principal.identity.issuer,
            "subject": principal.identity.subject,
        }

    @router.post("/session/logout", status_code=status.HTTP_204_NO_CONTENT)
    async def logout(_: Principal = Depends(principal_for)) -> None:
        return None

    @router.get("/me")
    async def me(
        principal: Principal = Depends(principal_for),
        session: AsyncSession = Depends(database_session),
    ) -> dict[str, Any]:
        memberships = (
            await session.scalars(
                select(ControlOperatorMembershipModel).where(
                    ControlOperatorMembershipModel.identity_id == principal.identity.id,
                    ControlOperatorMembershipModel.disabled_at.is_(None),
                )
            )
        ).all()
        return {
            "issuer": principal.identity.issuer,
            "subject": principal.identity.subject,
            "display_name": principal.identity.display_name,
            "email": principal.identity.email,
            "memberships": [
                {"tenant_id": str(item.tenant_id), "role": item.role}
                for item in memberships
            ],
        }

    @router.get("/tenants")
    async def list_tenants(
        principal: Principal = Depends(principal_for),
        session: AsyncSession = Depends(database_session),
    ) -> dict[str, Any]:
        rows = await session.execute(
            select(ControlTenantModel, ControlOperatorMembershipModel.role)
            .join(
                ControlOperatorMembershipModel,
                ControlOperatorMembershipModel.tenant_id == ControlTenantModel.id,
            )
            .where(
                ControlOperatorMembershipModel.identity_id == principal.identity.id,
                ControlOperatorMembershipModel.disabled_at.is_(None),
            )
        )
        return {
            "items": [
                {**tenant_body(tenant), "role": role} for tenant, role in rows.all()
            ]
        }

    @router.post("/tenants", status_code=201)
    async def create_tenant(
        payload: TenantInput,
        request: Request,
        principal: Principal = Depends(principal_for),
        session: AsyncSession = Depends(database_session),
    ) -> dict[str, Any]:
        count = await session.scalar(
            select(func.count()).select_from(ControlTenantModel)
        )
        if count != 0:
            raise HTTPException(status_code=403, detail="Forbidden")
        tenant = ControlTenantModel(slug=payload.slug, name=payload.name)
        session.add(tenant)
        await session.flush()
        session.add(
            ControlOperatorMembershipModel(
                tenant_id=tenant.id,
                identity_id=principal.identity.id,
                role="tenant_owner",
            )
        )
        await audit(
            session,
            request,
            tenant.id,
            principal,
            "tenant.create",
            "success",
            "tenant",
            tenant.id,
        )
        await session.commit()
        return tenant_body(tenant)

    @router.get("/tenants/{tenant_id}/members")
    async def list_members(
        tenant_id: UUID,
        principal: Principal = Depends(principal_for),
        session: AsyncSession = Depends(database_session),
    ) -> dict[str, Any]:
        await membership_for(session, principal, tenant_id)
        rows = await session.execute(
            select(ControlOperatorMembershipModel, ControlOperatorIdentityModel)
            .join(
                ControlOperatorIdentityModel,
                ControlOperatorIdentityModel.id
                == ControlOperatorMembershipModel.identity_id,
            )
            .where(
                ControlOperatorMembershipModel.tenant_id == tenant_id,
                ControlOperatorMembershipModel.disabled_at.is_(None),
            )
        )
        return {
            "items": [
                {
                    "id": str(identity.id),
                    "issuer": identity.issuer,
                    "subject": identity.subject,
                    "display_name": identity.display_name,
                    "email": identity.email,
                    "role": membership.role,
                }
                for membership, identity in rows.all()
            ]
        }

    @router.post("/tenants/{tenant_id}/members", status_code=201)
    async def add_member(
        tenant_id: UUID,
        payload: MembershipInput,
        request: Request,
        principal: Principal = Depends(principal_for),
        session: AsyncSession = Depends(database_session),
    ) -> dict[str, Any]:
        actor = await membership_for(session, principal, tenant_id)
        if actor.role not in ADMIN_ROLES or (
            payload.role == "tenant_owner" and actor.role != "tenant_owner"
        ):
            raise HTTPException(status_code=403, detail="Forbidden")
        identity = await session.scalar(
            select(ControlOperatorIdentityModel).where(
                ControlOperatorIdentityModel.issuer == payload.issuer,
                ControlOperatorIdentityModel.subject == payload.subject,
            )
        )
        if identity is None:
            identity = ControlOperatorIdentityModel(
                issuer=payload.issuer,
                subject=payload.subject,
                display_name=payload.display_name,
                email=payload.email,
            )
            session.add(identity)
            await session.flush()
        member = ControlOperatorMembershipModel(
            tenant_id=tenant_id, identity_id=identity.id, role=payload.role
        )
        session.add(member)
        await audit(
            session,
            request,
            tenant_id,
            principal,
            "member.add",
            "success",
            "membership",
            identity.id,
        )
        await session.commit()
        return {
            "id": str(identity.id),
            "issuer": identity.issuer,
            "subject": identity.subject,
            "role": member.role,
        }

    @router.delete("/tenants/{tenant_id}/members/{identity_id}", status_code=204)
    async def remove_member(
        tenant_id: UUID,
        identity_id: UUID,
        request: Request,
        principal: Principal = Depends(principal_for),
        session: AsyncSession = Depends(database_session),
    ) -> None:
        actor = await membership_for(session, principal, tenant_id)
        if actor.role not in ADMIN_ROLES:
            raise HTTPException(status_code=403, detail="Forbidden")
        member = await session.scalar(
            select(ControlOperatorMembershipModel).where(
                ControlOperatorMembershipModel.tenant_id == tenant_id,
                ControlOperatorMembershipModel.identity_id == identity_id,
                ControlOperatorMembershipModel.disabled_at.is_(None),
            )
        )
        if member is None:
            raise HTTPException(status_code=404, detail="Not found")
        if member.role == "tenant_owner":
            owners = await session.scalar(
                select(func.count())
                .select_from(ControlOperatorMembershipModel)
                .where(
                    ControlOperatorMembershipModel.tenant_id == tenant_id,
                    ControlOperatorMembershipModel.role == "tenant_owner",
                    ControlOperatorMembershipModel.disabled_at.is_(None),
                )
            )
            if owners == 1:
                raise HTTPException(
                    status_code=409, detail="Last owner cannot be removed"
                )
        member.disabled_at = datetime.now(UTC)
        await audit(
            session,
            request,
            tenant_id,
            principal,
            "member.remove",
            "success",
            "membership",
            identity_id,
        )
        await session.commit()

    @router.get("/tenants/{tenant_id}/assistants")
    async def list_assistants(
        tenant_id: UUID,
        principal: Principal = Depends(principal_for),
        session: AsyncSession = Depends(database_session),
    ) -> dict[str, Any]:
        await membership_for(session, principal, tenant_id)
        rows = await session.execute(
            select(AssistantModel, ControlAssistantBindingModel)
            .join(
                ControlAssistantBindingModel,
                ControlAssistantBindingModel.assistant_id == AssistantModel.id,
            )
            .where(ControlAssistantBindingModel.tenant_id == tenant_id)
        )
        return {
            "items": [
                {
                    "id": str(assistant.id),
                    "name": assistant.name,
                    "status": assistant.status.value,
                }
                for assistant, _ in rows.all()
            ]
        }

    @router.post("/tenants/{tenant_id}/assistants", status_code=201)
    async def create_assistant(
        tenant_id: UUID,
        payload: AssistantInput,
        request: Request,
        principal: Principal = Depends(principal_for),
        session: AsyncSession = Depends(database_session),
    ) -> dict[str, Any]:
        member = await membership_for(session, principal, tenant_id)
        if member.role not in WRITE_ROLES:
            raise HTTPException(status_code=403, detail="Forbidden")
        assistant = AssistantModel(name=payload.name)
        session.add(assistant)
        await session.flush()
        session.add(
            ControlAssistantBindingModel(tenant_id=tenant_id, assistant_id=assistant.id)
        )
        await audit(
            session,
            request,
            tenant_id,
            principal,
            "assistant.create",
            "success",
            "assistant",
            assistant.id,
        )
        await session.commit()
        return {
            "id": str(assistant.id),
            "name": assistant.name,
            "status": assistant.status.value,
        }

    @router.patch("/tenants/{tenant_id}/assistants/{assistant_id}")
    async def update_assistant(
        tenant_id: UUID,
        assistant_id: UUID,
        payload: AssistantPatch,
        request: Request,
        principal: Principal = Depends(principal_for),
        session: AsyncSession = Depends(database_session),
    ) -> dict[str, Any]:
        member = await membership_for(session, principal, tenant_id)
        if member.role not in WRITE_ROLES:
            raise HTTPException(status_code=403, detail="Forbidden")
        binding = await session.scalar(
            select(ControlAssistantBindingModel).where(
                ControlAssistantBindingModel.tenant_id == tenant_id,
                ControlAssistantBindingModel.assistant_id == assistant_id,
            )
        )
        assistant = await session.get(AssistantModel, assistant_id)
        if binding is None or assistant is None:
            raise HTTPException(status_code=404, detail="Not found")
        if payload.name is not None:
            assistant.name = payload.name
        await audit(
            session,
            request,
            tenant_id,
            principal,
            "assistant.update",
            "success",
            "assistant",
            assistant.id,
        )
        await session.commit()
        return {
            "id": str(assistant.id),
            "name": assistant.name,
            "status": assistant.status.value,
        }

    @router.get("/tenants/{tenant_id}/assistants/{assistant_id}/status")
    async def assistant_status(
        tenant_id: UUID,
        assistant_id: UUID,
        principal: Principal = Depends(principal_for),
        session: AsyncSession = Depends(database_session),
    ) -> dict[str, Any]:
        await membership_for(session, principal, tenant_id)
        binding = await session.scalar(
            select(ControlAssistantBindingModel).where(
                ControlAssistantBindingModel.tenant_id == tenant_id,
                ControlAssistantBindingModel.assistant_id == assistant_id,
            )
        )
        assistant = await session.get(AssistantModel, assistant_id)
        if binding is None or assistant is None:
            raise HTTPException(status_code=404, detail="Not found")
        return {"assistant_id": str(assistant.id), "status": assistant.status.value}

    @router.delete("/tenants/{tenant_id}/assistants/{assistant_id}", status_code=204)
    async def disable_assistant(
        tenant_id: UUID,
        assistant_id: UUID,
        request: Request,
        principal: Principal = Depends(principal_for),
        session: AsyncSession = Depends(database_session),
    ) -> None:
        member = await membership_for(session, principal, tenant_id)
        if member.role not in ADMIN_ROLES:
            raise HTTPException(status_code=403, detail="Forbidden")
        binding = await session.scalar(
            select(ControlAssistantBindingModel).where(
                ControlAssistantBindingModel.tenant_id == tenant_id,
                ControlAssistantBindingModel.assistant_id == assistant_id,
            )
        )
        assistant = await session.get(AssistantModel, assistant_id)
        if binding is None or assistant is None:
            raise HTTPException(status_code=404, detail="Not found")
        assistant.status = AssistantStatus.DISABLED
        await audit(
            session,
            request,
            tenant_id,
            principal,
            "assistant.disable",
            "success",
            "assistant",
            assistant.id,
        )
        await session.commit()

    @router.delete("/tenants/{tenant_id}/connections/{connection_id}", status_code=204)
    async def disable_connection(
        tenant_id: UUID,
        connection_id: UUID,
        request: Request,
        principal: Principal = Depends(principal_for),
        session: AsyncSession = Depends(database_session),
    ) -> None:
        member = await membership_for(session, principal, tenant_id)
        if member.role not in ADMIN_ROLES:
            raise HTTPException(status_code=403, detail="Forbidden")
        binding = await session.scalar(
            select(ControlConnectionBindingModel).where(
                ControlConnectionBindingModel.tenant_id == tenant_id,
                ControlConnectionBindingModel.connection_id == connection_id,
            )
        )
        connection = await session.get(PlatformConnectionModel, connection_id)
        if binding is None or connection is None:
            raise HTTPException(status_code=404, detail="Not found")
        connection.status = PlatformConnectionStatus.DISABLED
        await audit(
            session,
            request,
            tenant_id,
            principal,
            "connection.disable",
            "success",
            "connection",
            connection.id,
        )
        await session.commit()

    @router.get("/tenants/{tenant_id}/connections")
    async def list_connections(
        tenant_id: UUID,
        principal: Principal = Depends(principal_for),
        session: AsyncSession = Depends(database_session),
    ) -> dict[str, Any]:
        await membership_for(session, principal, tenant_id)
        rows = await session.execute(
            select(PlatformConnectionModel)
            .join(
                ControlConnectionBindingModel,
                ControlConnectionBindingModel.connection_id
                == PlatformConnectionModel.id,
            )
            .where(ControlConnectionBindingModel.tenant_id == tenant_id)
        )
        return {
            "items": [
                {
                    "id": str(connection.id),
                    "assistant_id": str(connection.assistant_id),
                    "platform": connection.platform.value,
                    "external_bot_id": connection.external_bot_id,
                    "status": connection.status.value,
                    "credential_configured": connection.credential_reference
                    is not None,
                }
                for (connection,) in rows.all()
            ]
        }

    @router.post("/tenants/{tenant_id}/connections", status_code=201)
    async def create_connection(
        tenant_id: UUID,
        payload: ConnectionInput,
        request: Request,
        principal: Principal = Depends(principal_for),
        session: AsyncSession = Depends(database_session),
    ) -> dict[str, Any]:
        member = await membership_for(session, principal, tenant_id)
        if member.role not in WRITE_ROLES:
            raise HTTPException(status_code=403, detail="Forbidden")
        assistant_binding = await session.scalar(
            select(ControlAssistantBindingModel).where(
                ControlAssistantBindingModel.tenant_id == tenant_id,
                ControlAssistantBindingModel.assistant_id == payload.assistant_id,
            )
        )
        if assistant_binding is None:
            raise HTTPException(status_code=404, detail="Not found")
        try:
            platform = Platform(payload.platform)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid platform") from exc
        connection = PlatformConnectionModel(
            assistant_id=payload.assistant_id,
            platform=platform,
            external_bot_id=payload.external_bot_id,
            status=PlatformConnectionStatus.ACTIVE,
            credential_reference=payload.credential_reference,
        )
        session.add(connection)
        await session.flush()
        session.add(
            ControlConnectionBindingModel(
                tenant_id=tenant_id, connection_id=connection.id
            )
        )
        await audit(
            session,
            request,
            tenant_id,
            principal,
            "connection.create",
            "success",
            "connection",
            connection.id,
        )
        await session.commit()
        return {
            "id": str(connection.id),
            "assistant_id": str(connection.assistant_id),
            "platform": connection.platform.value,
            "external_bot_id": connection.external_bot_id,
            "status": connection.status.value,
            "credential_configured": connection.credential_reference is not None,
        }

    @router.patch("/tenants/{tenant_id}/connections/{connection_id}")
    async def update_connection(
        tenant_id: UUID,
        connection_id: UUID,
        payload: ConnectionPatch,
        request: Request,
        principal: Principal = Depends(principal_for),
        session: AsyncSession = Depends(database_session),
    ) -> dict[str, Any]:
        member = await membership_for(session, principal, tenant_id)
        if member.role not in WRITE_ROLES:
            raise HTTPException(status_code=403, detail="Forbidden")
        binding = await session.scalar(
            select(ControlConnectionBindingModel).where(
                ControlConnectionBindingModel.tenant_id == tenant_id,
                ControlConnectionBindingModel.connection_id == connection_id,
            )
        )
        connection = await session.get(PlatformConnectionModel, connection_id)
        if binding is None or connection is None:
            raise HTTPException(status_code=404, detail="Not found")
        if payload.credential_reference is not None:
            connection.credential_reference = payload.credential_reference
        if payload.status is not None:
            connection.status = PlatformConnectionStatus(payload.status)
        await audit(
            session,
            request,
            tenant_id,
            principal,
            "connection.update",
            "success",
            "connection",
            connection.id,
        )
        await session.commit()
        return {
            "id": str(connection.id),
            "assistant_id": str(connection.assistant_id),
            "platform": connection.platform.value,
            "external_bot_id": connection.external_bot_id,
            "status": connection.status.value,
            "credential_configured": connection.credential_reference is not None,
        }

    @router.post("/tenants/{tenant_id}/connections/{connection_id}/rotate")
    async def rotate_connection(
        tenant_id: UUID,
        connection_id: UUID,
        request: Request,
        principal: Principal = Depends(principal_for),
        session: AsyncSession = Depends(database_session),
    ) -> dict[str, Any]:
        member = await membership_for(session, principal, tenant_id)
        if member.role not in ADMIN_ROLES:
            raise HTTPException(status_code=403, detail="Forbidden")
        binding = await session.scalar(
            select(ControlConnectionBindingModel).where(
                ControlConnectionBindingModel.tenant_id == tenant_id,
                ControlConnectionBindingModel.connection_id == connection_id,
            )
        )
        connection = await session.get(PlatformConnectionModel, connection_id)
        if binding is None or connection is None:
            raise HTTPException(status_code=404, detail="Not found")
        await audit(
            session,
            request,
            tenant_id,
            principal,
            "connection.rotate",
            "pending",
            "connection",
            connection.id,
        )
        await session.commit()
        return {"operation": "pending", "connection_id": str(connection.id)}

    @router.get("/tenants/{tenant_id}/connections/{connection_id}/status")
    async def connection_status(
        tenant_id: UUID,
        connection_id: UUID,
        principal: Principal = Depends(principal_for),
        session: AsyncSession = Depends(database_session),
    ) -> dict[str, Any]:
        await membership_for(session, principal, tenant_id)
        binding = await session.scalar(
            select(ControlConnectionBindingModel).where(
                ControlConnectionBindingModel.tenant_id == tenant_id,
                ControlConnectionBindingModel.connection_id == connection_id,
            )
        )
        connection = await session.get(PlatformConnectionModel, connection_id)
        if binding is None or connection is None:
            raise HTTPException(status_code=404, detail="Not found")
        return {"connection_id": str(connection.id), "status": connection.status.value}

    @router.post("/tenants/{tenant_id}/groups/{group_id}/restore/{revision}")
    async def restore_group(
        tenant_id: UUID,
        group_id: UUID,
        revision: int,
        request: Request,
        principal: Principal = Depends(principal_for),
        session: AsyncSession = Depends(database_session),
    ) -> dict[str, Any]:
        member = await membership_for(session, principal, tenant_id)
        if member.role not in WRITE_ROLES:
            raise HTTPException(status_code=403, detail="Forbidden")
        group = await session.scalar(
            select(ControlGroupBindingModel).where(
                ControlGroupBindingModel.id == group_id,
                ControlGroupBindingModel.tenant_id == tenant_id,
            )
        )
        source = await session.scalar(
            select(ControlGroupRevisionModel).where(
                ControlGroupRevisionModel.group_id == group_id,
                ControlGroupRevisionModel.revision == revision,
            )
        )
        if group is None or source is None:
            raise HTTPException(status_code=404, detail="Not found")
        next_revision = group.current_revision + 1
        session.add(
            ControlGroupRevisionModel(
                group_id=group.id,
                revision=next_revision,
                parent_revision=group.current_revision or None,
                settings=source.settings,
                actor_identity_id=principal.identity.id,
                reason=f"restore:{revision}",
            )
        )
        group.settings = source.settings
        group.current_revision = next_revision
        await audit(
            session,
            request,
            tenant_id,
            principal,
            "group.configuration.restore",
            "success",
            "group",
            group.id,
        )
        await session.commit()
        return {
            "id": str(group.id),
            "revision": next_revision,
            "settings": group.settings,
        }

    @router.get("/tenants/{tenant_id}/groups/{group_id}/revisions")
    async def group_revisions(
        tenant_id: UUID,
        group_id: UUID,
        principal: Principal = Depends(principal_for),
        session: AsyncSession = Depends(database_session),
    ) -> dict[str, Any]:
        await membership_for(session, principal, tenant_id)
        group = await session.scalar(
            select(ControlGroupBindingModel).where(
                ControlGroupBindingModel.id == group_id,
                ControlGroupBindingModel.tenant_id == tenant_id,
            )
        )
        if group is None:
            raise HTTPException(status_code=404, detail="Not found")
        revisions = (
            await session.scalars(
                select(ControlGroupRevisionModel)
                .where(ControlGroupRevisionModel.group_id == group_id)
                .order_by(ControlGroupRevisionModel.revision.desc())
            )
        ).all()
        return {
            "items": [
                {
                    "id": str(item.id),
                    "revision": item.revision,
                    "parent_revision": item.parent_revision,
                    "settings": item.settings,
                    "reason": item.reason,
                }
                for item in revisions
            ]
        }

    @router.get("/tenants/{tenant_id}/groups")
    async def list_groups(
        tenant_id: UUID,
        principal: Principal = Depends(principal_for),
        session: AsyncSession = Depends(database_session),
    ) -> dict[str, Any]:
        await membership_for(session, principal, tenant_id)
        groups = (
            await session.scalars(
                select(ControlGroupBindingModel).where(
                    ControlGroupBindingModel.tenant_id == tenant_id
                )
            )
        ).all()
        return {
            "items": [
                {
                    "id": str(group.id),
                    "connection_id": str(group.connection_id),
                    "external_group_id": group.external_group_id,
                    "title": group.title,
                    "revision": group.current_revision,
                    "settings": group.settings,
                }
                for group in groups
            ]
        }

    @router.get("/tenants/{tenant_id}/groups/{group_id}")
    async def get_group(
        tenant_id: UUID,
        group_id: UUID,
        principal: Principal = Depends(principal_for),
        session: AsyncSession = Depends(database_session),
    ) -> dict[str, Any]:
        await membership_for(session, principal, tenant_id)
        group = await session.scalar(
            select(ControlGroupBindingModel).where(
                ControlGroupBindingModel.id == group_id,
                ControlGroupBindingModel.tenant_id == tenant_id,
            )
        )
        if group is None:
            raise HTTPException(status_code=404, detail="Not found")
        return {
            "id": str(group.id),
            "connection_id": str(group.connection_id),
            "external_group_id": group.external_group_id,
            "title": group.title,
            "revision": group.current_revision,
            "settings": group.settings,
        }

    @router.patch("/tenants/{tenant_id}/groups/{group_id}")
    async def update_group(
        tenant_id: UUID,
        group_id: UUID,
        payload: GroupPatch,
        request: Request,
        principal: Principal = Depends(principal_for),
        session: AsyncSession = Depends(database_session),
    ) -> dict[str, Any]:
        member = await membership_for(session, principal, tenant_id)
        if member.role not in WRITE_ROLES:
            raise HTTPException(status_code=403, detail="Forbidden")
        group = await session.scalar(
            select(ControlGroupBindingModel).where(
                ControlGroupBindingModel.id == group_id,
                ControlGroupBindingModel.tenant_id == tenant_id,
            )
        )
        if group is None:
            raise HTTPException(status_code=404, detail="Not found")
        if payload.expected_revision != group.current_revision:
            raise HTTPException(status_code=409, detail="Revision conflict")
        revision = group.current_revision + 1
        session.add(
            ControlGroupRevisionModel(
                group_id=group.id,
                revision=revision,
                parent_revision=group.current_revision or None,
                settings=payload.settings,
                actor_identity_id=principal.identity.id,
                reason=payload.reason,
            )
        )
        group.settings = payload.settings
        group.current_revision = revision
        await audit(
            session,
            request,
            tenant_id,
            principal,
            "group.configuration.update",
            "success",
            "group",
            group.id,
        )
        await session.commit()
        return {"id": str(group.id), "revision": revision, "settings": group.settings}

    @router.get("/tenants/{tenant_id}/audit-events")
    async def audit_events(
        tenant_id: UUID,
        principal: Principal = Depends(principal_for),
        session: AsyncSession = Depends(database_session),
    ) -> dict[str, Any]:
        member = await membership_for(session, principal, tenant_id)
        if member.role not in ADMIN_ROLES | {"auditor"}:
            raise HTTPException(status_code=403, detail="Forbidden")
        events = (
            await session.scalars(
                select(ControlAuditEventModel)
                .where(ControlAuditEventModel.tenant_id == tenant_id)
                .order_by(ControlAuditEventModel.created_at.desc())
                .limit(100)
            )
        ).all()
        return {
            "items": [
                {
                    "id": str(event.id),
                    "action": event.action,
                    "outcome": event.outcome,
                    "resource_type": event.resource_type,
                    "resource_id": event.resource_id,
                    "request_id": event.request_id,
                    "metadata": event.metadata_,
                }
                for event in events
            ]
        }

    return router
