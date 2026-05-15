"""Tests for FileCleanupTask: -delete perf path + path-form validation."""

from unittest.mock import AsyncMock

import pytest

from rock.admin.scheduler.task_base import TaskStatusEnum
from rock.admin.scheduler.tasks.file_cleanup_task import FileCleanupTask, TargetDirConfig

# --------------------------------------------------------------------------- #
# Section A: TargetDirConfig.from_raw — backward-compat + path validation
# --------------------------------------------------------------------------- #


class TestTargetDirConfigFromRaw:
    def test_from_raw_with_string(self):
        cfg = TargetDirConfig.from_raw("/data/cache")
        assert cfg.path == "/data/cache"
        assert cfg.exclude_dirs == []
        assert cfg.exclude_files == []

    def test_from_raw_with_dict_full(self):
        cfg = TargetDirConfig.from_raw(
            {
                "path": "/data/cache",
                "exclude_dirs": [".git", "important"],
                "exclude_files": [".gitkeep"],
            }
        )
        assert cfg.path == "/data/cache"
        assert cfg.exclude_dirs == [".git", "important"]
        assert cfg.exclude_files == [".gitkeep"]

    def test_from_raw_with_dict_minimal(self):
        cfg = TargetDirConfig.from_raw({"path": "/data/cache"})
        assert cfg.exclude_dirs == []
        assert cfg.exclude_files == []

    @pytest.mark.parametrize("bad", [123, None, ["/data"], ()])
    def test_from_raw_rejects_unsupported_type(self, bad):
        with pytest.raises(ValueError, match="Unsupported target_dirs entry type"):
            TargetDirConfig.from_raw(bad)

    @pytest.mark.parametrize("bad_path", ["", "relative/path", "./logs"])
    def test_from_raw_rejects_relative_or_empty(self, bad_path):
        with pytest.raises(ValueError):
            TargetDirConfig.from_raw(bad_path) if bad_path else TargetDirConfig.from_raw({"path": bad_path})

    def test_from_raw_dict_rejects_relative(self):
        with pytest.raises(ValueError, match="absolute path"):
            TargetDirConfig.from_raw({"path": "relative/dir"})

    def test_from_raw_rejects_dotdot(self):
        with pytest.raises(ValueError, match="must not contain '..'"):
            TargetDirConfig.from_raw("/data/../etc")


# --------------------------------------------------------------------------- #
# Section B: _build_cleanup_command — uses -delete (the perf change)
# --------------------------------------------------------------------------- #


class TestBuildCleanupCommand:
    def _new_task(self, **kwargs):
        return FileCleanupTask(
            target_dirs=kwargs.pop("target_dirs", [TargetDirConfig(path="/data/cache")]),
            max_age_mins=kwargs.pop("max_age_mins", 10080),
            max_file_size=kwargs.pop("max_file_size", "1G"),
            **kwargs,
        )

    def test_command_uses_delete_for_files(self):
        task = self._new_task()
        cmd = task._build_cleanup_command(TargetDirConfig(path="/data/cache"))
        assert "-delete;" in cmd
        # Old forms must be gone
        assert "-exec rm -f" not in cmd
        assert "-exec rm " not in cmd

    def test_command_uses_delete_for_empty_dirs(self):
        task = self._new_task()
        cmd = task._build_cleanup_command(TargetDirConfig(path="/data/cache"))
        assert "-type d -empty -delete" in cmd
        assert "-exec rmdir" not in cmd

    def test_command_includes_target_dir_existence_check(self):
        task = self._new_task()
        cmd = task._build_cleanup_command(TargetDirConfig(path="/data/cache"))
        assert 'if [ -d "/data/cache" ]; then' in cmd
        assert 'else echo "dir_not_found"; fi' in cmd
        assert 'echo "cleanup_done"' in cmd

    def test_command_includes_age_and_size_predicates(self):
        task = self._new_task(max_age_mins=4320, max_file_size="500M")
        cmd = task._build_cleanup_command(TargetDirConfig(path="/data/cache"))
        assert "-mmin +4320" in cmd
        # 500M = 500 * 1024 * 1024 = 524288000
        assert "-size +524288000c" in cmd

    def test_command_with_exclude_dirs(self):
        dir_cfg = TargetDirConfig(path="/data/cache", exclude_dirs=["keep_me"])
        task = self._new_task(target_dirs=[dir_cfg])
        cmd = task._build_cleanup_command(dir_cfg)
        assert '-name "keep_me" -prune' in cmd

    def test_command_with_exclude_files(self):
        dir_cfg = TargetDirConfig(path="/data/cache", exclude_files=["important.log"])
        task = self._new_task(target_dirs=[dir_cfg])
        cmd = task._build_cleanup_command(dir_cfg)
        assert '-name "important.log" -prune' in cmd

    def test_command_with_relative_path_exclude(self):
        dir_cfg = TargetDirConfig(path="/data/cache", exclude_files=["./subdir/keep.log"])
        task = self._new_task(target_dirs=[dir_cfg])
        cmd = task._build_cleanup_command(dir_cfg)
        assert '-path "/data/cache/subdir/keep.log" -prune' in cmd

    def test_command_with_absolute_path_exclude(self):
        dir_cfg = TargetDirConfig(path="/data/cache", exclude_dirs=["/data/cache/keep_subdir"])
        task = self._new_task(target_dirs=[dir_cfg])
        cmd = task._build_cleanup_command(dir_cfg)
        assert '-path "/data/cache/keep_subdir" -prune' in cmd


