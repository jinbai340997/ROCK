import pytest

from rock import env_vars


class TestRockImageKeepPatterns:
    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("ROCK_IMAGE_KEEP_PATTERNS", raising=False)
        assert env_vars.ROCK_IMAGE_KEEP_PATTERNS == [
            "^.*envhub.*$",
            "^rock-base.*$",
        ]

    def test_override_with_comma_separated(self, monkeypatch):
        monkeypatch.setenv(
            "ROCK_IMAGE_KEEP_PATTERNS",
            "^foo$,^bar.*$, ^baz$ ",
        )
        assert env_vars.ROCK_IMAGE_KEEP_PATTERNS == [
            "^foo$",
            "^bar.*$",
            "^baz$",
        ]

    def test_empty_string_yields_default(self, monkeypatch):
        """Empty string → default whitelist (NOT empty list).
        To truly disable the whitelist, the call site must opt in explicitly."""
        monkeypatch.setenv("ROCK_IMAGE_KEEP_PATTERNS", "")
        assert env_vars.ROCK_IMAGE_KEEP_PATTERNS == [
            "^.*envhub.*$",
            "^rock-base.*$",
        ]

    def test_is_set_true_when_env_present(self, monkeypatch):
        monkeypatch.setenv("ROCK_IMAGE_KEEP_PATTERNS", "^x$")
        assert env_vars.is_set("ROCK_IMAGE_KEEP_PATTERNS") is True

    def test_is_set_false_when_env_absent(self, monkeypatch):
        monkeypatch.delenv("ROCK_IMAGE_KEEP_PATTERNS", raising=False)
        assert env_vars.is_set("ROCK_IMAGE_KEEP_PATTERNS") is False

    def test_lazy_re_evaluation(self, monkeypatch):
        """Each access re-reads os.environ — set then read in same test
        without needing importlib.reload."""
        monkeypatch.setenv("ROCK_IMAGE_KEEP_PATTERNS", "^a$")
        assert env_vars.ROCK_IMAGE_KEEP_PATTERNS == ["^a$"]

        monkeypatch.setenv("ROCK_IMAGE_KEEP_PATTERNS", "^b$,^c$")
        assert env_vars.ROCK_IMAGE_KEEP_PATTERNS == ["^b$", "^c$"]
