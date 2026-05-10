import re
import subprocess

from rock import env_vars
from rock.logger import init_logger
from rock.utils.docker import DockerUtil

logger = init_logger(__name__)

"""Safe image removal with multi-layer protection.

Used by:
- DockerDeployment._stop() (when remove_images=True)
- (future) ImageCleanupTask docuum guard
- (future) disk_emergency_api hard-level cleanup

Protections (in order):
1. In-use check: skip if any running container references the image
2. EnvHub registration check: skip if image is registered as a
   ROCK environment template (would break new sandbox starts)
3. Whitelist regex: skip if image matches ROCK_IMAGE_KEEP_PATTERNS
   (default: ^.*envhub.*$ and ^rock-base.*$)

Returns True only if all checks pass and DockerUtil.remove_image
succeeds. False on any skip or failure (caller should NOT treat
this as an error; it's by design conservative).
"""

async def safe_remove_image(image: str) -> bool:
    """Conservative image removal. Returns True if actually removed."""
    # Layer 1: in-use check
    if _containers_using_image(image):
        logger.info(f"Skip rm image {image}: still used by running containers")
        return False

    # Layer 2: EnvHub registration check (best-effort, fail-safe)
    try:
        from rock.sdk.envhub.client import EnvHubClient
        client = EnvHubClient()
        envs = await client.list_envs()
        registered_images = {e.image for e in envs}
        if image in registered_images:
            logger.info(f"Skip rm image {image}: registered in EnvHub")
            return False
    except Exception as e:
        # Conservative: if we can't verify, do NOT delete.
        logger.warning(
            f"EnvHub check failed for image {image}; conservative skip: {e}"
        )
        return False

    # Layer 3: whitelist regex
    patterns = env_vars.ROCK_IMAGE_KEEP_PATTERNS or []
    if any(re.fullmatch(p, image) for p in patterns):
        logger.info(
            f"Skip rm image {image}: matches whitelist pattern in "
            f"ROCK_IMAGE_KEEP_PATTERNS"
        )
        return False

    # All checks passed — actually remove
    try:
        DockerUtil.remove_image(image)
        logger.info(f"Removed image {image}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(
            f"Failed to docker rmi {image}: {e}", exc_info=True,
        )
        return False

def _containers_using_image(image: str) -> bool:
    """Check via `docker ps --filter ancestor=<image>`."""
    try:
        result = subprocess.check_output(
            ["docker", "ps", "-q", "--filter", f"ancestor={image}"],
            timeout=10,
        )
        return bool(result.strip())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.warning(
            f"docker ps ancestor check failed for {image}: {e}; "
            f"conservative skip"
        )
        # Conservative: if we can't check, treat as in-use.
        return True