# --------------------------------------------------------------------------- #
# Section C: from_config — yaml -> task instance, backward compat
# --------------------------------------------------------------------------- #


class _FakeTaskConfig:
    """Lightweight stand-in for rock.config.TaskConfig in unit tests."""

    def __init__(self, params, interval_seconds=86400):
        self.params = params
        self.interval_seconds = interval_seconds


class TestFromConfig:
    def test_from_config_legacy_string_format(self):
        task_config = _FakeTaskConfig(
            params={
                "target_dirs": ["/data/cache", "/data/scratch"],
                "max_age_mins": 1440,
                "max_file_size": "500M",
            }
        )
        task = FileCleanupTask.from_config(task_config)
        assert [dc.path for dc in task.target_dirs] == ["/data/cache", "/data/scratch"]
        assert task.max_age_mins == 1440
        assert task.max_file_size == "500M"

    def test_from_config_new_dict_format(self):
        task_config = _FakeTaskConfig(
            params={
                "target_dirs": [
                    {"path": "/data/cache", "exclude_dirs": ["keep"], "exclude_files": ["KEEP.txt"]},
                    "/data/scratch",
                ],
            }
        )
        task = FileCleanupTask.from_config(task_config)
        assert task.target_dirs[0].path == "/data/cache"
        assert task.target_dirs[0].exclude_dirs == ["keep"]
        assert task.target_dirs[1].path == "/data/scratch"
        assert task.target_dirs[1].exclude_dirs == []

    def test_from_config_defaults_when_missing(self):
        task_config = _FakeTaskConfig(params={"target_dirs": ["/data/cache"]})
        task = FileCleanupTask.from_config(task_config)
        assert task.max_age_mins == 10080
        assert task.max_file_size == "1G"

    def test_from_config_rejects_relative_yaml_path(self):
        """yaml typo: relative path must fail at load time, not at runtime."""
        task_config = _FakeTaskConfig(params={"target_dirs": ["relative/path"]})
        with pytest.raises(ValueError, match="absolute path"):
            FileCleanupTask.from_config(task_config)


# --------------------------------------------------------------------------- #
# Section D: run_action — happy path + error path (status enum)
# --------------------------------------------------------------------------- #


class _FakeExecResult:
    def __init__(self, exit_code=0, stdout="cleanup_done"):
        self.exit_code = exit_code
        self.stdout = stdout


class TestRunAction:
    @pytest.mark.asyncio
    async def test_run_action_no_target_dirs(self):
        task = FileCleanupTask(target_dirs=[])
        result = await task.run_action(runtime=AsyncMock())
        assert result["status"] == TaskStatusEnum.SUCCESS
        assert "no target directories" in result["message"]

    @pytest.mark.asyncio
    async def test_run_action_happy_path(self):
        task = FileCleanupTask(target_dirs=[TargetDirConfig(path="/data/cache")])

        runtime = AsyncMock()
        runtime._config = type("C", (), {"host": "10.0.0.1"})()
        runtime.execute = AsyncMock(return_value=_FakeExecResult())

        result = await task.run_action(runtime)
        assert result["status"] == TaskStatusEnum.SUCCESS
        assert result["target_dirs"] == ["/data/cache"]
        assert "/data/cache" in result["details"]
        assert result["details"]["/data/cache"]["exit_code"] == 0

        # Verify the executed shell command actually used -delete
        executed_cmd = runtime.execute.await_args.args[0].command
        assert "-delete" in executed_cmd
        assert "-exec rm" not in executed_cmd

    @pytest.mark.asyncio
    async def test_run_action_re_raises_on_error(self):
        task = FileCleanupTask(target_dirs=[TargetDirConfig(path="/data/cache")])

        runtime = AsyncMock()
        runtime._config = type("C", (), {"host": "10.0.0.1"})()
        runtime.execute = AsyncMock(side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError, match="boom"):
            await task.run_action(runtime)
