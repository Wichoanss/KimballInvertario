import logging
import logging.handlers
import config

def setup_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))

    if not logger.handlers:
        # File Handler - con ruta absoluta desde config
        file_handler = logging.handlers.RotatingFileHandler(
            config.LOG_FILE, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8'
        )
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - [%(name)s] - %(message)s")
        file_handler.setFormatter(formatter)

        # Console output
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(logging.WARNING)

        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)

    return logger

