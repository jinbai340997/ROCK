import io
import tarfile
import time
from unittest.mock import MagicMock, patch

import pytest

from rock.utils.oss_archiver import OssArchiver


@pytest.fixture(autouse=True)
def _reset_singleton_and_globals():
    OssArchiver._bucket = None
    OssArchiver._archive_prefix = "rock-archives/"
    OssArchiver._archive_ttl_days = 30
    yield
    OssArchiver._bucket = None


def _make_fake_config(bucket: str = "test-bucket", prefix: str = "rock-archives/"):
    """Build a fake RockConfig.from_env() return value."""
    cfg = MagicMock()
    cfg.oss.bucket = bucket
    cfg.oss.endpoint = "oss-cn-hangzhou.aliyuncs.com"
    cfg.oss.access_key_id = "ak"
    cfg.oss.access_key_secret = "sk"
    cfg.oss.archive_prefix = prefix
    cfg.oss.archive_ttl_days = 30
    return cfg


# === build_sandbox_log_key ===


def test_build_sandbox_log_key_uses_prefix():
    with patch("rock.utils.oss_archiver.RockConfig.from_env", return_value=_make_fake_config()):
        key = OssArchiver.build_sandbox_log_key("abc123")
    assert key == "rock-archives/sandbox-logs/abc123.tar.gz"


def test_build_sandbox_log_key_custom_prefix():
    with patch("rock.utils.oss_archiver.RockConfig.from_env", return_value=_make_fake_config(prefix="my-rock/")):
        key = OssArchiver.build_sandbox_log_key("abc123")
    assert key == "my-rock/sandbox-logs/abc123.tar.gz"


# === Failure semantics ===


def test_returns_false_when_bucket_not_configured():
    with patch("rock.utils.oss_archiver.RockConfig.from_env", return_value=_make_fake_config(bucket="")):
        result = OssArchiver.try_upload_dir_sync("/tmp/x", "k.tar.gz")
    assert result is False


def test_returns_false_on_network_error(tmp_path):
    fake_bucket = MagicMock()
    fake_bucket.put_object.side_effect = Exception("network down")
    with (
        patch.object(OssArchiver, "_get_bucket", return_value=fake_bucket),
        patch("rock.utils.oss_archiver.RockConfig.from_env", return_value=_make_fake_config()),
    ):
        (tmp_path / "a.log").write_text("x" * 100)
        result = OssArchiver.try_upload_dir_sync(str(tmp_path), "k.tar.gz")
    assert result is False


def test_returns_false_when_size_exceeds_limit(tmp_path):
    fake_bucket = MagicMock()
    with (
        patch.object(OssArchiver, "_get_bucket", return_value=fake_bucket),
        patch("rock.utils.oss_archiver.RockConfig.from_env", return_value=_make_fake_config()),
    ):
        (tmp_path / "huge").write_bytes(b"x" * 1024)
        result = OssArchiver.try_upload_dir_sync(
            str(tmp_path),
            "k.tar.gz",
            max_size_bytes=512,
        )
    assert result is False
    fake_bucket.put_object.assert_not_called()


def test_timeout_returns_false(tmp_path):
    """Critical: 60s hard timeout must trigger fail-safe."""

    def slow_upload(*a, **kw):
        time.sleep(5)
        return True

    fake_bucket = MagicMock()
    fake_bucket.put_object.side_effect = slow_upload
    with (
        patch.object(OssArchiver, "_get_bucket", return_value=fake_bucket),
        patch("rock.utils.oss_archiver.RockConfig.from_env", return_value=_make_fake_config()),
    ):
        (tmp_path / "x").write_text("y")
        result = OssArchiver.try_upload_dir_sync(
            str(tmp_path),
            "k.tar.gz",
            timeout_seconds=1,
        )
    assert result is False


# === Success paths ===


def test_small_dir_uses_in_memory_buffer(tmp_path):
    fake_bucket = MagicMock()
    fake_bucket.bucket_name = "test-bucket"
    with (
        patch.object(OssArchiver, "_get_bucket", return_value=fake_bucket),
        patch("rock.utils.oss_archiver.RockConfig.from_env", return_value=_make_fake_config()),
    ):
        (tmp_path / "a.log").write_text("hi")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "b.log").write_text("hello")
        result = OssArchiver.try_upload_dir_sync(str(tmp_path), "k.tar.gz")
    assert result is True
    assert fake_bucket.put_object.call_count == 1
    assert fake_bucket.put_object_from_file.call_count == 0


