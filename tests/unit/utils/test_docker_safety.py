"""Tests for rock.utils.docker_safety — whitelist-only image removal guard."""

import subprocess
from unittest.mock import patch

import pytest

from rock.utils.docker_safety import safe_remove_image


class TestSafeRemoveImage:
    def test_removes_when_no_whitelist_match(self):
        """Image not matching any whitelist pattern → DockerUtil.remove_image called."""
        with (
            patch("rock.utils.docker_safety.env_vars.ROCK_IMAGE_KEEP_PATTERNS", ["^rock-base.*$"]),
            patch("rock.utils.docker_safety.DockerUtil.remove_image") as mock_remove,
        ):
            result = safe_remove_image("my-app:1.0")
        assert result is True
        mock_remove.assert_called_once_with("my-app:1.0")

    def test_skips_when_whitelist_matches(self):
        """Image matching a whitelist pattern → preserved, no docker rmi."""
        with (
            patch("rock.utils.docker_safety.env_vars.ROCK_IMAGE_KEEP_PATTERNS", ["^rock-base.*$"]),
            patch("rock.utils.docker_safety.DockerUtil.remove_image") as mock_remove,
        ):
            result = safe_remove_image("rock-base:python3.11")
        assert result is False
        mock_remove.assert_not_called()

    def test_skips_when_envhub_pattern_matches(self):
        """Default whitelist also covers envhub-derived images."""
        with (
            patch("rock.utils.docker_safety.env_vars.ROCK_IMAGE_KEEP_PATTERNS", ["^.*envhub.*$"]),
            patch("rock.utils.docker_safety.DockerUtil.remove_image") as mock_remove,
        ):
            result = safe_remove_image("registry.example.com/envhub-derived:latest")
        assert result is False
        mock_remove.assert_not_called()

    def test_empty_whitelist_allows_removal(self):
        """ROCK_IMAGE_KEEP_PATTERNS=[] disables the whitelist entirely."""
        with (
            patch("rock.utils.docker_safety.env_vars.ROCK_IMAGE_KEEP_PATTERNS", []),
            patch("rock.utils.docker_safety.DockerUtil.remove_image") as mock_remove,
        ):
            result = safe_remove_image("rock-base:python3.11")
        assert result is True
        mock_remove.assert_called_once()

    def test_returns_false_on_docker_rmi_error(self):
        """docker rmi failure → False (caller treats as benign skip)."""
        with (
            patch("rock.utils.docker_safety.env_vars.ROCK_IMAGE_KEEP_PATTERNS", []),
            patch(
                "rock.utils.docker_safety.DockerUtil.remove_image",
                side_effect=subprocess.CalledProcessError(1, ["docker", "rmi"]),
            ),
        ):
            result = safe_remove_image("my-app:1.0")
        assert result is False

    @pytest.mark.parametrize(
        "image,patterns,expected",
        [
            # fullmatch semantics: substring should NOT match unless pattern allows
            ("my-rock-base-app", ["^rock-base.*$"], True),
            # wildcard prefix anchored
            ("rock-base", ["^rock-base.*$"], False),
            # multiple patterns: any match wins
            ("foo:1", ["^bar.*$", "^foo.*$"], False),
            # no patterns → allow
            ("anything:any", [], True),
        ],
    )
    def test_fullmatch_semantics(self, image, patterns, expected):
        """Whitelist uses re.fullmatch; substring matches do not protect."""
        with (
            patch("rock.utils.docker_safety.env_vars.ROCK_IMAGE_KEEP_PATTERNS", patterns),
            patch("rock.utils.docker_safety.DockerUtil.remove_image"),
        ):
            assert safe_remove_image(image) is expected
