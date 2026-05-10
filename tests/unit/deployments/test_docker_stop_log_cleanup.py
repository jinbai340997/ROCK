"""Test DockerDeployment._handle_sandbox_log_dir + _archive_then_clean.

We test these methods in isolation rather than full _stop() because
_stop() requires a live container_process. The real _stop() path is
exercised by integration tests.
"""

import logging
from unittest.mock import patch

import pytest

from rock.deployments.log_cleanup import LogCleanupPolicy


@pytest.fixture(autouse=True)
def _propagate_docker_logger():
    """ROCK loggers set propagate=False; opt back in so caplog sees them."""
    lg = logging.getLogger("rock.deployments.docker")
    saved = lg.propagate
    lg.propagate = True
    lg.setLevel(logging.DEBUG)
    yield
    lg.propagate = saved


@pytest.fixture
def deployment_with_container(make_docker_deployment_config_fixture):
    """Build a minimal DockerDeployment-like object exposing only what
    _handle_sandbox_log_dir needs.
    """
    from rock.deployments.docker import DockerDeployment

    cfg = make_docker_deployment_config_fixture(container_name="test-uuid-abc")
    cfg.sandbox_log_cleanup_policy = LogCleanupPolicy.KEEP  # placeholder

    # Bypass __init__ heavy lifting
    deploy = DockerDeployment.__new__(DockerDeployment)
    deploy._config = cfg
    deploy._container_name = "test-uuid-abc"
    return deploy


class TestKeepPolicy:
    def test_keep_preserves_dir(self, deployment_with_container, tmp_path, caplog):
        log_dir = tmp_path / "test-uuid-abc"
        log_dir.mkdir()
        (log_dir / "out.log").write_text("hello")

        deployment_with_container._handle_sandbox_log_dir(
            log_dir,
            LogCleanupPolicy.KEEP,
        )
        assert log_dir.exists()
        assert (log_dir / "out.log").read_text() == "hello"
        assert "Keep sandbox log dir" in caplog.text


class TestCleanDirectlyPolicy:
    def test_clean_directly_removes_dir(self, deployment_with_container, tmp_path):
        log_dir = tmp_path / "test-uuid-abc"
        log_dir.mkdir()
        (log_dir / "x").write_text("y")

        deployment_with_container._handle_sandbox_log_dir(
            log_dir,
            LogCleanupPolicy.CLEAN_DIRECTLY,
        )
        assert not log_dir.exists()


class TestArchiveThenCleanPolicy:
    def test_success_path_uploads_and_removes(
        self,
        deployment_with_container,
        tmp_path,
    ):
        log_dir = tmp_path / "test-uuid-abc"
        log_dir.mkdir()
        (log_dir / "x").write_text("y")

        with patch(
            "rock.utils.oss_archiver.OssArchiver.try_upload_dir_sync",
            return_value=True,
        ) as mock_upload:
            deployment_with_container._handle_sandbox_log_dir(
                log_dir,
                LogCleanupPolicy.ARCHIVE_THEN_CLEAN,
            )

        # Verify oss_key follows convention
        call_args = mock_upload.call_args
        assert (
            call_args.args[1] == "rock-archives/sandbox-logs/test-uuid-abc.tar.gz"
            or call_args.kwargs.get("oss_key") == "rock-archives/sandbox-logs/test-uuid-abc.tar.gz"
        )
        # container_name passed for metric tagging
        assert call_args.kwargs.get("container_name") == "test-uuid-abc"
        # Dir was removed
        assert not log_dir.exists()

    def test_failure_path_preserves_dir(
        self,
        deployment_with_container,
        tmp_path,
        caplog,
    ):
        """Critical fail-safe regression: archive failure MUST NOT delete."""
        log_dir = tmp_path / "test-uuid-abc"
        log_dir.mkdir()
        (log_dir / "x").write_text("important data")

        with patch(
            "rock.utils.oss_archiver.OssArchiver.try_upload_dir_sync",
            return_value=False,
        ):
            deployment_with_container._handle_sandbox_log_dir(
                log_dir,
                LogCleanupPolicy.ARCHIVE_THEN_CLEAN,
            )
        assert log_dir.exists()
        assert (log_dir / "x").read_text() == "important data"
        assert "Archive failed; preserving sandbox log dir" in caplog.text


class TestUnknownPolicyDefensiveBranch:
    def test_unknown_policy_falls_back_to_keep(
        self,
        deployment_with_container,
        tmp_path,
        caplog,
    ):
        """Defensive: future enum values added without updating the
        match block should NOT silently archive or delete."""
        log_dir = tmp_path / "test-uuid-abc"
        log_dir.mkdir()
        (log_dir / "x").write_text("y")

        # Pass a sentinel that's not a valid LogCleanupPolicy
        deployment_with_container._handle_sandbox_log_dir(
            log_dir,
            "future_unknown_value",
        )
        assert log_dir.exists()
        assert "Unknown sandbox_log_cleanup_policy" in caplog.text
