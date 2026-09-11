import logging
import logging.handlers
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


def setup_logging() -> logging.Logger:
    app_logger = logging.getLogger("backend")
    if app_logger.handlers:
        return app_logger  # --reload re-imports this module; don't double-attach handlers

    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    app_logger.addHandler(console_handler)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "backend.log", maxBytes=5 * 1024 * 1024, backupCount=3
    )
    file_handler.setFormatter(formatter)
    app_logger.addHandler(file_handler)

    return app_logger


logger = setup_logging()
