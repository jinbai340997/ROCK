import argparse
from unittest.mock import AsyncMock, patch

import pytest

from rock.cli.command.storage import StorageCommand


@pytest.mark.asyncio
async def test_get_success(tmp_path, capsys):
    cmd = StorageCommand()
    args = argparse.Namespace(
        storage_action="get",
        sandbox_id="abc",
        out=str(tmp_path),
    )
    with (
        patch(
            "rock.cli.command.storage.OssArchiver.build_sandbox_log_key",
            return_value="rock-archives/sandbox-logs/abc.tar.gz",
        ),
        patch(
            "rock.cli.command.storage.OssArchiver.get_object",
            new=AsyncMock(return_value=True),
        ),
    ):
        await cmd.arun(args)
    captured = capsys.readouterr()
    assert f"OK: {tmp_path}/abc.tar.gz" in captured.out
    assert "tar -xzf" in captured.out


@pytest.mark.asyncio
async def test_get_failure_prints_failed(tmp_path, capsys):
    cmd = StorageCommand()
    args = argparse.Namespace(
        storage_action="get",
        sandbox_id="abc",
        out=str(tmp_path),
    )
    with (
        patch(
            "rock.cli.command.storage.OssArchiver.build_sandbox_log_key",
            return_value="k",
        ),
        patch(
            "rock.cli.command.storage.OssArchiver.get_object",
            new=AsyncMock(return_value=False),
        ),
    ):
        await cmd.arun(args)
    captured = capsys.readouterr()
    assert "FAILED" in captured.out


@pytest.mark.asyncio
async def test_no_action_raises():
    cmd = StorageCommand()
    args = argparse.Namespace(storage_action=None)
    with pytest.raises(ValueError, match="storage action is required"):
        await cmd.arun(args)


@pytest.mark.asyncio
async def test_unknown_action_raises():
    cmd = StorageCommand()
    args = argparse.Namespace(storage_action="put")
    with pytest.raises(ValueError, match="Unknown storage action"):
        await cmd.arun(args)


@pytest.mark.asyncio
async def test_add_parser_to_registers_get_subcommand():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    await StorageCommand.add_parser_to(subparsers)

    args = parser.parse_args(["storage", "get", "myid", "--out", "/tmp/o"])
    assert args.command == "storage"
    assert args.storage_action == "get"
    assert args.sandbox_id == "myid"
    assert args.out == "/tmp/o"
