import pytest
from pydantic import ValidationError

from rock.deployments.log_cleanup import LogCleanupPolicy
from rock.sdk.sandbox.config import SandboxConfig


class TestSandboxConfigAutoDeleteSeconds:
    def test_default_is_none(self):
        config = SandboxConfig()
        assert config.auto_delete_seconds is None

    def test_none_is_valid(self):
        config = SandboxConfig(auto_delete_seconds=None)
        assert config.auto_delete_seconds is None

    def test_zero_is_valid(self):
        config = SandboxConfig(auto_delete_seconds=0)
        assert config.auto_delete_seconds == 0

    def test_positive_value_is_valid(self):
        config = SandboxConfig(auto_delete_seconds=300)
        assert config.auto_delete_seconds == 300

    def test_negative_value_raises_error(self):
        with pytest.raises(ValidationError, match="auto_delete_seconds must be >= 0"):
            SandboxConfig(auto_delete_seconds=-1)

    def test_large_negative_value_raises_error(self):
        with pytest.raises(ValidationError, match="auto_delete_seconds must be >= 0"):
            SandboxConfig(auto_delete_seconds=-100)


class TestSandboxConfigPolicyField:
    def test_default_is_none(self):
        cfg = SandboxConfig()
        assert cfg.sandbox_log_cleanup_policy is None

    def test_explicit_enum(self):
        cfg = SandboxConfig(sandbox_log_cleanup_policy=LogCleanupPolicy.KEEP)
        assert cfg.sandbox_log_cleanup_policy == LogCleanupPolicy.KEEP

    def test_string_accepted(self):
        # API users may send strings via JSON; Pydantic must coerce.
        cfg = SandboxConfig(sandbox_log_cleanup_policy="archive_then_clean")
        assert cfg.sandbox_log_cleanup_policy == LogCleanupPolicy.ARCHIVE_THEN_CLEAN

    def test_serializes_to_string_value(self):
        cfg = SandboxConfig(sandbox_log_cleanup_policy=LogCleanupPolicy.CLEAN_DIRECTLY)
        payload = cfg.model_dump()
        # str-Enum serializes as its value
        assert payload["sandbox_log_cleanup_policy"] in (
            "clean_directly",
            LogCleanupPolicy.CLEAN_DIRECTLY,
        )
