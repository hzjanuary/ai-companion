import asyncio

import pytest
from sqlalchemy import func, select, text

from app.application.ports.platform import BotIdentity
from app.core.config import Settings
from app.domain.persistence import Platform, PlatformConnectionStatus
from app.infrastructure.database.bootstrap import (
    BootstrapConflictError,
    SqlAlchemyOperatorBootstrap,
)
from app.infrastructure.database.database import Database
from app.infrastructure.database.models import AssistantModel, PlatformConnectionModel


@pytest.mark.integration
@pytest.mark.demo_integration
def test_demo_bootstrap_is_idempotent_and_rejects_identity_mismatch() -> None:
    async def scenario() -> None:
        settings = Settings(_env_file=None, environment="test", app_name="January Demo")
        database = Database(settings)
        await database.start()
        try:
            async with database.engine.begin() as connection:
                await connection.execute(text("TRUNCATE assistants CASCADE"))
            bootstrap = SqlAlchemyOperatorBootstrap(database.session_factory)
            identity = BotIdentity(
                platform=Platform.TELEGRAM,
                external_bot_id="900000001",
                username="january_demo_bot",
                display_name="January Demo",
                is_bot=True,
                can_join_groups=True,
                can_read_all_group_messages=False,
            )
            first = await bootstrap.reconcile(settings, identity)
            second = await bootstrap.reconcile(settings, identity)
            assert first.assistant_id == second.assistant_id
            assert first.platform_connection_id == second.platform_connection_id
            async with database.session_factory() as session:
                assert await session.scalar(select(func.count(AssistantModel.id))) == 1
                connection = await session.get(
                    PlatformConnectionModel, first.platform_connection_id
                )
                assert connection is not None
                assert (
                    connection.credential_reference == "env:JANUARY_TELEGRAM_BOT_TOKEN"
                )
                assert connection.configuration["username"] == "january_demo_bot"
                assert "fake-token" not in str(connection.configuration)
                mismatch = PlatformConnectionModel(
                    assistant_id=first.assistant_id,
                    platform=Platform.TELEGRAM,
                    external_bot_id="900000002",
                    status=PlatformConnectionStatus.ACTIVE,
                )
                session.add(mismatch)
                await session.commit()
                mismatch_id = mismatch.id
            configured = settings.model_copy(
                update={"telegram_platform_connection_id": mismatch_id}
            )
            with pytest.raises(BootstrapConflictError, match="another bot"):
                await bootstrap.reconcile(configured, identity)
        finally:
            await database.stop()

    asyncio.run(scenario())
