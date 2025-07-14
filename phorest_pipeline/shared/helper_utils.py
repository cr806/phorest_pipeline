import datetime
import logging
from pathlib import Path

from phorest_pipeline.shared.config import (
    BACKUP_DIR,
    DATA_DIR,
    ENABLE_SYNCER,
    IMAGE_BUFFER_SIZE,
    METADATA_FILENAME,
)
from phorest_pipeline.shared.metadata_manager import load_metadata_with_lock, move_file_with_lock


def move_existing_files_to_backup(source_filepaths: list, logger: logging.Logger) -> None:
    """
    Moves a list of existing files to a backup directory, adding a timestamp
    to each. This process uses a file lock for safety.
    """
    if not source_filepaths:
        return

    destination_root = Path(BACKUP_DIR)
    logger.info(f"Moving existing files to '{destination_root}'...")

    files_moved_count = 0
    errors_count = 0

    for source_filepath in source_filepaths:
        if not source_filepath.exists() or source_filepath.is_dir():
            logger.info(f"Source '{source_filepath}' does not exist or is a directory. Skipping...")
            continue

        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            destination_file = Path(
                destination_root,
                source_filepath.parent.name,
                f"{source_filepath.stem}_{timestamp}{source_filepath.suffix}",
            )

            move_file_with_lock(source_filepath, destination_file)
            files_moved_count += 1
        except Exception as e:
            logger.error(f"Failed to move '{source_filepath.name}': {e}")
            errors_count += 1

    logger.info("Finished moving files.")
    logger.info(f"    Total files moved: {files_moved_count}")
    if errors_count > 0:
        logger.error(f"    Total errors: {errors_count}")


def ring_buffer_cleanup(logger: logging.Logger):
    """
    Manages the number of images on local storage, ensuring the buffer size
    is not exceeded. If the syncer is enabled, protects unsynced
    images from being deleted.
    """
    logger.info("Performing ring buffer cleanup...")
    try:
        # 1. Get all image files on disk, sorted by modification time (oldest first)
        image_files_on_disk = list(DATA_DIR.glob("*.png"))
        image_files_on_disk.extend(list(DATA_DIR.glob("*.jpg")))
        image_files_on_disk.extend(list(DATA_DIR.glob("*.jpeg")))
        image_files_on_disk.extend(list(DATA_DIR.glob("*.webp")))
        image_files_on_disk.extend(list(DATA_DIR.glob("*.tif")))
        image_files_on_disk.extend(list(DATA_DIR.glob("*.tiff")))

        image_files_on_disk.sort(key=lambda p: p.stat().st_mtime)

        num_images = len(image_files_on_disk)
        logger.info(f"Found {num_images} local images. Buffer limit: {IMAGE_BUFFER_SIZE}.")

        if num_images <= IMAGE_BUFFER_SIZE:
            logger.info("Image count is within buffer limit. No cleanup needed.")
            return

        # 2. Determine which files are eligible for deletion
        files_to_potentially_delete = image_files_on_disk[: num_images - IMAGE_BUFFER_SIZE]

        final_files_to_delete = []

        if ENABLE_SYNCER:
            # --- Sync-Aware Mode ---
            logger.info("Syncer is ENABLED. Checking sync status before deleting.")
            manifest_data = load_metadata_with_lock(Path(DATA_DIR, METADATA_FILENAME))

            # Create a lookup map for checking
            sync_status_map = {
                entry.get("camera_data", {}).get("filename"): entry.get("image_synced", False)
                for entry in manifest_data
                if entry.get("camera_data")
            }

            for file_path in files_to_potentially_delete:
                # The file is eligible for deletion ONLY if it has been synced.
                if sync_status_map.get(file_path.name, False):
                    final_files_to_delete.append(file_path)
                else:
                    logger.warning(f"Unsynced file will not be removed: {file_path.name}")
        else:
            # --- Local-Only Mode ---
            logger.info("Syncer is DISABLED. Deleting oldest files.")
            final_files_to_delete = files_to_potentially_delete

        # 4. Delete relevant files
        if not final_files_to_delete:
            logger.info("No files to delete after checking sync status.")
            return

        logger.info(f"Buffer limit exceeded. Deleting {len(final_files_to_delete)} image(s)...")
        for file_to_delete in final_files_to_delete:
            try:
                logger.info(f"Deleting: {file_to_delete.name}")
                file_to_delete.unlink()
            except OSError as delete_err:
                logger.error(f"Failed to delete image {file_to_delete.name}: {delete_err}")

    except Exception as buffer_err:
        logger.error(
            f"An unexpected error occurred during ring buffer cleanup: {buffer_err}", exc_info=True
        )