def test_large_dir_uses_temp_file(tmp_path, monkeypatch):
    """Force temp-file path by lowering the buffer threshold."""
    monkeypatch.setattr("rock.utils.oss_archiver._MEMORY_BUFFER_MAX", 100)
    fake_bucket = MagicMock()
    fake_bucket.bucket_name = "test-bucket"
    with (
        patch.object(OssArchiver, "_get_bucket", return_value=fake_bucket),
        patch("rock.utils.oss_archiver.RockConfig.from_env", return_value=_make_fake_config()),
    ):
        (tmp_path / "big.log").write_bytes(b"x" * 200)
        result = OssArchiver.try_upload_dir_sync(str(tmp_path), "k.tar.gz")
    assert result is True
    assert fake_bucket.put_object_from_file.call_count == 1


# === Edge cases ===


def test_empty_dir_returns_true_no_upload(tmp_path):
    fake_bucket = MagicMock()
    with (
        patch.object(OssArchiver, "_get_bucket", return_value=fake_bucket),
        patch("rock.utils.oss_archiver.RockConfig.from_env", return_value=_make_fake_config()),
    ):
        result = OssArchiver.try_upload_dir_sync(str(tmp_path), "k.tar.gz")
    assert result is True
    fake_bucket.put_object.assert_not_called()


def test_missing_dir_returns_true(tmp_path):
    fake_bucket = MagicMock()
    with (
        patch.object(OssArchiver, "_get_bucket", return_value=fake_bucket),
        patch("rock.utils.oss_archiver.RockConfig.from_env", return_value=_make_fake_config()),
    ):
        result = OssArchiver.try_upload_dir_sync(
            str(tmp_path / "nonexistent"),
            "k.tar.gz",
        )
    assert result is True


# === Headers / metadata correctness ===


def test_headers_include_ttl_size_and_content_type(tmp_path):
    fake_bucket = MagicMock()
    fake_bucket.bucket_name = "test-bucket"
    with (
        patch.object(OssArchiver, "_get_bucket", return_value=fake_bucket),
        patch("rock.utils.oss_archiver.RockConfig.from_env", return_value=_make_fake_config()),
    ):
        (tmp_path / "a.log").write_bytes(b"abc")
        OssArchiver.try_upload_dir_sync(str(tmp_path), "k.tar.gz")
    _, kwargs = fake_bucket.put_object.call_args
    headers = kwargs["headers"]
    assert headers["x-oss-meta-ttl-days"] == "30"
    assert int(headers["x-oss-meta-original-size"]) == 3
    assert headers["Content-Type"] == "application/gzip"


# === End-to-end tarball correctness ===


def test_uploaded_tarball_can_be_extracted(tmp_path):
    captured = {}
    fake_bucket = MagicMock()
    fake_bucket.bucket_name = "test-bucket"

    def capture_put(key, body, headers=None):
        captured["body"] = body.read() if hasattr(body, "read") else body

    fake_bucket.put_object.side_effect = capture_put

    with (
        patch.object(OssArchiver, "_get_bucket", return_value=fake_bucket),
        patch("rock.utils.oss_archiver.RockConfig.from_env", return_value=_make_fake_config()),
    ):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.log").write_text("hello")
        (src / "b.log").write_text("world")
        OssArchiver.try_upload_dir_sync(str(src), "k.tar.gz")

    tf = tarfile.open(fileobj=io.BytesIO(captured["body"]), mode="r:gz")
    names = sorted(m.name for m in tf.getmembers() if m.isfile())
    assert names == ["src/a.log", "src/b.log"]


# === get_object ===


@pytest.mark.asyncio
async def test_get_object_downloads_to_local(tmp_path):
    fake_bucket = MagicMock()
    fake_bucket.get_object_to_file = MagicMock(return_value=None)
    with patch.object(OssArchiver, "_get_bucket", return_value=fake_bucket):
        target = tmp_path / "out" / "file.tar.gz"
        result = await OssArchiver.get_object("k.tar.gz", str(target))
    assert result is True
    fake_bucket.get_object_to_file.assert_called_once_with(
        "k.tar.gz",
        str(target),
    )
    assert target.parent.exists()


