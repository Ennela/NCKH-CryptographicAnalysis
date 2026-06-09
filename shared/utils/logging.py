import logging
import sys
from shared.config.settings import settings


def setup_logging():
    """
    Sets up structured logging configuration based on the ENV setting.
    In production, this could be structured json. For dev, it is human-readable.
    """
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO

    # Set up basic config
    logging.basicConfig(
        level=log_level, format=log_format, handlers=[logging.StreamHandler(sys.stdout)]
    )

    # Disable spammy logs
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("ccxt").setLevel(logging.WARNING)

    logger = logging.getLogger("app")
    logger.info(f"Logging initialized in {settings.ENV} mode (debug={settings.DEBUG})")
