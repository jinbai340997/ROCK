import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rock.utils.docker_safety import _containers_using_image, safe_remove_image


class TestContainersUsingImage:
    def test_returns_true_when_containers_present(self):
        with patch("subprocess.check_output", return_value=b"abc123\ndef456\n"):
            assert _containers_using_image("nginx") is True

    def test_returns_false_when_no_containers(self):
        with patch("subprocess.check_output", return_value=b""):
            assert _containers_using_image("nginx") is False

    def test_returns_true_on_subprocess_error_conservative(self):
        """Conservative: if docker ps fails, treat as in-use."""
        with patch(
            "subprocess.check_output",
            side_effect=subprocess.CalledProcessError(1, "docker"),
        ):
            assert _containers_using_image("nginx") is True

    def test_returns_true_on_timeout_conservative(self):
        with patch(
            "subprocess.check_output",
            side_effect=subprocess.TimeoutExpired("docker", 10),
        ):
            assert _containers_using_image("nginx") is True


class TestSafeRemoveImage:
    @pytest.mark.asyncio
    async def test_skip_when_in_use(self):
        with patch(
            "rock.utils.docker_safety._containers_using_image",
            return_value=True,
        ):
            with patch(
                "rock.utils.docker_safety.DockerUtil.remove_image"
            ) as mock_remove:
                result = await safe_remove_image("nginx")
        assert result is False
        mock_remove.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_when_envhub_registered(self):
        fake_envs = [MagicMock(image="my-app:1.0")]
        fake_client = MagicMock()
        fake_client.list_envs = AsyncMock(return_value=fake_envs)
        with patch(
            "rock.utils.docker_safety._containers_using_image",
            return_value=False,
        ), patch(
            "rock.sdk.envhub.client.EnvHubClient",
            return_value=fake_client,
        ):
            with patch(
                "rock.utils.docker_safety.DockerUtil.remove_image"
            ) as mock_remove:
                result = await safe_remove_image("my-app:1.0")
        assert result is False
        mock_remove.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_when_envhub_check_fails_conservative(self):
        """Conservative: EnvHub network failure → skip removal."""
        fake_client = MagicMock()
        fake_client.list_envs = AsyncMock(side_effect=Exception("envhub down"))
        with patch(
            "rock.utils.docker_safety._containers_using_image",
            return_value=False,
        ), patch(
            "rock.sdk.envhub.client.EnvHubClient",
            return_value=fake_client,
        ):
            with patch(
                "rock.utils.docker_safety.DockerUtil.remove_image"
            ) as mock_remove:
                result = await safe_remove_image("my-app:1.0")
        assert result is False
        mock_remove.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_when_whitelist_match(self):
        fake_client = MagicMock()
        fake_client.list_envs = AsyncMock(return_value=[])
        with patch(
            "rock.utils.docker_safety._containers_using_image",
            return_value=False,
        ), patch(
            "rock.sdk.envhub.client.EnvHubClient",
            return_value=fake_client,
        ), patch(
            "rock.utils.docker_safety.env_vars.ROCK_IMAGE_KEEP_PATTERNS",
            ["^rock-base.*$"],
        ):
            with patch(
                "rock.utils.docker_safety.DockerUtil.remove_image"
            ) as mock_remove:
                result = await safe_remove_image("rock-base:python3.11")
        assert result is False
        mock_remove.assert_not_called()

    @pytest.mark.asyncio
    async def test_remove_when_all_checks_pass(self):
        fake_client = MagicMock()
        fake_client.list_envs = AsyncMock(return_value=[])
        with patch(
            "rock.utils.docker_safety._containers_using_image",
            return_value=False,
        ), patch(
            "rock.sdk.envhub.client.EnvHubClient",
            return_value=fake_client,
        ), patch(
            "rock.utils.docker_safety.env_vars.ROCK_IMAGE_KEEP_PATTERNS",
            ["^rock-base.*$"],
        ):
            with patch(
                "rock.utils.docker_safety.DockerUtil.remove_image"
            ) as mock_remove:
                result = await safe_remove_image("my-app:1.0")
        assert result is True
        mock_remove.assert_called_once_with("my-app:1.0")

    @pytest.mark.asyncio
    async def test_returns_false_on_remove_image_error(self):
        fake_client = MagicMock()
        fake_client.list_envs = AsyncMock(return_value=[])
        with patch(
            "rock.utils.docker_safety._containers_using_image",
            return_value=False,
        ), patch(
            "rock.sdk.envhub.client.EnvHubClient",
            return_value=fake_client,
        ), patch(
            "rock.utils.docker_safety.env_vars.ROCK_IMAGE_KEEP_PATTERNS",
            [],
        ), patch(
            "rock.utils.docker_safety.DockerUtil.remove_image",
            side_effect=subprocess.CalledProcessError(1, "docker"),
        ):
            result = await safe_remove_image("my-app:1.0")
        assert result is False

    @pytest.mark.asyncio
    async def test_empty_whitelist_does_not_skip(self):
        """Setting ROCK_IMAGE_KEEP_PATTERNS="" disables the layer."""
        fake_client = MagicMock()
        fake_client.list_envs = AsyncMock(return_value=[])
        with patch(
            "rock.utils.docker_safety._containers_using_image",
            return_value=False,
        ), patch(
            "rock.sdk.envhub.client.EnvHubClient",
            return_value=fake_client,
        ), patch(
            "rock.utils.docker_safety.env_vars.ROCK_IMAGE_KEEP_PATTERNS",
            [],
        ):
            with patch(
                "rock.utils.docker_safety.DockerUtil.remove_image"
            ) as mock_remove:
                result = await safe_remove_image("rock-base:python3.11")
        assert result is True
        mock_remove.assert_called_once()
