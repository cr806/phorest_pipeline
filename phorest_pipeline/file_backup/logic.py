# phorest_pipeline/file_backup/logic.py
import datetime
import gzip
import shutil
import sys
import time
from pathlib import Path

from phorest_pipeline.shared.config import (
    BACKUP_DIR,
    DATA_DIR,
    ENABLE_BACKUP,
    FILE_BACKUP_INTERVAL,
    RESULTS_DIR,
    settings,
)
from phorest_pipeline.shared.logger_config import configure_logger
from phorest_pipeline.shared.metadata_manager import move_file_with_lock
from phorest_pipeline.shared.states import BackupState

logger = configure_logger(name=__name__, rotate_daily=True, log_filename="file_backup.log")

POLL_INTERVAL = FILE_BACKUP_INTERVAL / 20 if FILE_BACKUP_INTERVAL > (5 * 20) else 5
BACKUP_ROOT_PATH = Path(BACKUP_DIR)

LIVE_FILES_TO_BACKUP = [
    Path(DATA_DIR, "metadata_manifest.json"),
    Path(RESULTS_DIR, "processing_results.jsonl"),
    Path(RESULTS_DIR, "communicating_results.csv"),
    Path(RESULTS_DIR, "processed_data_plot.png"),
]


def archive_live_files():
    """
    Archives the live data files by safely moving them to the backup directory
    using a locked, atomic operation handled by the metadata_manager
    """
    logger.info("--- Archiving Live Files ---   ")
    for original_filepath in LIVE_FILES_TO_BACKUP:
        try:
            # 1. Generate the timestamped backup file name
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filepath = Path(
                BACKUP_ROOT_PATH,
                original_filepath.parent.name,
                f"{original_filepath.stem}_{timestamp}{original_filepath.suffix}",
            )

            # 2. Move file
            move_file_with_lock(original_filepath.parent, original_filepath.name, backup_filepath)
        except Exception as e:
            logger.error(f"Failed to archive {original_filepath}: {e}")
            continue


def compress_files_in_backup_dir():
    """
    Finds all non-gzipped files in the backup directory and compresses them.
    """
    logger.info("--- Compressing Backed-up Files ---")
    if not BACKUP_ROOT_PATH.exists():
        logger.warning(
            f"Backup root directory '{BACKUP_ROOT_PATH}' not found. Nothing to compress."
        )
        return

    # Find all files that don't end in .gz
    files_to_compress = [
        p for p in BACKUP_ROOT_PATH.rglob("*") if p.is_file() and p.suffix != ".gz"
    ]

    if not files_to_compress:
        logger.info("No new files to compress in backup directory.")
        return

    for file_path in files_to_compress:
        output_file_path = file_path.with_suffix(file_path.suffix + ".gz")
        try:
            logger.info(f"Compressing '{file_path}' to '{output_file_path}'...")
            with file_path.open("rb") as f_in, gzip.open(output_file_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            file_path.unlink()
            logger.info(f"Successfully compressed and removed original: '{file_path}'")
        except Exception as e:
            logger.error(f"An unexpected error occurred compressing '{file_path}': {e}")


def perform_file_backup_cycle(current_state: BackupState) -> BackupState:
    """State machine logic for the file renamer."""
    next_state = current_state

    if settings is None:
        logger.info("Configuration error. Halting.")
        time.sleep(POLL_INTERVAL * 5)
        return current_state  # FATAL_ERROR state ?

    match current_state:
        case BackupState.IDLE:
            logger.info("IDLE -> WAITING_TO_RUN")
            next_state = BackupState.WAITING_TO_RUN
            global next_run_time
            next_run_time = time.monotonic() + FILE_BACKUP_INTERVAL
            logger.info(f"Will wait for {FILE_BACKUP_INTERVAL} seconds until next cycle...")

        case BackupState.WAITING_TO_RUN:
            now = time.monotonic()
            if now >= next_run_time:
                logger.info("WAITING_TO_RUN -> BACKUP_FILES")
                next_state = BackupState.BACKUP_FILES
            else:
                time.sleep(POLL_INTERVAL)

        case BackupState.BACKUP_FILES:
            logger.info("--- Starting Full Backup and Compression Cycle ---")
            archive_live_files()
            compress_files_in_backup_dir()
            logger.info("--- Full Backup and Compression Cycle Finished ---")
            logger.info("BACKUP_FILES -> IDLE")
            next_state = BackupState.IDLE

    return next_state


def run_file_backup():
    """Main loop for the file backup process."""
    logger.info("--- Starting File Backup ---")
    print("--- Starting File Backup ---")

    if settings is None:
        logger.info("Configuration error. Halting.")
        sys.exit(1)

    current_state = BackupState.IDLE
    global next_run_time  # Needs to be accessible across state calls
    next_run_time = 0
    try:
        while True:
            if not ENABLE_BACKUP:
                logger.info("File backup is disabled in config. Exiting.")
                break

            current_state = perform_file_backup_cycle(current_state)
            if current_state == BackupState.IDLE or current_state == BackupState.CHECKING:
                time.sleep(0.1)
    except KeyboardInterrupt:
        logger.info("Shutdown requested.")
    finally:
        logger.info("--- File Backup Stopped ---")
        print("--- File Backup Stopped ---")
