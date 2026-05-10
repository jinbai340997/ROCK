from unittest.mock import AsyncMock

import pytest

from rock.config import SandboxConfig
from rock.deployments.log_cleanup import LogCleanupPolicy
from rock.deployments.manager import DeploymentManager


@pytest.fixture
def manager_with_policy_default(make_rock_config_fixture):
    """Helper: build DeploymentManager with a custom cluster default."""

    def _build(default_policy: LogCleanupPolicy):
        rock_config = make_rock_config_fixture(
            sandbox_config=SandboxConfig(
                sandbox_log_cleanup_policy_default=default_policy,
            ),
        )
        # Avoid hitting nacos / network in update()
        rock_config.update = AsyncMock(return_value=None)
        return DeploymentManager(rock_config)

    return _build


@pytest.mark.asyncio
async def test_policy_none_falls_back_to_cluster_default_archive(
    manager_with_policy_default,
    make_docker_deployment_config_fixture,
):
    mgr = manager_with_policy_default(LogCleanupPolicy.ARCHIVE_THEN_CLEAN)
    user_cfg = make_docker_deployment_config_fixture()
    assert user_cfg.sandbox_log_cleanup_policy is None  # not specified

    resolved = await mgr.init_config(user_cfg)
    assert resolved.sandbox_log_cleanup_policy == LogCleanupPolicy.ARCHIVE_THEN_CLEAN


@pytest.mark.asyncio
async def test_policy_none_falls_back_to_cluster_default_keep(
    manager_with_policy_default,
    make_docker_deployment_config_fixture,
):
    mgr = manager_with_policy_default(LogCleanupPolicy.KEEP)
    user_cfg = make_docker_deployment_config_fixture()
    resolved = await mgr.init_config(user_cfg)
    assert resolved.sandbox_log_cleanup_policy == LogCleanupPolicy.KEEP


@pytest.mark.asyncio
async def test_policy_explicit_user_override_beats_cluster_default(
    manager_with_policy_default,
    make_docker_deployment_config_fixture,
):
    """User explicitly setting CLEAN_DIRECTLY must win over cluster's
    ARCHIVE_THEN_CLEAN default."""
    mgr = manager_with_policy_default(LogCleanupPolicy.ARCHIVE_THEN_CLEAN)
    user_cfg = make_docker_deployment_config_fixture(
        sandbox_log_cleanup_policy=LogCleanupPolicy.CLEAN_DIRECTLY,
    )
    resolved = await mgr.init_config(user_cfg)
    assert resolved.sandbox_log_cleanup_policy == LogCleanupPolicy.CLEAN_DIRECTLY


@pytest.mark.asyncio
async def test_existing_remove_container_logic_intact(
    manager_with_policy_default,
    make_docker_deployment_config_fixture,
):
    """Regression: PR-1 added a NEW block but must not affect
    auto_delete_seconds / remove_container resolution."""
    mgr = manager_with_policy_default(LogCleanupPolicy.KEEP)
    user_cfg = make_docker_deployment_config_fixture(auto_delete_seconds=0)
    resolved = await mgr.init_config(user_cfg)
    assert resolved.remove_container is True

    user_cfg2 = make_docker_deployment_config_fixture(auto_delete_seconds=60)
    resolved2 = await mgr.init_config(user_cfg2)
    assert resolved2.remove_container is False
