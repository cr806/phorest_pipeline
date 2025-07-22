# phorest_pipeline/file_backup/logic.py
import datetime
import gzip
import shutil
import signal
import time
from pathlib import Path

from phorest_pipeline.shared.config import (
    BACKUP_DIR,
    CONFIG_FILEPATH,
    CSV_FILENAME,
    DATA_DIR,
    ENABLE_BACKUP,
    FILE_BACKUP_INTERVAL,
    FLAG_DIR,
    IMAGE_FILENAME,
    METADATA_FILENAME,
    RESULTS_DIR,
    RESULTS_FILENAME,
    ROI_MANIFEST_FILENAME,
    settings,
)
from phorest_pipeline.shared.logger_config import configure_logger
from phorest_pipeline.shared.metadata_manager import move_file_with_lock, update_service_status
from phorest_pipeline.shared.states import BackupState

logger = configure_logger(name=__name__, rotate_daily=True, log_filename="file_backup.log")

SCRIPT_NAME = "phorest-backup"

POLL_INTERVAL = FILE_BACKUP_INTERVAL / 20 if FILE_BACKUP_INTERVAL > (5 * 20) else 5

LIVE_FILES_TO_BACKUP = [
    Path(DATA_DIR, CONFIG_FILEPATH.name),
    Path(DATA_DIR, ROI_MANIFEST_FILENAME),
    Path(DATA_DIR, METADATA_FILENAME),
    Path(RESULTS_DIR, RESULTS_FILENAME),
    Path(RESULTS_DIR, CSV_FILENAME),
    Path(RESULTS_DIR, IMAGE_FILENAME),
]


def archive_live_files():
    """
    Archives the live data files by safely moving them to the backup directory
    using a locked, atomic operation handled by the metadata_manager
    """
    logger.info("--- Archiving Live Files ---   ")
    for original_filepath in LIVE_FILES_TO_BACKUP:
        if not original_filepath.exists():
            logger.warning(f"'{original_filepath.name}', does not exist. Skipping...")
            continue
        try:
            # 1. Generate the timestamped backup file name
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filepath = Path(
                BACKUP_DIR,
                original_filepath.parent.name,
                f"{original_filepath.stem}_{timestamp}{original_filepath.suffix}",
            )

            # 2. Move file
            move_file_with_lock(original_filepath, backup_filepath)
        except Exception as e:
            logger.error(f"Failed to archive {original_filepath}: {e}")
            continue


def compress_files_in_backup_dir():
    """
    Finds all non-gzipped files in the backup directory and compresses them.
    """
    logger.info("--- Compressing Backed-up Files ---")
    if not BACKUP_DIR.exists():
        logger.warning(f"Backup root directory '{BACKUP_DIR}' not found. Nothing to compress.")
        return

    # Find all files that don't end in .gz
    files_to_compress = [p for p in BACKUP_DIR.rglob("*") if p.is_file() and p.suffix != ".gz"]

    if not files_to_compress:
        logger.info("No new files to compress in backup directory.")
        return

    for file_path in files_to_compress:
        output_file_path = file_path.with_suffix(file_path.suffix + ".gz")
        try:
            logger.debug(f"Compressing '{file_path}' to '{output_file_path}'...")
            with file_path.open("rb") as f_in, gzip.open(output_file_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            file_path.unlink()
            logger.info(f"Successfully compressed and removed original: '{file_path}'")
        except Exception as e:
            logger.error(f"An unexpected error occurred compressing '{file_path}': {e}")


class FileBackup:
    """Encapsulates the state and logic for the file backup process."""

    def __init__(self):
        self.shutdown_requested = False
        self.current_state = BackupState.IDLE
        self.next_run_time = 0

        # Register the signal handler
        signal.signal(signal.SIGINT, self._graceful_shutdown)
        signal.signal(signal.SIGTERM, self._graceful_shutdown)

    def _graceful_shutdown(self, _signum, _frame):
        """Signal handler to initiate a graceful shutdown"""
        if not self.shutdown_requested:
            logger.info("Shutdown signal received. Finishing current cycle before stopping...")
            self.shutdown_requested = True

    def _perform_file_backup_cycle(self):
        """State machine logic for the file renamer."""

        if settings is None:
            logger.debug("Configuration error. Halting.")
            self.current_state = BackupState.FATAL_ERROR
            return

        match self.current_state:
            case BackupState.IDLE:
                logger.debug("IDLE -> WAITING_TO_RUN")
                self.next_run_time = time.monotonic() + FILE_BACKUP_INTERVAL
                logger.debug(f"Will wait for {FILE_BACKUP_INTERVAL} seconds until next cycle...")
                self.current_state = BackupState.WAITING_TO_RUN

            case BackupState.WAITING_TO_RUN:
                now = time.monotonic()
                if now >= self.next_run_time:
                    logger.debug("WAITING_TO_RUN -> BACKUP_FILES")
                    self.current_state = BackupState.BACKUP_FILES
                else:
                    for _ in range(int(POLL_INTERVAL)):
                        if self.shutdown_requested:
                            return
                        time.sleep(1)

            case BackupState.BACKUP_FILES:
                logger.info("--- Starting Full Backup and Compression Cycle ---")
                archive_live_files()
                compress_files_in_backup_dir()
                logger.info("--- Full Backup and Compression Cycle Finished ---")
                logger.debug("BACKUP_FILES -> IDLE")
                self.current_state = BackupState.IDLE

    def run(self):
        """Main loop for the file backup process."""
        logger.info("--- Starting File Backup ---")
        print("--- Starting File Backup ---")

        if settings is None:
            logger.debug("Configuration error. Halting.")
            return

        if not ENABLE_BACKUP:
            logger.info("File backup is disabled in config. Exiting.")
            return

        try:
            while not self.shutdown_requested:
                self._perform_file_backup_cycle()

                # After a cycle is complete, send a heartbeat.
                update_service_status(SCRIPT_NAME, heartbeat=True)

                if self.current_state == BackupState.IDLE:
                    time.sleep(0.1)
        except Exception as e:
            logger.critical(f"UNEXPECTED ERROR in main loop: {e}", exc_info=True)
        finally:
            logger.info("--- File Backup Stopped ---")
            print("--- File Backup Stopped ---")


def run_file_backup():
    """Main entry point to create and run a File_backup instanace."""
    file_backup = FileBackup()
    file_backup.run()
