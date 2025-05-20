# phorest_pipeline/shared/logger_config.py
import logging
import logging.handlers
from pathlib import Path

from phorest_pipeline.shared.config import LOGS_DIR


def configure_logger(name=None, level=logging.INFO, log_filename='app.log', rotate_daily=False, log_to_terminal=False):
    """Configures a logger with the specified settings.

    Args:
        name (str, optional): The name of the logger. If None, uses the root logger. Defaults to None.
        level (int, optional): The logging level. Defaults to logging.INFO.
        log_filename (str, optional): The name of the log file. Defaults to 'app.log'.
        rotate_daily (bool, optional): Whether to rotate the log file daily at midnight. Defaults to False.

    Returns:
        logging.Logger: The configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        for handler in logger.handlers[:]: # Iterating of a slice allows in-place modification
            logger.removeHandler(handler)

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(module)s - %(name)s - %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')

    log_file_path = Path(LOGS_DIR, log_filename)
    if rotate_daily:
        file_handler = logging.handlers.TimedRotatingFileHandler(
            log_file_path,
            when='midnight',
            interval=1,
            backupCount=0,
            encoding='utf-8'
        )
    else:
        file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
    
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if log_to_terminal:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


if __name__ == '__main__':
    LOGS_DIR = Path('logs')
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logger = configure_logger(rotate_daily=True, log_filename='example.log')
    logger.info('This is an info message.')
    logger.error('This is an error message.')
