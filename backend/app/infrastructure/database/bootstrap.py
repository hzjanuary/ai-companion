"""Transactional, credential-free Assistant and Telegram connection bootstrap."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.bootstrap import BootstrapResult
from app.application.ports.platform import BotIdentity
from app.core.config import Settings
from app.domain.persistence import AssistantStatus, Platform, PlatformConnectionStatus
from app.infrastructure.database.models import AssistantModel, PlatformConnectionModel
from app.infrastructure.database.personality import ensure_assistant_default


class BootstrapConflictError(RuntimeError):
    pass


class SqlAlchemyOperatorBootstrap:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def reconcile(
        self, settings: Settings, identity: BotIdentity
    ) -> BootstrapResult:
        if not identity.is_bot or identity.platform != Platform.TELEGRAM:
            raise BootstrapConflictError("configured Telegram identity is not a bot")
        async with self._session_factory() as session:
            async with session.begin():
                configured = (
                    await session.get(
                        PlatformConnectionModel,
                        settings.telegram_platform_connection_id,
                    )
                    if settings.telegram_platform_connection_id is not None
                    else None
                )
                if (
                    configured is not None
                    and configured.external_bot_id != identity.external_bot_id
                ):
                    raise BootstrapConflictError(
                        "configured platform connection belongs to another bot"
                    )
                connection = await session.scalar(
                    select(PlatformConnectionModel).where(
                        PlatformConnectionModel.platform == Platform.TELEGRAM,
                        PlatformConnectionModel.external_bot_id
                        == identity.external_bot_id,
                    )
                )
                if (
                    configured is not None
                    and connection is not None
                    and configured.id != connection.id
                ):
                    raise BootstrapConflictError("conflicting Telegram connection rows")
                if connection is not None:
                    assistant = await session.get(
                        AssistantModel, connection.assistant_id
                    )
                    if assistant is None or assistant.name != settings.app_name:
                        raise BootstrapConflictError(
                            "existing bot connection belongs to another Assistant"
                        )
                    if (
                        connection.status != PlatformConnectionStatus.ACTIVE
                        or assistant.status != AssistantStatus.ACTIVE
                    ):
                        raise BootstrapConflictError(
                            "existing Assistant or platform connection is inactive"
                        )
                else:
                    assistants = list(
                        await session.scalars(
                            select(AssistantModel).where(
                                AssistantModel.name == settings.app_name
                            )
                        )
                    )
                    if len(assistants) > 1:
                        raise BootstrapConflictError(
                            "conflicting duplicate Assistant rows"
                        )
                    assistant = assistants[0] if assistants else None
                    if (
                        assistant is not None
                        and assistant.status != AssistantStatus.ACTIVE
                    ):
                        raise BootstrapConflictError("existing Assistant is inactive")
                    if assistant is None:
                        assistant = AssistantModel(
                            name=settings.app_name, status=AssistantStatus.ACTIVE
                        )
                        session.add(assistant)
                        await session.flush()
                    connection = PlatformConnectionModel(
                        assistant_id=assistant.id,
                        platform=Platform.TELEGRAM,
                        external_bot_id=identity.external_bot_id,
                        credential_reference="env:JANUARY_TELEGRAM_BOT_TOKEN",
                    )
                    session.add(connection)
                    await session.flush()
                connection.status = PlatformConnectionStatus.ACTIVE
                connection.configuration = {
                    "username": identity.username,
                    "display_name": identity.display_name,
                    "can_join_groups": identity.can_join_groups,
                    "can_read_all_group_messages": identity.can_read_all_group_messages,
                }
                await ensure_assistant_default(session, assistant)
                return BootstrapResult(
                    assistant.id,
                    connection.id,
                    identity.external_bot_id,
                    identity.username,
                    identity.display_name,
                    identity.can_join_groups,
                    identity.can_read_all_group_messages,
                )
