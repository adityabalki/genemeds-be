import logging
from logging.config import dictConfig

from pythonjsonlogger.json import JsonFormatter


def configure_logging(level: str) -> None:
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "()": JsonFormatter,
                    "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s",
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                }
            },
            "root": {
                "level": level.upper(),
                "handlers": ["default"],
            },
        }
    )
    logging.captureWarnings(True)

