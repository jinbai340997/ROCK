from rock.config import RockConfig
from rock.deployments.log_cleanup import LogCleanupPolicy
from rock.logger import init_logger

logger = init_logger(__name__)


def check_oss_consistency_with_log_policy(rock_config: RockConfig) -> None:
    """Startup-time consistency checks for admin service.

    These run once when admin starts and emit WARN logs but do NOT
    abort startup — the runtime fail-safe handles the actual risk
    (e.g. OssArchiver returns False on missing config, _stop() then
    preserves the dir).
    """
    policy = rock_config.sandbox_config.sandbox_log_cleanup_policy_default
    oss = rock_config.oss
    if policy == LogCleanupPolicy.ARCHIVE_THEN_CLEAN and not oss.bucket:
        logger.warning(
            "sandbox_log_cleanup_policy_default=archive_then_clean but "
            "OssConfig.bucket is empty. _stop() will preserve sandbox "
            "log dirs (fail-safe), so disk usage will keep growing. "
            "Either configure oss.* or change the policy default to "
            "'keep' (relies on FileCleanupTask) or 'clean_directly' "
            "(accepts permanent loss)."
        )