@pytest.mark.asyncio
async def test_get_object_returns_false_when_no_bucket():
    with patch.object(OssArchiver, "_get_bucket", return_value=None):
        result = await OssArchiver.get_object("k.tar.gz", "/tmp/x")
    assert result is False


@pytest.mark.asyncio
async def test_get_object_returns_false_on_error(tmp_path):
    fake_bucket = MagicMock()
    fake_bucket.get_object_to_file = MagicMock(side_effect=Exception("boom"))
    with patch.object(OssArchiver, "_get_bucket", return_value=fake_bucket):
        result = await OssArchiver.get_object(
            "k.tar.gz",
            str(tmp_path / "out.tar.gz"),
        )
    assert result is False


# === Metric integration (parameter-passed monitor; no global state) ===


def test_metric_recorded_on_success(tmp_path):
    fake_bucket = MagicMock()
    fake_bucket.bucket_name = "test-bucket"
    fake_monitor = MagicMock()
    with (
        patch.object(OssArchiver, "_get_bucket", return_value=fake_bucket),
        patch("rock.utils.oss_archiver.RockConfig.from_env", return_value=_make_fake_config()),
    ):
        (tmp_path / "x").write_text("y")
        OssArchiver.try_upload_dir_sync(
            str(tmp_path),
            "k.tar.gz",
            container_name="abc",
            metrics_monitor=fake_monitor,  # 显式传入,无全局
        )
    # total + success counters; size gauge
    metric_calls = [c.args[0] for c in fake_monitor.record_counter_by_name.call_args_list]
    assert "sandbox.log.archive.total" in metric_calls
    assert "sandbox.log.archive.success" in metric_calls
    fake_monitor.record_gauge_by_name.assert_called_once()
    # container tag transmitted on every metric
    assert fake_monitor.record_counter_by_name.call_args_list[0].args[2] == {"container": "abc"}


def test_metric_recorded_on_failure(tmp_path):
    fake_bucket = MagicMock()
    fake_bucket.put_object.side_effect = Exception("boom")
    fake_monitor = MagicMock()
    with (
        patch.object(OssArchiver, "_get_bucket", return_value=fake_bucket),
        patch("rock.utils.oss_archiver.RockConfig.from_env", return_value=_make_fake_config()),
    ):
        (tmp_path / "x").write_text("y")
        OssArchiver.try_upload_dir_sync(
            str(tmp_path),
            "k.tar.gz",
            container_name="abc",
            metrics_monitor=fake_monitor,
        )
    metric_calls = [c.args[0] for c in fake_monitor.record_counter_by_name.call_args_list]
    assert "sandbox.log.archive.total" in metric_calls
    assert "sandbox.log.archive.failure" in metric_calls


def test_metric_silent_when_monitor_none(tmp_path):
    """No metrics_monitor passed (default None) → no crash, no recording."""
    fake_bucket = MagicMock()
    fake_bucket.bucket_name = "test-bucket"
    with (
        patch.object(OssArchiver, "_get_bucket", return_value=fake_bucket),
        patch("rock.utils.oss_archiver.RockConfig.from_env", return_value=_make_fake_config()),
    ):
        (tmp_path / "x").write_text("y")
        # No metrics_monitor=, defaults to None
        result = OssArchiver.try_upload_dir_sync(str(tmp_path), "k.tar.gz")
    assert result is True


def test_metric_default_none_when_not_passed(tmp_path):
    """Regression: ensure metrics_monitor parameter is optional with default None
    (so existing callers / unit tests don't need to pass it)."""
    fake_bucket = MagicMock()
    fake_bucket.bucket_name = "test-bucket"
    with (
        patch.object(OssArchiver, "_get_bucket", return_value=fake_bucket),
        patch("rock.utils.oss_archiver.RockConfig.from_env", return_value=_make_fake_config()),
    ):
        (tmp_path / "x").write_text("y")
        # No metrics_monitor kwarg at all
        result = OssArchiver.try_upload_dir_sync(
            str(tmp_path),
            "k.tar.gz",
            container_name="abc",
        )
    assert result is True
