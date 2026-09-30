import logging


LOGGER_NAME = "nexora"


def configure_logging() -> None:
    logger = logging.getLogger(LOGGER_NAME)

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
