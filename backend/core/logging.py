import logging


LOGGER_NAME = "nexora"

logger = logging.getLogger(LOGGER_NAME)


def configure_logging() -> None:
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )
    )

    logger.addHandler(handler)
