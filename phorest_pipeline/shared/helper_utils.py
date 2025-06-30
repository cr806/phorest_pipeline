import datetime
import logging
from pathlib import Path

from phorest_pipeline.shared.metadata_manager import move_file_with_lock
from phorest_pipeline.shared.config import BACKUP_DIR

def move_existing_files_to_backup(source_files: list, logger: logging.Logger) -> None:
    """
    Moves a list of existing files to a backup directory, adding a timestamp
    to each. This process uses a file lock for safety.
    """
    if not source_files:
        return
    
    destination_root = Path(BACKUP_DIR)
    logger.info(f"Moving existing files to '{destination_root}'...")

    files_moved_count = 0
    errors_count = 0

    for source_file in source_files:
        if not source_file.exists() or source_file.is_dir():
            logger.info(f"Source '{source_file}' does not exist or is a directory. Skipping...")
            continue
        
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            destination_file = Path(destination_root, source_file.parent.name, f"{source_file.stem}_{timestamp}{source_file.suffix}")

            move_file_with_lock(source_file, destination_file)
            files_moved_count += 1
        except Exception as e:
            logger.error(f"Failed to move '{source_file.name}': {e}")
            errors_count += 1

    logger.info("Finished moving files.")
    logger.info(f"    Total files moved: {files_moved_count}")
    if errors_count > 0:
        logger.error(f"    Total errors: {errors_count}")

