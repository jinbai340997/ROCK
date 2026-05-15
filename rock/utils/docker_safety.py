"""Safe image removal with whitelist guard.

Used by DockerDeployment._stop() when remove_images=True.

Protection: regex whitelist via ROCK_IMAGE_KEEP_PATTERNS env var
(default: ^.*envhub.*$ and ^rock-base.*$). Any image whose full
name matches a pattern is preserved.

Returns True only if the whitelist allows removal AND
DockerUtil.remove_image succeeds. False on whitelist hit or any
docker rmi failure (caller should treat False as a benign skip).
"""

import re
import subprocess

from rock import env_vars
from rock.logger import init_logger
from rock.utils.docker import DockerUtil

logger = init_logger(__name__)


def safe_remove_image(image: str) -> bool:
    """Conservative image removal. Returns True if actually removed.

    Skip semantics (return False):
        - image matches any pattern in ROCK_IMAGE_KEEP_PATTERNS
        - docker rmi fails (image still in use, partial removal, etc.)
    """
    patterns = env_vars.ROCK_IMAGE_KEEP_PATTERNS or []
    for p in patterns:
        if re.fullmatch(p, image):
            logger.info(f"Skip rm image {image}: matches whitelist pattern {p!r}")
            return False

    try:
        DockerUtil.remove_image(image)
        logger.info(f"Removed image {image}")
        return True
    except subprocess.CalledProcessError:
        logger.error(f"Failed to docker rmi {image}", exc_info=True)
        return False
