import logging
from logging.handlers import RotatingFileHandler
from os import getenv
from pathlib import Path


def setup_logging() -> logging.Logger:
    """Configure the logger used for server-error API responses."""
    log_directory = Path(getenv("API_ERROR_LOG_DIR", "logs"))
    log_directory.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("api.errors")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    log_path = log_directory / "api-errors.log"
    if any(
        isinstance(handler, RotatingFileHandler)
        and Path(handler.baseFilename) == log_path.resolve()
        for handler in logger.handlers
    ):
        return logger

    handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(handler)
    return logger
