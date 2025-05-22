# phorest_pipeline/compressor/logic.py
import datetime
import gzip
import shutil
import time
from pathlib import Path

from phorest_pipeline.shared.config import (
    DATA_DIR,
    RESULTS_DIR,
    settings,
)
from phorest_pipeline.shared.logger_config import configure_logger
from phorest_pipeline.shared.states import BackupState

logger = configure_logger(name=__name__, rotate_daily=True, log_filename="file_backup.log")

RENAME_INTERVAL = 3600
POLL_INTERVAL = RENAME_INTERVAL / 20

FILES_TO_PROCESS = [
    Path(DATA_DIR, "processing_manifest.json"),
    Path(RESULTS_DIR, "processing_results.json"),
    Path(RESULTS_DIR, "communicating_results.csv"),
    Path(RESULTS_DIR, "processed_data_plot.png"),
]


def compress_files(files_to_process: list[Path]):
    logger.info('--- Compressing Files ---')
    for file_path in files_to_process:
        if not file_path.is_file():
            logger.warning(f"Skipping compression: '{file_path}' is not a file or does not exist.")
            continue

        try:
            output_file_path = file_path.with_suffix(file_path.suffix + '.gz')

            logger.info(f"Compressing '{file_path}' to '{output_file_path}'...")

            with file_path.open("rb") as f_in, gzip.open(output_file_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            
            # Remove the original file after compression
            file_path.unlink()

            logger.info(f"Successfully compressed: '{file_path}' to '{output_file_path}'")

        except FileNotFoundError:
            logger.error(f"Error compressing '{file_path}': File not found.")
        except PermissionError:
            logger.error(f"Error compressing '{file_path}': Permission denied to read or write.")
        except Exception as e:
            logger.error(f"An unexpected error occurred compressing '{file_path}': {e}")



def backup_and_empty_original_file(files_to_process: list[Path]) -> list[Path]:
    logger.info("--- Backing up and Emptying Files ---")
    files_to_compress = []
    for original_file_path in files_to_process:
        if not original_file_path.exists():
            logger.warning(f"File {original_file_path} does not exist. Skipping processing.")
            continue

        if not original_file_path.is_file():
            logger.warning(f"Path {original_file_path} is not a file. Skipping processing.")
            continue

        try:
            # 1. Generate the backup file name with datetime suffix
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file_path = Path('backup', original_file_path.with_name(
                f"{original_file_path.stem}_{timestamp}{original_file_path.suffix}"
            ))

            # 2. Copy the original file to the backup location
            shutil.copy2(str(original_file_path), str(backup_file_path))
            logger.info(f"Copied {original_file_path} to backup {backup_file_path}")

            # 3. Replace the original file with an empty file
            with original_file_path.open("w") as f:
                f.write("")  # Write an empty string to ensure it's empty
            logger.info(f"Emptied original file: {original_file_path}")
        except PermissionError:
            logger.error(
                f"Permission denied: Cannot process file {original_file_path}. Check file permissions."
            )
            continue
        except OSError as e:
            logger.error(f"OS error processing file {original_file_path}: {e}")
            continue
        except Exception as e:
            logger.error(
                f"An unexpected error occurred while processing {original_file_path}: {e}"
            )    
            continue
        files_to_compress.append(backup_file_path)
    return files_to_compress


def perform_file_backup_cycle(current_state: BackupState) -> BackupState:
    """State machine logic for the file renamer."""
    next_state = current_state

    if settings is None:
        logger.info("Configuration error. Halting.")
        time.sleep(POLL_INTERVAL * 5)
        return current_state  # Consider a FATAL_ERROR state

    match current_state:
        case BackupState.IDLE:
            logger.info("IDLE -> WAITING_TO_RUN")
            next_state = BackupState.WAITING_TO_RUN
            global next_run_time
            next_run_time = time.monotonic() + RENAME_INTERVAL

        case BackupState.WAITING_TO_RUN:
            logger.info(f"Waiting for {RENAME_INTERVAL} seconds until next cycle...")
            now = time.monotonic()
            if now >= next_run_time:
                logger.info("WAITING_TO_RUN -> BACKUP_FILES")
                next_state = BackupState.BACKUP_FILES
            else:
                time.sleep(POLL_INTERVAL)
        
        case BackupState.BACKUP_FILES:
            logger.info("--- Backing up files ---")
            files_to_compress = backup_and_empty_original_file(FILES_TO_PROCESS)
            compress_files(files_to_compress)
            logger.info("BACKUP_FILES -> IDLE")
            next_state = BackupState.IDLE

    return next_state


def run_file_backup():
    """Main loop for the file backup process."""
    logger.info("--- Starting File Renamer ---")
    print("--- Starting File Backup ---")

    current_state = BackupState.IDLE
    global next_run_time  # Needs to be accessible across state calls
    next_run_time = 0
    try:
        while True:
            current_state = perform_file_backup_cycle(current_state)
            if current_state == BackupState.IDLE or current_state == BackupState.CHECKING:
                time.sleep(0.1)
    except KeyboardInterrupt:
        logger.info("Shutdown requested.")
    finally:
        logger.info("--- File Backup Stopped ---")
        print("--- File Backup Stopped ---")
