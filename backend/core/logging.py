import logging


LOGGER_NAME = "nexora"

logger = logging.getLogger(LOGGER_NAME)


def configure_logging() -> None:
    logger.setLevel(logging.INFO)