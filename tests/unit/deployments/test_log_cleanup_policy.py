import pytest

from rock.deployments.log_cleanup import LogCleanupPolicy


class TestLogCleanupPolicy:
    def test_string_to_enum(self):
        assert LogCleanupPolicy("keep") == LogCleanupPolicy.KEEP
        assert LogCleanupPolicy("archive_then_clean") == LogCleanupPolicy.ARCHIVE_THEN_CLEAN
        assert LogCleanupPolicy("clean_directly") == LogCleanupPolicy.CLEAN_DIRECTLY

    def test_enum_value_is_string(self):
        # str-Enum so yaml dataclass field auto-converts via __post_init__
        assert LogCleanupPolicy.KEEP.value == "keep"
        assert isinstance(LogCleanupPolicy.KEEP, str)

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            LogCleanupPolicy("delete_everything")
        with pytest.raises(ValueError):
            LogCleanupPolicy("")

    def test_three_values_only(self):
        # Defensive: if someone adds a 4th value, _handle_sandbox_log_dir
        # match block must be updated. Lock this down so adding a value
        # forces a deliberate decision.
        assert {p.value for p in LogCleanupPolicy} == {
            "keep",
            "archive_then_clean",
            "clean_directly",
        }
