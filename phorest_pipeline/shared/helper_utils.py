import datetime
import logging
import shutil
from pathlib import Path


def move_existing_files_to_backup(source_files: list, logger: logging.Logger) -> None:
    """
    Moves listed files to a destination directory.
    """

    if not source_files:
        return
    
    destination_path = Path("backup")

    # 1. Check source files
    files_to_move = []
    for source_file in source_files:
        if not source_file.exists():
            logger.info(f"Source directory '{source_file}' does not exist. Skipping...")
            continue
        if source_file.is_dir():
            logger.error(f"Source path '{source_file}' is a directory.")
            continue
        files_to_move.append(source_file)

    if not files_to_move:
        return

    # 2. Check destination
    try:
        destination_path.mkdir(parents=True, exist_ok=True)
        if not destination_path.is_dir():
            logger.error(
                f"Destination path '{destination_path}' exists but is not a directory."
            )
            return
    except Exception as e:
        logger.error(f"Error creating/accessing destination directory '{destination_path}': {e}")
        return

    logger.info(f"Moving files to '{destination_path}'...")

    # 3. Iterate through source directory and move files
    files_moved_count = 0
    errors_count = 0

    for item in files_to_move:
        if item.is_file():
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            destination_file_path = Path(
                destination_path,
                item.with_name(f"{item.stem}_{timestamp}{item.suffix}"),
            )
            try:
                destination_file_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(item), str(destination_file_path))
                logger.info(f"Moved: '{item}' to '{destination_file_path}'")
                files_moved_count += 1
            except shutil.Error as e:
                logger.error(f"Error moving '{item.name}': {e}")
                errors_count += 1
            except Exception as e:
                logger.error(f"Unexpected error moving '{item.name}': {e}")
                errors_count += 1

            # Check for and remove associated .tmp file
            temp_file_path = item.with_suffix(item.suffix + '.tmp')
            if temp_file_path.exists():
                try:
                    temp_file_path.unlink() # Delete the temporary file
                    logger.info(f"Cleaned up stale temporary file: {temp_file_path.name}.")
                except OSError as e:
                    logger.error(f"Could not delete stale temporary file {temp_file_path.name}: {e}")

        else:
            logger.info(f"Skipped directory: '{item.name}'")

    logger.info("Finished moving files.")
    logger.info(f"    Total files moved: {files_moved_count}")
    if errors_count > 0:
        logger.error(f"Total errors: {errors_count}")
