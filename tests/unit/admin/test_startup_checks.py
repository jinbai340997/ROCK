import logging

import pytest

from rock.admin.startup_checks import check_oss_consistency_with_log_policy
from rock.config import OssConfig, SandboxConfig
from rock.deployments.log_cleanup import LogCleanupPolicy


@pytest.fixture(autouse=True)
def _propagate_startup_checks_logger():
    """ROCK loggers set propagate=False; opt back in so caplog sees them."""
    lg = logging.getLogger("rock.admin.startup_checks")
    saved = lg.propagate
    lg.propagate = True
    lg.setLevel(logging.DEBUG)
    yield
    lg.propagate = saved


class TestStartupChecks:
    def test_warns_when_archive_default_but_no_oss(
        self,
        make_rock_config_fixture,
        caplog,
    ):
        rock_config = make_rock_config_fixture(
            sandbox_config=SandboxConfig(
                sandbox_log_cleanup_policy_default=LogCleanupPolicy.ARCHIVE_THEN_CLEAN,
            ),
            oss=OssConfig(bucket=""),
        )
        with caplog.at_level(logging.WARNING):
            check_oss_consistency_with_log_policy(rock_config)
        assert "archive_then_clean" in caplog.text
        assert "OssConfig.bucket is empty" in caplog.text

    def test_silent_when_keep_default(
        self,
        make_rock_config_fixture,
        caplog,
    ):
        rock_config = make_rock_config_fixture(
            sandbox_config=SandboxConfig(
                sandbox_log_cleanup_policy_default=LogCleanupPolicy.KEEP,
            ),
            oss=OssConfig(bucket=""),
        )
        with caplog.at_level(logging.WARNING):
            check_oss_consistency_with_log_policy(rock_config)
        assert "OssConfig.bucket is empty" not in caplog.text

    def test_silent_when_oss_configured(
        self,
        make_rock_config_fixture,
        caplog,
    ):
        rock_config = make_rock_config_fixture(
            sandbox_config=SandboxConfig(
                sandbox_log_cleanup_policy_default=LogCleanupPolicy.ARCHIVE_THEN_CLEAN,
            ),
            oss=OssConfig(bucket="my-bucket"),
        )
        with caplog.at_level(logging.WARNING):
            check_oss_consistency_with_log_policy(rock_config)
        assert "OssConfig.bucket is empty" not in caplog.text

    def test_silent_when_clean_directly(
        self,
        make_rock_config_fixture,
        caplog,
    ):
        rock_config = make_rock_config_fixture(
            sandbox_config=SandboxConfig(
                sandbox_log_cleanup_policy_default=LogCleanupPolicy.CLEAN_DIRECTLY,
            ),
            oss=OssConfig(bucket=""),
        )
        with caplog.at_level(logging.WARNING):
            check_oss_consistency_with_log_policy(rock_config)
        assert "OssConfig.bucket is empty" not in caplog.text
