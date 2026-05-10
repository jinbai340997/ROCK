from enum import Enum


class LogCleanupPolicy(str, Enum):
    """Per-sandbox bind-mount log directory cleanup policy on _stop().

    Applies ONLY to the per-sandbox UUID dir under ROCK_LOGGING_PATH,
    NOT to host-side logs (/data/logs/*.log) which are managed by
    logrotate.
    """

    KEEP = "keep"
    """Do not touch the dir. Relies on FileCleanupTask to purge file
    contents by mtime; the empty dir shell may persist."""

    ARCHIVE_THEN_CLEAN = "archive_then_clean"
    """Default. Tar+gzip the dir to OSS first; only delete if upload
    succeeds. If OssConfig is missing or upload fails, the dir is
    PRESERVED — never silently destroyed. Safe even when ops forgets
    to wire OSS."""

    CLEAN_DIRECTLY = "clean_directly"
    """Delete without archiving. Caller explicitly accepts permanent
    loss. Use when no OSS budget and operator manually offloaded any
    needed logs upfront."""
